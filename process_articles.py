#!/usr/bin/env python
import os
import sys
import logging
import warnings
from app import create_app
from app.feed_processor import process_pending_articles

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Display deprecation warning
warnings.warn(
    "DEPRECATED: This script is deprecated and will be removed in a future version. "
    "Please use run_process_articles.py instead, which properly disables scheduler initialization.",
    DeprecationWarning, stacklevel=2
)
print("WARNING: This script is deprecated. Please use run_process_articles.py instead.")

def main():
    """Process pending articles manually without using the scheduler"""
    try:
        logger.info("Starting manual article processing")
        
        # Create app context
        app = create_app()
        
        # Process articles within app context
        with app.app_context():
            logger.info("Processing pending articles")
            result = process_pending_articles()
            
            if result:
                logger.info("Article processing completed successfully")
                return 0
            else:
                logger.error("Article processing failed")
                return 1
                
    except Exception as e:
        logger.error(f"Error during manual article processing: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
