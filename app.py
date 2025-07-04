from app import create_app
from datetime import datetime
import os
import sys

# Set MAIN_PROCESS environment variable when running directly
if __name__ == "__main__":
    os.environ['MAIN_PROCESS'] = 'true'
    print("Setting MAIN_PROCESS=true to enable scheduler initialization")

# Initialize the scheduler in the Flask app
app = create_app(init_scheduler=True)

# Add context processor for current year in templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

if __name__ == "__main__":
    print("Starting Flask app with scheduler enabled")
    app.run(host="0.0.0.0", port=5000, debug=True)
