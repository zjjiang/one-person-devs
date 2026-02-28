"""add_performance_indexes

Revision ID: fb1f6833e072
Revises: 3a13561945ba
Create Date: 2026-02-28 17:56:55.905202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb1f6833e072'
down_revision: Union[str, Sequence[str], None] = '3a13561945ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add indexes for foreign keys and frequently queried columns
    op.create_index('ix_stories_project_id', 'stories', ['project_id'])
    op.create_index('ix_stories_status', 'stories', ['status'])
    op.create_index('ix_rounds_story_id', 'rounds', ['story_id'])
    op.create_index('ix_rounds_status', 'rounds', ['status'])
    op.create_index('ix_ai_messages_round_id', 'ai_messages', ['round_id'])
    op.create_index('ix_clarifications_story_id', 'clarifications', ['story_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_clarifications_story_id', table_name='clarifications')
    op.drop_index('ix_ai_messages_round_id', table_name='ai_messages')
    op.drop_index('ix_rounds_status', table_name='rounds')
    op.drop_index('ix_rounds_story_id', table_name='rounds')
    op.drop_index('ix_stories_status', table_name='stories')
    op.drop_index('ix_stories_project_id', table_name='stories')
