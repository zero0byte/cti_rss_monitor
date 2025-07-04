#!/usr/bin/env python
"""
Clean Scheduler Script for CTI Monitor
This script removes any stale lock files and helps reset the scheduler state
"""

import os
import tempfile
import psutil
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('clean_scheduler')

# Lock file path - must match the one in scheduler.py
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'cti_monitor_scheduler.lock')

def remove_lock_file():
    """Remove the scheduler lock file if it exists"""
    try:
        if os.path.exists(LOCK_FILE):
            logger.info(f"Found lock file at {LOCK_FILE}")
            with open(LOCK_FILE, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    try:
                        pid = int(pid_str)
                        if psutil.pid_exists(pid):
                            logger.warning(f"Process with PID {pid} exists. Checking if it's a Python process...")
                            try:
                                process = psutil.Process(pid)
                                if "python" in process.name().lower():
                                    logger.warning(f"Process {pid} appears to be a Python process. It might be the scheduler.")
                                    if "--force" in sys.argv:
                                        logger.warning("Force flag set, removing lock file anyway")
                                    else:
                                        logger.error("Aborting. Use --force to remove the lock file anyway.")
                                        return False
                                else:
                                    logger.info(f"Process {pid} is not a Python process ({process.name()}), safe to remove lock")
                            except psutil.NoSuchProcess:
                                logger.info(f"Process {pid} no longer exists")
                        else:
                            logger.info(f"No process with PID {pid} exists")
                    except ValueError:
                        logger.warning(f"Invalid PID in lock file: {pid_str}")
            
            os.remove(LOCK_FILE)
            logger.info("Lock file removed successfully")
            return True
        else:
            logger.info("No lock file found")
            return True
    except Exception as e:
        logger.error(f"Error removing lock file: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("CTI Monitor Scheduler Cleanup Utility")
    
    if remove_lock_file():
        logger.info("Cleanup completed successfully")
        sys.exit(0)
    else:
        logger.error("Cleanup failed")
        sys.exit(1)
