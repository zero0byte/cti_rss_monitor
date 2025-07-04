from app import db
from datetime import datetime
import uuid

# Association table for many-to-many relationship between Article and Tag
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    openai_api_key = db.Column(db.String(255), nullable=True)
    joplin_api_url = db.Column(db.String(255), nullable=True)
    joplin_token = db.Column(db.String(255), nullable=True)
    joplin_enabled = db.Column(db.Boolean, default=True)  # Toggle for Joplin integration
    check_interval = db.Column(db.Integer, default=60)  # Minutes between feed checks
    max_article_age = db.Column(db.Integer, default=0)  # Maximum age of articles to process in days (0 = no limit)

class Prompt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    model = db.Column(db.String(50), nullable=False)

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    category = db.Column(db.String(50), default='general')
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    articles = db.relationship('Article', backref='feed', lazy=True, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<Feed {self.name}>'

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    color = db.Column(db.String(20), default='#6c757d')  # Default color (Bootstrap secondary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Tag {self.name}>'

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False, unique=True)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    content = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    published = db.Column(db.DateTime, nullable=True)
    processed = db.Column(db.Boolean, default=False)
    processing = db.Column(db.Boolean, default=False)  # Flag to indicate article is currently being processed
    processing_started = db.Column(db.DateTime, nullable=True)  # Timestamp when processing started
    sent_to_joplin = db.Column(db.Boolean, default=False)
    joplin_id = db.Column(db.String(100), nullable=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Many-to-many relationship with Tag
    tags = db.relationship('Tag', secondary=article_tags, lazy='subquery',
                           backref=db.backref('articles', lazy=True))
    
    def __repr__(self):
        return f'<Article {self.title}>'
