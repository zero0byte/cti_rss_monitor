from app import db
from app.models import Article
from alembic import op
import sqlalchemy as sa

def upgrade():
    """Add processing column and processing_started timestamp to Article table"""
    with op.batch_alter_table('article') as batch_op:
        batch_op.add_column(sa.Column('processing', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('processing_started', sa.DateTime(), nullable=True))
    
    # Reset any potentially stuck articles
    articles = Article.query.filter_by(processing=True).all()
    for article in articles:
        article.processing = False
        article.processing_started = None
    db.session.commit()

def downgrade():
    """Remove processing and processing_started columns from Article table"""
    with op.batch_alter_table('article') as batch_op:
        batch_op.drop_column('processing_started')
        batch_op.drop_column('processing')
