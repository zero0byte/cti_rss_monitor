from app import db
from app.models import Settings
from alembic import op
import sqlalchemy as sa

def upgrade():
    """Add max_article_age column to Settings table"""
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('max_article_age', sa.Integer(), nullable=False, server_default='0'))
    
    # Set default value for existing settings
    settings = Settings.query.all()
    for setting in settings:
        setting.max_article_age = 0  # Default to no limit
    db.session.commit()

def downgrade():
    """Remove max_article_age column from Settings table"""
    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('max_article_age')
