from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from app.models import Tag, Article
from app import db

tags = Blueprint('tags', __name__)

@tags.route('/tags', methods=['GET'])
def tag_list():
    """List all tags"""
    all_tags = Tag.query.order_by(Tag.name).all()
    return render_template('tags.html', tags=all_tags)

@tags.route('/tags/new', methods=['GET', 'POST'])
def create_tag():
    """Create a new tag"""
    if request.method == 'POST':
        name = request.form.get('name')
        color = request.form.get('color', '#6c757d')
        
        # Check if tag already exists
        existing_tag = Tag.query.filter_by(name=name).first()
        if existing_tag:
            flash(f'Tag "{name}" already exists!', 'danger')
            return redirect(url_for('tags.tag_list'))
        
        # Create new tag
        tag = Tag(name=name, color=color)
        db.session.add(tag)
        db.session.commit()
        
        flash(f'Tag "{name}" created successfully!', 'success')
        return redirect(url_for('tags.tag_list'))
    
    return render_template('tag_form.html', tag=None)

@tags.route('/tags/<int:tag_id>/edit', methods=['GET', 'POST'])
def edit_tag(tag_id):
    """Edit an existing tag"""
    tag = Tag.query.get_or_404(tag_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        color = request.form.get('color')
        
        # Check if another tag with the same name exists
        existing_tag = Tag.query.filter(Tag.name == name, Tag.id != tag_id).first()
        if existing_tag:
            flash(f'Another tag with name "{name}" already exists!', 'danger')
            return redirect(url_for('tags.edit_tag', tag_id=tag_id))
        
        tag.name = name
        tag.color = color
        db.session.commit()
        
        flash(f'Tag "{name}" updated successfully!', 'success')
        return redirect(url_for('tags.tag_list'))
    
    return render_template('tag_form.html', tag=tag)

@tags.route('/tags/<int:tag_id>/delete', methods=['POST'])
def delete_tag(tag_id):
    """Delete a tag"""
    tag = Tag.query.get_or_404(tag_id)
    name = tag.name
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Tag "{name}" deleted successfully!', 'success')
    return redirect(url_for('tags.tag_list'))

@tags.route('/api/tags', methods=['GET'])
def api_tags():
    """Return all tags as JSON for AJAX requests"""
    all_tags = Tag.query.order_by(Tag.name).all()
    return jsonify([{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in all_tags])

@tags.route('/api/articles/<int:article_id>/tags', methods=['POST'])
def update_article_tags(article_id):
    """Update tags for an article via AJAX"""
    article = Article.query.get_or_404(article_id)
    tag_ids = request.json.get('tag_ids', [])
    
    # Clear existing tags and add new ones
    article.tags = []
    for tag_id in tag_ids:
        tag = Tag.query.get(tag_id)
        if tag:
            article.tags.append(tag)
    
    db.session.commit()
    return jsonify({'status': 'success'})
