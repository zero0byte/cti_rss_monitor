#!/usr/bin/env python
"""
Startup script for CTI Monitor
This script initializes the database, adds sample feeds if needed, and starts the application.
"""
import os
import sys
import time
import subprocess
import webbrowser
import threading
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are installed"""
    try:
        import flask
        import flask_sqlalchemy
        import openai
        import requests
        import feedparser
        import apscheduler
        import bs4
        import html2text
        import markdown
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def init_database():
    """Initialize the database with sample feeds"""
    print("Initializing database with sample feeds...")
    try:
        import init_db
        init_db.init_db()
        print("Database initialization complete.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        return False
    return True

def start_application():
    """Start the Flask application"""
    print("Starting CTI Monitor application...")
    
    # For local development, use subprocess to allow for browser opening
    env = os.environ.copy()
    
    # Set environment variable to indicate this is the main process that should run the scheduler
    env['MAIN_PROCESS'] = 'true'
    
    flask_process = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        env=env
    )
    
    # Wait a moment for the server to start
    time.sleep(2)
    
    # Open browser in a separate thread to avoid blocking
    print("Opening browser to http://localhost:5000")
    try:
        def open_browser():
            try:
                webbrowser.open("http://localhost:5000")
            except Exception as e:
                print(f"Error opening browser: {str(e)}")
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
    except Exception as e:
        print(f"Error starting browser thread: {str(e)}")
    
    try:
        # Print Flask output
        while True:
            output = flask_process.stdout.readline()
            if output:
                print(output.strip())
            if flask_process.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\nShutting down...")
        flask_process.terminate()
        flask_process.wait()
    except Exception as e:
        print(f"Error: {e}")
        flask_process.terminate()
        flask_process.wait()

if __name__ == "__main__":
    print("=" * 50)
    print("CTI Monitor - RSS to Joplin Integration")
    print("=" * 50)
    
    # Ensure we're in the right directory
    os.chdir(Path(__file__).parent)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Initialize database
    if not init_database():
        sys.exit(1)
    
    # Start application
    start_application()
