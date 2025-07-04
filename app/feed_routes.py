import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from app.models import Feed, Article, Settings, Tag
from app import db
from app.feed_processor import check_feed, process_article
from app.scheduler import update_feed_check_interval
from datetime import datetime
import json

feeds = Blueprint('feeds', __name__)

@feeds.route('/feeds')
def feed_list():
    """Display list of feeds"""
    all_feeds = Feed.query.all()
    settings = Settings.query.first()
    return render_template('feeds.html', feeds=all_feeds, settings=settings)

@feeds.route('/feeds/add', methods=['POST'])
def add_feed():
    """Add a new feed"""
    name = request.form.get('name')
    url = request.form.get('url')
    category = request.form.get('category', 'general')
    
    if not name or not url:
        flash('Name and URL are required', 'error')
        return redirect(url_for('feeds.feed_list'))
    
    # Check if feed already exists
    existing = Feed.query.filter_by(url=url).first()
    if existing:
        flash(f'Feed with URL {url} already exists', 'error')
        return redirect(url_for('feeds.feed_list'))
    
    # Create new feed
    feed = Feed(name=name, url=url, category=category)
    db.session.add(feed)
    db.session.commit()
    
    # Check the feed immediately
    check_feed(feed.id)
    
    flash(f'Feed {name} added successfully', 'success')
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/feeds/<int:feed_id>/toggle', methods=['POST'])
def toggle_feed(feed_id):
    """Toggle feed active status"""
    feed = Feed.query.get_or_404(feed_id)
    feed.active = not feed.active
    db.session.commit()
    
    status = 'activated' if feed.active else 'deactivated'
    flash(f'Feed {feed.name} {status}', 'success')
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/feeds/<int:feed_id>/delete', methods=['POST'])
def delete_feed(feed_id):
    """Delete a feed"""
    feed = Feed.query.get_or_404(feed_id)
    name = feed.name
    db.session.delete(feed)
    db.session.commit()
    
    flash(f'Feed {name} deleted', 'success')
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/feeds/<int:feed_id>/check', methods=['POST'])
def check_feed_now(feed_id):
    """Check a feed immediately"""
    result = check_feed(feed_id)
    
    if result:
        flash('Feed checked successfully', 'success')
    else:
        flash('Error checking feed', 'error')
    
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/feeds/check_all', methods=['POST'])
def check_all_feeds():
    """Check all active feeds immediately"""
    feeds = Feed.query.filter_by(active=True).all()
    success = 0
    
    for feed in feeds:
        if check_feed(feed.id):
            success += 1
    
    flash(f'Checked {success} out of {len(feeds)} feeds', 'success')
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/feeds/update_interval', methods=['POST'])
def update_interval():
    """Update feed check interval"""
    interval = request.form.get('check_interval', type=int)
    
    if not interval or interval < 5:
        flash('Interval must be at least 5 minutes', 'error')
        return redirect(url_for('feeds.feed_list'))
    
    # Update in database
    settings = Settings.query.first()
    settings.check_interval = interval
    db.session.commit()
    
    # Update scheduler if possible, but don't fail if it's not accessible
    try:
        # Import here to avoid circular imports
        from app.scheduler import init_scheduler, update_feed_check_interval
        
        # Try to initialize scheduler if it's not already running
        scheduler = init_scheduler(current_app._get_current_object())
        
        if scheduler:
            # Update the interval
            success = update_feed_check_interval(interval)
            if success:
                current_app.logger.info(f"Updated scheduler feed check interval to {interval} minutes")
            else:
                current_app.logger.warning(f"Failed to update scheduler interval, but database was updated")
        else:
            current_app.logger.warning(f"Scheduler could not be initialized, interval updated in database only")
    except Exception as e:
        current_app.logger.error(f"Error updating scheduler interval: {str(e)}")
    
    flash(f'Check interval updated to {interval} minutes', 'success')
    return redirect(url_for('feeds.feed_list'))

@feeds.route('/articles')
def article_list():
    """List all articles with optional filtering"""
    # Get filter parameters
    feed_id = request.args.get('feed_id', '')
    processed = request.args.get('processed', '')
    sent_to_joplin = request.args.get('sent_to_joplin', '')
    date_filter = request.args.get('date_filter', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    tag_id = request.args.get('tag_id', '')
    
    # Start with all articles
    query = Article.query
    
    # Apply filters
    if feed_id:
        query = query.filter(Article.feed_id == feed_id)
    
    if processed == 'yes':
        query = query.filter(Article.processed == True)
    elif processed == 'no':
        query = query.filter(Article.processed == False)
    
    if sent_to_joplin == 'yes':
        query = query.filter(Article.sent_to_joplin == True)
    elif sent_to_joplin == 'no':
        query = query.filter(Article.sent_to_joplin == False)
        
    # Filter by tag if specified
    if tag_id:
        query = query.filter(Article.tags.any(Tag.id == tag_id))
    
    # Apply date filters
    now = datetime.utcnow()
    if date_filter == '12h':
        time_threshold = now - timedelta(hours=12)
        query = query.filter(Article.published >= time_threshold)
    elif date_filter == '24h':
        time_threshold = now - timedelta(hours=24)
        query = query.filter(Article.published >= time_threshold)
    elif date_filter == '72h':
        time_threshold = now - timedelta(hours=72)
        query = query.filter(Article.published >= time_threshold)
    elif date_filter == '1w':
        time_threshold = now - timedelta(weeks=1)
        query = query.filter(Article.published >= time_threshold)
    elif date_filter == '1m':
        time_threshold = now - timedelta(days=30)  # Approximation for a month
        query = query.filter(Article.published >= time_threshold)
    elif date_filter == 'custom' and start_date:
        # Parse start_date string to datetime
        try:
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Article.published >= start_datetime)
            
            if end_date:
                # Parse end_date string to datetime and set to end of day
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                query = query.filter(Article.published <= end_datetime)
        except ValueError:
            # Handle invalid date format
            current_app.logger.error(f"Invalid date format: {start_date} or {end_date}")
    
    # Order by published date descending (newest first)
    articles = query.order_by(Article.published.desc()).all()
    
    # Get all feeds for the filter dropdown
    feeds = Feed.query.all()
    
    # Get all tags with article counts
    tags = []
    for tag in Tag.query.all():
        # Count articles with this tag
        tag.article_count = Article.query.filter(Article.tags.any(Tag.id == tag.id)).count()
        tags.append(tag)
    
    # Render template with articles and filter values
    return render_template(
        'articles.html',
        articles=articles,
        feeds=feeds,
        tags=tags,
        current_feed_id=int(feed_id) if feed_id.isdigit() else None,
        current_tag_id=int(tag_id) if tag_id.isdigit() else None,
        processed=processed,
        sent_to_joplin=sent_to_joplin,
        date_filter=date_filter,
        start_date=start_date,
        end_date=end_date
    )

@feeds.route('/article/<int:article_id>')
def article_detail(article_id):
    """View article details"""
    article = Article.query.get_or_404(article_id)
    
    # Parse summary JSON if available
    summary_data = None
    if article.summary:
        try:
            summary_data = json.loads(article.summary)
            # If article was filtered out, we still want to show that in the UI
            if summary_data.get('filtered_out', False):
                current_app.logger.info(f"Article {article_id} was filtered out by GPT-3.5")
        except json.JSONDecodeError:
            summary_data = None
    
    return render_template('article_detail.html', article=article, summary_data=summary_data)

@feeds.route('/articles/<int:article_id>/process', methods=['POST'])
def process_article_now(article_id):
    """Process an article immediately"""
    result = process_article(article_id)
    
    if result:
        flash('Article processed successfully', 'success')
    else:
        flash('Error processing article', 'error')
    
    return redirect(url_for('feeds.article_detail', article_id=article_id))

@feeds.route('/articles/process_pending', methods=['POST'])
def process_pending():
    """Process all pending articles"""
    articles = Article.query.filter_by(processed=False).all()
    success = 0
    
    for article in articles:
        if process_article(article.id):
            success += 1
    
    flash(f'Processed {success} out of {len(articles)} articles', 'success')
    return redirect(url_for('feeds.article_list'))
