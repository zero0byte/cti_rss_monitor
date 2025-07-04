#!/usr/bin/env python
import os
import sys
import logging
from app import create_app
from app.scheduler import init_scheduler, add_jobs

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Run the scheduler manually with proper environment variables"""
    try:
        # Set the MAIN_PROCESS environment variable to true
        os.environ['MAIN_PROCESS'] = 'true'
        
        logger.info("Starting scheduler with MAIN_PROCESS=true")
        
        # Create app
        app = create_app(init_scheduler=False)  # Don't init scheduler in create_app
        
        # Initialize scheduler manually
        scheduler = init_scheduler(app)
        
        if not scheduler:
            logger.error("Failed to initialize scheduler")
            return 1
            
        # Add jobs to scheduler
        if not add_jobs(app):
            logger.error("Failed to add jobs to scheduler")
            return 1
            
        logger.info("Scheduler initialized and jobs added successfully")
        logger.info("Press Ctrl+C to exit")
        
        # Keep the script running to maintain the scheduler
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down scheduler")
            scheduler.shutdown()
            return 0
                
    except Exception as e:
        logger.error(f"Error running scheduler: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
