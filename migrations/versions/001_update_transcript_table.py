"""update transcript table

Revision ID: 001
Revises: 
Create Date: 2025-02-05 02:11:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create a temporary table with the new schema
    op.create_table(
        'transcript_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('segments', JSON, nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Copy data from old table to new table
    op.execute("""
        INSERT INTO transcript_new (
            id, title, content, word_count, duration, 
            created_at, updated_at, status, error_message
        )
        SELECT 
            id, filename, content, word_count, duration,
            created_at, updated_at, status, error_message
        FROM transcript;
    """)
    
    # Drop old table
    op.drop_table('transcript')
    
    # Rename new table to original name
    op.rename_table('transcript_new', 'transcript')


def downgrade():
    # Create old table structure
    op.create_table(
        'transcript_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Copy data back
    op.execute("""
        INSERT INTO transcript_old (
            id, filename, original_filename, content, word_count,
            duration, created_at, updated_at, status, error_message
        )
        SELECT 
            id, title, title, content, word_count,
            duration, created_at, updated_at, status, error_message
        FROM transcript;
    """)
    
    # Drop new table
    op.drop_table('transcript')
    
    # Rename old table to original name
    op.rename_table('transcript_old', 'transcript')
