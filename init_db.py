"""
Initialize the database with sample feeds.
Run this script after setting up the application to add some initial RSS feeds.
"""
from app import create_app, db
from app.models import Feed

# Sample cybersecurity and threat intelligence RSS feeds
SAMPLE_FEEDS = [
    {
        'name': 'Krebs on Security',
        'url': 'https://krebsonsecurity.com/feed/',
        'category': 'security_news'
    },
    {
        'name': 'The Hacker News',
        'url': 'https://feeds.feedburner.com/TheHackersNews',
        'category': 'security_news'
    },
    {
        'name': 'Bleeping Computer',
        'url': 'https://www.bleepingcomputer.com/feed/',
        'category': 'security_news'
    },
    {
        'name': 'CISA Alerts',
        'url': 'https://www.cisa.gov/uscert/ncas/alerts.xml',
        'category': 'government'
    },
    {
        'name': 'Microsoft Security Blog',
        'url': 'https://www.microsoft.com/en-us/security/blog/feed/',
        'category': 'vendor'
    },
    {
        'name': 'Google Security Blog',
        'url': 'https://security.googleblog.com/feeds/posts/default',
        'category': 'vendor'
    }
]

def init_db():
    """Initialize the database with sample feeds"""
    # Create app without initializing scheduler to avoid circular imports
    app = create_app(init_scheduler=False)
    
    with app.app_context():
        print("Checking for existing feeds...")
        existing_count = Feed.query.count()
        
        if existing_count > 0:
            print(f"Database already contains {existing_count} feeds. Skipping initialization.")
            return
        
        print("Adding sample feeds to database...")
        for feed_data in SAMPLE_FEEDS:
            feed = Feed(
                name=feed_data['name'],
                url=feed_data['url'],
                category=feed_data['category']
            )
            db.session.add(feed)
        
        db.session.commit()
        print(f"Added {len(SAMPLE_FEEDS)} sample feeds to the database.")

if __name__ == '__main__':
    init_db()
