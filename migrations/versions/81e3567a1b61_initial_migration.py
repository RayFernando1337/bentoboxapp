"""initial migration

Revision ID: 81e3567a1b61
Revises: 
Create Date: 2025-02-04 23:14:26.285443

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator, TEXT
import json

class JSONType(TypeDecorator):
    """Enables JSON storage by encoding and decoding on the fly."""
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

# revision identifiers, used by Alembic.
revision = '81e3567a1b61'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('transcripts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('progress', sa.Float(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('word_count', sa.Integer(), nullable=True),
    sa.Column('duration', sa.Float(), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('segments', JSONType(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transcripts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_transcripts_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_transcripts_title'), ['title'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcripts_title'))
        batch_op.drop_index(batch_op.f('ix_transcripts_status'))
        batch_op.drop_index(batch_op.f('ix_transcripts_created_at'))

    op.drop_table('transcripts')
    # ### end Alembic commands ###
