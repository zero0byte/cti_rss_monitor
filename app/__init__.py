from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize SQLAlchemy
db = SQLAlchemy()

def create_app(init_scheduler=True):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///settings.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    # Add custom template filters
    @app.template_filter('from_json')
    def from_json(value):
        import json
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    
    # Import and register blueprints
    from app.routes import main
    from app.feed_routes import feeds
    from app.tag_routes import tags
    app.register_blueprint(main)
    app.register_blueprint(feeds)
    app.register_blueprint(tags)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Initialize default settings if they don't exist
        from app.models import Settings, Prompt
        if not Settings.query.first():
            default_settings = Settings(
                openai_api_key='',
                joplin_api_url='http://localhost:41184/notes',
                joplin_token='',
                check_interval=60
            )
            db.session.add(default_settings)
            
        # Create default prompts if they don't exist
        if not Prompt.query.filter_by(name='filter_prompt').first():
            filter_prompt = Prompt(
                name='filter_prompt',
                content='Determine if this article contains valuable threat intelligence information such as new threats, vulnerabilities, TTPs, or IOCs. Respond with only "KEEP" or "DISCARD".',
                model='gpt-3.5-turbo'
            )
            db.session.add(filter_prompt)
        
        if not Prompt.query.filter_by(name='parse_prompt').first():
            parse_prompt = Prompt(
                name='parse_prompt',
                content='Parse this article and extract the following information in JSON format: {"summary": "brief overview of the threat or vulnerability", "threat_groups": ["list of threat actors mentioned"], "ttp": ["list of tactics, techniques, procedures"], "tags": ["relevant tags"]}. Be concise and focus on actionable threat intelligence.',
                model='gpt-4'
            )
            db.session.add(parse_prompt)
            
        db.session.commit()
    
    # Initialize scheduler if requested and we're in the main process
    # This ensures only one scheduler instance runs across all processes
    if init_scheduler and os.environ.get('MAIN_PROCESS') == 'true':
        from app.scheduler import init_scheduler
        scheduler = init_scheduler(app)
        if scheduler:
            app.logger.info("Scheduler initialized and started successfully")
        else:
            app.logger.warning("Scheduler could not be initialized or another instance is already running")
    else:
        app.logger.info("Scheduler initialization skipped - not in main process or initialization not requested")
    
    return app
