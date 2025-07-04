import os
import json
import uuid
import logging
import feedparser
import requests
import psutil
import html2text
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
from app import db
from app.models import Feed, Article, Settings, Prompt, Tag, article_tags
import openai
import re
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# HTML to text converter
h2t = html2text.HTML2Text()
h2t.ignore_links = False
h2t.ignore_images = True
h2t.ignore_tables = False

def fetch_feed(feed_url):
    """Fetch and parse an RSS feed"""
    try:
        feed_data = feedparser.parse(feed_url)
        return feed_data
    except Exception as e:
        logger.error(f"Error fetching feed {feed_url}: {str(e)}")
        return None

def extract_content(url):
    """Extract the main content from a URL"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Try to find the main content
        main_content = None
        
        # Look for common content containers
        content_candidates = soup.select('article, .article, .post, .content, main, #content, #main')
        if content_candidates:
            main_content = content_candidates[0]
        else:
            # Fallback to body
            main_content = soup.body
        
        if main_content:
            # Convert to markdown
            text = h2t.handle(str(main_content))
            return text
        
        return None
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {str(e)}")
        return None

def regex_extract_iocs(text):
    """Extract IOCs using regex patterns"""
    md5 = re.findall(r"\b[a-fA-F0-9]{32}\b", text)
    sha1 = re.findall(r"\b[a-fA-F0-9]{40}\b", text)
    sha256 = re.findall(r"\b[a-fA-F0-9]{64}\b", text)
    ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    domains = re.findall(r"\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
    return {"md5": md5, "sha1": sha1, "sha256": sha256, "ips": ips, "domains": domains}

def call_openai(model, messages, api_key):
    """Call OpenAI API with the given model and messages"""
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {str(e)}")
        return None

def send_to_joplin(title, content, api_url, token):
    """Send content to Joplin via the Webclipper API"""
    try:
        url = api_url
        params = {"token": token}
        
        data = {
            "title": title,
            "body": content,
            "source_url": "",
            "tags": ["cti", "openai"]
        }
        
        response = requests.post(url, params=params, json=data)
        return response.json()
    except Exception as e:
        logger.error(f"Error sending to Joplin: {str(e)}")
        return None

def process_article(article_id, skip_processing_check=False):
    """Process an article with OpenAI and send to Joplin"""
    try:
        # Get the article with row locking to prevent concurrent processing
        article = Article.query.with_for_update().get(article_id)
        if not article:
            logger.error(f"Article {article_id} not found")
            return False
            
        # Check if article is already processed
        if article.processed:
            logger.warning(f"Article {article_id} (GUID: {article.guid}) has already been processed, skipping")
            # Make sure processing flag is reset
            article.processing = False
            db.session.commit()
            return True
            
        # Check if article is currently being processed by another process
        # Skip this check if skip_processing_check is True (when called from process_pending_articles)
        if not skip_processing_check and article.processing and not article.processed:
            # Check if the processing has been going on for too long (more than 5 minutes)
            # This prevents articles from getting stuck in processing state
            current_time = datetime.utcnow()
            processing_timeout = timedelta(minutes=5)
            
            if article.processing_started and (current_time - article.processing_started) > processing_timeout:
                logger.warning(f"Article {article_id} (GUID: {article.guid}) has been in processing state for too long. Resetting processing flag.")
                # Reset the processing flag to allow this process to handle it
                article.processing = False
                article.processing_started = None
                db.session.commit()
            else:
                logger.warning(f"Article {article_id} (GUID: {article.guid}) is currently being processed by another process, skipping")
                return True
            
        # Mark article as being processed and set the processing start time
        article.processing = True
        article.processing_started = datetime.utcnow()
        db.session.commit()
        
        # Get settings
        settings = Settings.query.first()
        if not settings or not settings.openai_api_key:
            logger.error("OpenAI API key not configured")
            return False
        
        # Get prompts
        filter_prompt = Prompt.query.filter_by(name='filter_prompt').first()
        parse_prompt = Prompt.query.filter_by(name='parse_prompt').first()
        
        if not filter_prompt or not parse_prompt:
            logger.error("Prompts not configured")
            return False
        
        # Extract content if not already done
        if not article.content:
            article.content = extract_content(article.url)
            db.session.commit()
        
        if not article.content:
            logger.error(f"Could not extract content from {article.url}")
            return False
        
        # Truncate content to limit token usage
        truncated_content = article.content[:3000]
        
        # FIRST STAGE: Determine if the article is worth keeping with GPT-3.5
        filter_messages = [
            {"role": "system", "content": "You are a CTI analyst assistant that determines if articles contain valuable threat intelligence."},
            {"role": "user", "content": f"Determine if this article contains valuable threat intelligence information such as new threats, vulnerabilities, TTPs, or IOCs. Respond with only 'KEEP' or 'DISCARD'. Article: {truncated_content}"}
        ]
        
        # Call the filter model (GPT-3.5)
        filter_result = call_openai(filter_prompt.model, filter_messages, settings.openai_api_key)
        if not filter_result:
            logger.error(f"Error calling OpenAI filter model for article {article_id}")
            return False
        
        # Check if the article should be kept
        if "KEEP" not in filter_result.upper():
            logger.info(f"Article {article_id} filtered out by GPT-3.5")
            article.processed = True
            article.summary = json.dumps({"summary": "Article filtered out - not relevant for CTI", "filtered_out": True})
            db.session.commit()
            return True  # We successfully processed it by deciding to filter it out
        
        # SECOND STAGE: Process the article in detail
        logger.info(f"Article {article_id} deemed relevant, processing with detailed analysis")
        
        # Extract IOCs using regex
        iocs_regex = regex_extract_iocs(article.content)
        
        # Prepare messages for detailed analysis
        parse_messages = [
            {"role": "system", "content": "You are a concise CTI analyst assistant."},
            {"role": "user", "content": f"{parse_prompt.content} Article: {truncated_content}"}
        ]
        
        # Call the more powerful model for detailed analysis
        result_parse = call_openai(parse_prompt.model, parse_messages, settings.openai_api_key)
        if not result_parse:
            logger.error(f"Error calling OpenAI parse model for article {article_id}")
            return False
        
        # Try to parse the result as JSON
        try:
            summary_data = json.loads(result_parse)
        except json.JSONDecodeError:
            summary_data = {"summary": result_parse, "tags": ["cti"], "iocs": iocs_regex}
        
        # Ensure IOCs are included
        if "iocs" not in summary_data:
            summary_data["iocs"] = iocs_regex
        
        # Add the title
        summary_data["title"] = article.title
        summary_data["filtered_out"] = False
        
        # Save summary to article
        article.summary = json.dumps(summary_data)
        article.processed = True
        db.session.commit()
        
        # Format the content for Joplin
        joplin_content = f"# {summary_data['title']}\n\n"
        
        # Add publication date and link near the top
        if article.published:
            formatted_date = article.published.strftime('%Y-%m-%d %H:%M UTC')
            joplin_content += f"*Published on: {formatted_date}*  \n"
        joplin_content += f"*Source: [{article.url.split('/')[2]}]({article.url})*\n\n"
        
        joplin_content += f"## Summary\n{summary_data.get('summary', 'No summary available')}\n\n"
        joplin_content += f"## Source Details\n[Original Article]({article.url})\n\n"
        
        joplin_content += "## IOCs\n"
        for k, v in summary_data['iocs'].items():
            if v:  # Only add if there are values
                joplin_content += f"- {k.upper()}: {', '.join(v)}\n"
        
        if summary_data.get("ttp"):
            joplin_content += f"\n## TTPs\n- {' '.join(summary_data['ttp'])}\n"
        
        if summary_data.get("threat_groups"):
            joplin_content += f"\n## Threat Groups\n- {' '.join(summary_data['threat_groups'])}\n"
        
        # Send to Joplin if enabled and configured
        if settings.joplin_enabled and settings.joplin_api_url and settings.joplin_token:
            logger.info(f"Sending article {article_id} to Joplin")
            joplin_response = send_to_joplin(
                summary_data["title"], 
                joplin_content, 
                settings.joplin_api_url, 
                settings.joplin_token
            )
            
            if joplin_response:
                article.sent_to_joplin = True
                if 'id' in joplin_response:
                    article.joplin_id = joplin_response['id']
                db.session.commit()
                logger.info(f"Successfully sent article {article_id} to Joplin")
        else:
            if not settings.joplin_enabled:
                logger.info(f"Joplin integration disabled, skipping send for article {article_id}")
            else:
                logger.info(f"Joplin API URL or token not configured, skipping send for article {article_id}")
        
        # Mark as processed and reset processing flag
        article.processed = True
        article.processing = False
        db.session.commit()
        
        return True
    except Exception as e:
        logger.error(f"Error processing article {article_id}: {str(e)}")
        # Reset processing flag on error
        try:
            article = Article.query.get(article_id)
            if article:
                article.processing = False
                db.session.commit()
        except Exception as inner_e:
            logger.error(f"Error resetting processing flag for article {article_id}: {str(inner_e)}")
        return False

def check_feed(feed_id):
    """Check a feed for new articles"""
    try:
        # Get the feed
        feed = Feed.query.get(feed_id)
        if not feed:
            logger.error(f"Feed {feed_id} not found")
            return False
        
        # Fetch the feed
        feed_data = fetch_feed(feed.url)
        if not feed_data:
            logger.error(f"Could not fetch feed {feed.url}")
            return False
        
        # Update last checked time
        feed.last_checked = datetime.utcnow()
        db.session.commit()
        
        # Process entries
        new_articles = 0
        for entry in feed_data.entries:
            # Generate a stable GUID based on the article URL and title
            article_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{entry.link}|{entry.title}"))
            
            # Check if article already exists by GUID, URL, or title
            existing = Article.query.filter(
                (Article.guid == article_guid) |
                (Article.url == entry.link) | 
                (Article.title == entry.title)
            ).first()
            if existing:
                logger.debug(f"Skipping duplicate article: {entry.title} (GUID: {article_guid})")
                continue
            
            # Parse published date
            published = None
            if hasattr(entry, 'published'):
                try:
                    published = date_parser.parse(entry.published)
                except:
                    pass
            
            # Create new article with the generated GUID
            article = Article(
                guid=article_guid,
                title=entry.title,
                url=entry.link,
                published=published,
                feed_id=feed.id
            )
            
            # Extract content if available in the feed
            if hasattr(entry, 'content'):
                article.content = entry.content[0].value
            elif hasattr(entry, 'summary'):
                article.content = entry.summary
            
            db.session.add(article)
            new_articles += 1
        
        db.session.commit()
        logger.info(f"Added {new_articles} new articles from feed {feed.name}")
        return True
    except Exception as e:
        logger.error(f"Error checking feed {feed_id}: {str(e)}")
        return False

def check_all_feeds():
    """Check all active feeds for new articles"""
    feeds = Feed.query.filter_by(active=True).all()
    logger.info(f"Found {len(feeds)} active feeds to check")
    
    if not feeds:
        logger.warning("No active feeds found to check")
        return False
        
    results = []
    for feed in feeds:
        logger.info(f"Checking feed {feed.id}: {feed.name}")
        result = check_feed(feed.id)
        results.append(result)
        
    success_count = results.count(True)
    logger.info(f"Completed checking {len(feeds)} feeds. {success_count} succeeded, {len(feeds) - success_count} failed")
    return any(results)  # Return True if at least one feed check succeeded

def process_pending_articles():
    """Process all unprocessed articles"""
    # Create a set to track processed GUIDs in this session
    processed_guids = set()
    
    # Get max article age setting
    settings = Settings.query.first()
    max_article_age = settings.max_article_age if settings else 0
    
    try:
        # First, get all previously processed GUIDs without locking
        processed_articles = Article.query.filter_by(processed=True).all()
        for processed_article in processed_articles:
            processed_guids.add(processed_article.guid)
        
        logger.info(f"Found {len(processed_guids)} previously processed article GUIDs")
        
        # Get all unprocessed articles with row locking to prevent concurrent processing
        articles = Article.query.filter_by(processed=False).with_for_update().all()
        logger.info(f"Found {len(articles)} unprocessed articles")
        
        if not articles:
            logger.info("No pending articles to process")
            return True  # Not an error if there's nothing to process
        
        # Mark all articles as being processed to prevent other processes from picking them up
        current_time = datetime.utcnow()
        for article in articles:
            article.processing = True
            article.processing_started = current_time
        
        # Commit the processing flag changes
        db.session.commit()
        
        # Filter out any duplicate articles based on GUID and respect max_article_age setting
        unique_articles = []
        duplicate_count = 0
        skipped_age_count = 0
        current_time = datetime.utcnow()
        
        for article in articles:
            # Skip if article is a duplicate
            if article.guid in processed_guids:
                duplicate_count += 1
                logger.warning(f"Skipping duplicate article with GUID {article.guid}: {article.title}")
                article.processed = True
                continue
                
            # Skip if article is too old (when max_article_age > 0)
            if max_article_age > 0 and article.published:
                article_age_days = (current_time - article.published).days
                if article_age_days > max_article_age:
                    skipped_age_count += 1
                    logger.info(f"Skipping article {article.id} due to age: {article_age_days} days old (max: {max_article_age} days): {article.title}")
                    article.processed = True
                    continue
            
            # Article passed all filters, add it to processing list
            unique_articles.append(article)
            processed_guids.add(article.guid)
        
        # Commit any changes to mark duplicates and age-filtered articles as processed
        if duplicate_count > 0 or skipped_age_count > 0:
            db.session.commit()
            if duplicate_count > 0:
                logger.info(f"Marked {duplicate_count} duplicate articles as processed")
            if skipped_age_count > 0:
                logger.info(f"Marked {skipped_age_count} articles as processed due to age limit ({max_article_age} days)")
        
        logger.info(f"Processing {len(unique_articles)} unique articles after filtering duplicates")
        
        results = []
        for article in unique_articles:
            logger.info(f"Processing article {article.id} (GUID: {article.guid}): {article.title}")
            result = process_article(article.id, skip_processing_check=True)
            results.append(result)
        
        success_count = results.count(True)
        logger.info(f"Completed processing {len(unique_articles)} articles. {success_count} succeeded, {len(unique_articles) - success_count} failed")
        return any(results)  # Return True if at least one article was processed successfully
    except Exception as e:
        logger.error(f"Error during article processing: {str(e)}")
        # Make sure to roll back any pending changes if there's an error
        db.session.rollback()
        return False
