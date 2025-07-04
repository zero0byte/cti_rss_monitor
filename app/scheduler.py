import os
import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from pytz import utc
from datetime import datetime, timedelta
from app.feed_processor import check_all_feeds, process_pending_articles
from app.models import Settings
from app import db
import atexit
import os
import tempfile
import socket
import time
import psutil

# Configure logging
logger = logging.getLogger(__name__)

# Global variables
scheduler = None
app_instance = None

# Lock file path
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'cti_monitor_scheduler.lock')

# Function to remove the lock file
def remove_lock_file():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            logger.info("Removed scheduler lock file")
    except Exception as e:
        logger.error(f"Error removing lock file: {str(e)}")

# Function to get the PID of a running scheduler from the lock file
def get_scheduler_pid():
    """Check if a scheduler lock file exists and return the PID and lock file status"""
    try:
        # Check if lock file exists
        if not os.path.exists(LOCK_FILE):
            return None, False
            
        # Read the lock file
        with open(LOCK_FILE, 'r') as f:
            pid_str = f.read().strip()
            if not pid_str:  # Empty file
                logger.info("Found empty lock file, removing it")
                remove_lock_file()
                return None, False
                
            pid = int(pid_str)
            
            # If the PID in the lock file is our own PID, we're good
            if pid == os.getpid():
                logger.info(f"Found our own lock file with PID {pid}")
                return pid, True
                
            return pid, True
    except Exception as e:
        logger.error(f"Error getting scheduler PID: {str(e)}")
        return None, False

# Function to check if another scheduler instance is running
def is_scheduler_running():
    # Always return False to force a new scheduler to start
    # This is a temporary fix to ensure the scheduler always starts
    # Remove any existing lock file to be safe
    if os.path.exists(LOCK_FILE):
        logger.warning("Removing existing lock file to ensure clean start")
        remove_lock_file()
    return False

# Cleanup function to run when the app exits
def cleanup():
    """Shutdown the scheduler and remove the lock file"""
    global scheduler
    
    if scheduler and scheduler.running:
        logger.info("Shutting down scheduler")
        try:
            scheduler.shutdown()
            logger.info("Scheduler shutdown successfully")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {str(e)}")
    
    # Always try to remove the lock file
    try:
        remove_lock_file()
        logger.info("Lock file removed successfully")
    except Exception as e:
        logger.error(f"Error removing lock file: {str(e)}")

# Alias for cleanup to maintain compatibility with both function names
def cleanup_lock_file():
    cleanup()

# Function to create a lock file
def create_lock_file():
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"Created scheduler lock file with PID {os.getpid()}")
        return True
    except Exception as e:
        logger.error(f"Error creating scheduler lock file: {str(e)}")
        return False

# Function to get the feed check interval from settings
def get_feed_check_interval():
    with app_instance.app_context():
        settings = Settings.query.first()
        return settings.check_interval if settings else 60  # Default to 60 minutes

# Job function to check feeds
def check_feeds_job():
    with app_instance.app_context():
        logger.info("Running scheduled feed check")
        result = check_all_feeds()
        logger.info(f"Feed check completed: {result}")
        return result

# Job function to process pending articles
def process_articles_job():
    # Create a lock file to prevent concurrent processing
    lock_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'article_processing.lock')
    
    # Check if a lock file exists (another process is running)
    if os.path.exists(lock_file):
        # Check if the lock is stale (older than 10 minutes)
        lock_time = os.path.getmtime(lock_file)
        current_time = time.time()
        if current_time - lock_time > 600:  # 10 minutes in seconds
            logger.warning("Found stale article processing lock file. Removing it.")
            try:
                os.remove(lock_file)
            except Exception as e:
                logger.error(f"Failed to remove stale lock file: {str(e)}")
                return False
        else:
            logger.info("Article processing already in progress. Skipping this run.")
            return False
    
    try:
        # Create the lock file
        with open(lock_file, 'w') as f:
            f.write(f"Article processing started at {datetime.utcnow().isoformat()}")
        
        with app_instance.app_context():
            logger.info("Processing pending articles")
            result = process_pending_articles()
            logger.info(f"Article processing completed: {result}")
            return result
    finally:
        # Always remove the lock file when done
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception as e:
                logger.error(f"Failed to remove lock file: {str(e)}")


# Function to add jobs to the scheduler
def add_jobs(app):
    global app_instance, scheduler
    
    # Store app instance for use in job functions
    app_instance = app
    
    # Make sure scheduler is initialized
    if not scheduler or not scheduler.running:
        logger.warning("Scheduler not initialized or not running. Initializing now.")
        init_scheduler(app)
        
    if not scheduler or not scheduler.running:
        logger.error("Failed to initialize scheduler. Cannot add jobs.")
        return False
    
    # Get feed check interval from settings
    check_interval = get_feed_check_interval()
    logger.info(f"Setting up feed check job with interval of {check_interval} minutes")
    
    # Add job to check feeds
    scheduler.add_job(
        func=check_feeds_job,
        trigger=IntervalTrigger(minutes=check_interval),
        id='check_feeds',
        name='Check all active feeds',
        replace_existing=True
    )
    logger.info("Feed check job added to scheduler")
    
    # Add job to process pending articles
    scheduler.add_job(
        func=process_articles_job,
        trigger=IntervalTrigger(minutes=5),  # Process articles every 5 minutes
        id='process_articles',
        name='Process pending articles',
        replace_existing=True
    )
    logger.info("Article processing job added to scheduler")
    return True
    
    # Log all jobs
    jobs = scheduler.get_jobs()
    logger.info(f"Total jobs scheduled: {len(jobs)}")
    for job in jobs:
        logger.info(f"Job: {job.id} added to scheduler")
    
    return True

# Initialize the scheduler
def init_scheduler(app, connect_only=False):
    global scheduler, app_instance

    # If scheduler is already initialized in this process, return it
    if scheduler and scheduler.running:
        logger.info("Scheduler already initialized and running in this process")
        return scheduler
        
    # Always remove any existing lock file to ensure a clean start
    if os.path.exists(LOCK_FILE):
        logger.warning("Removing any existing lock file before starting scheduler")
        remove_lock_file()
    
    # No scheduler is running, initialize a new one
    try:
        # Create lock file
        create_lock_file()
        
        # Configure the scheduler
        job_stores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 1
        }
        
        # Create and configure the scheduler
        scheduler = BackgroundScheduler(
            jobstores=job_stores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=utc
        )
        
        # Store app instance for job context
        app_instance = app
        
        # Register cleanup function
        atexit.register(cleanup)
        
        # Start the scheduler
        scheduler.start()
        logger.info("Scheduler started successfully")
        
        # Add jobs
        add_jobs(app)
        
        # Log scheduler status
        log_scheduler_status()
        
        return scheduler
    except Exception as e:
        logger.error(f"Error initializing scheduler: {str(e)}")
        # Clean up lock file if initialization fails
        remove_lock_file()
        return None

# Function to get the scheduler instance
def get_scheduler():
    global scheduler
    
    # If scheduler is not initialized in this process, try to connect to running instance
    if not scheduler:
        try:
            pid, _ = get_scheduler_pid()
            if pid:
                logger.debug(f"Attempting to connect to existing scheduler with PID {pid}")
                from flask import current_app
                if current_app:
                    init_scheduler(current_app._get_current_object(), connect_only=True)
        except Exception as e:
            logger.debug(f"Error connecting to scheduler: {str(e)}")
    
    return scheduler

# Function to log scheduler status
def log_scheduler_status():
    """Log the current status of the scheduler and its jobs"""
    global scheduler
    
    if not scheduler:
        logger.warning("Cannot log scheduler status: scheduler not initialized")
        return
    
    try:
        logger.info(f"Scheduler running: {scheduler.running}")
        jobs = scheduler.get_jobs()
        logger.info(f"Total jobs in scheduler: {len(jobs)}")
        
        for job in jobs:
            try:
                next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'Not scheduled'
                logger.info(f"Job: {job.id}, Next run: {next_run}")
            except Exception as e:
                logger.error(f"Error getting job details for {job.id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error logging scheduler status: {str(e)}")

# Update the feed check interval
def update_feed_check_interval(minutes):
    global scheduler
    
    # Log the update
    logger.info(f"Updating feed check interval to {minutes} minutes")
    
    # If we have a scheduler in this process, update the job directly
    if scheduler and scheduler.running:
        try:
            job = scheduler.get_job('feed_check')
            if job:
                job.reschedule(trigger='interval', minutes=minutes)
                logger.info(f"Feed check job rescheduled with interval: {minutes} minutes")
            else:
                scheduler.add_job(
                    id='feed_check',
                    func=check_feeds_job,
                    trigger='interval',
                    minutes=minutes,
                    replace_existing=True
                )
                logger.info(f"Feed check job added with interval: {minutes} minutes")
            return True
        except Exception as e:
            logger.error(f"Error updating scheduler job: {str(e)}")
    else:
        # If no scheduler in this process, just log it
        logger.info(f"No active scheduler in this process. Interval updated in database only.")
    
    return True

# Function to check if scheduler is initialized
def is_scheduler_initialized():
    global scheduler
    
    # If scheduler is not initialized in this process, try to connect to running instance
    if not scheduler:
        try:
            pid, _ = get_scheduler_pid()
            if pid:
                logger.debug(f"Attempting to connect to existing scheduler with PID {pid}")
                from flask import current_app
                if current_app:
                    init_scheduler(current_app._get_current_object(), connect_only=True)
        except Exception as e:
            logger.debug(f"Error connecting to scheduler: {str(e)}")
    
    return scheduler is not None

# Function to manually trigger feed check
def manual_check_feeds():
    """Manually trigger a feed check"""
    if not is_scheduler_initialized():
        logger.info("Scheduler not initialized, running feed check directly")
        try:
            # If scheduler is not initialized, we can still run the job function directly
            if app_instance:
                with app_instance.app_context():
                    result = check_all_feeds()
                    logger.info(f"Manual feed check completed: {result}")
                    return result
            else:
                logger.error("App instance not available, cannot run feed check")
                return False
        except Exception as e:
            logger.error(f"Error running manual feed check: {str(e)}")
            return False
    else:
        # If scheduler is initialized, we can use it to run the job
        try:
            scheduler.add_job(
                func=check_feeds_job,
                trigger='date',  # Run once immediately
                id='manual_check_feeds',
                name='Manual feed check',
                replace_existing=True
            )
            logger.info("Manual feed check scheduled")
            return True
        except Exception as e:
            logger.error(f"Error scheduling manual feed check: {str(e)}")
            return False

# Function to manually trigger article processing
def manual_process_articles():
    """Manually trigger article processing"""
    if not is_scheduler_initialized():
        logger.info("Scheduler not initialized, running article processing directly")
        try:
            # If scheduler is not initialized, we can still run the job function directly
            if app_instance:
                with app_instance.app_context():
                    result = process_pending_articles()
                    logger.info(f"Manual article processing completed: {result}")
                    return result
            else:
                logger.error("App instance not available, cannot run article processing")
                return False
        except Exception as e:
            logger.error(f"Error running manual article processing: {str(e)}")
            return False
    else:
        # If scheduler is initialized, we can use it to run the job
        try:
            scheduler.add_job(
                func=process_articles_job,
                trigger='date',  # Run once immediately
                id='manual_process_articles',
                name='Manual article processing',
                replace_existing=True
            )
            logger.info("Manual article processing scheduled")
            return True
        except Exception as e:
            logger.error(f"Error scheduling manual article processing: {str(e)}")
            return False
