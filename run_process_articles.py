#!/usr/bin/env python
import os
import sys
import logging
from app import create_app
from app.feed_processor import process_pending_articles

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Process pending articles immediately without using the scheduler"""
    try:
        logger.info("Starting immediate article processing")
        
        # Create app context
        app = create_app(init_scheduler=False)  # Don't initialize scheduler
        
        # Process articles within app context
        with app.app_context():
            logger.info("Processing pending articles")
            result = process_pending_articles()
            
            if result:
                logger.info("Article processing completed successfully")
                return 0
            else:
                logger.error("Article processing failed or no articles were processed")
                return 1
                
    except Exception as e:
        logger.error(f"Error during article processing: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
