"""add_story_mode_and_briefing_status

Revision ID: 6313cd1546bf
Revises: ce6ab882dab7
Create Date: 2026-03-12 01:31:34.274519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6313cd1546bf'
down_revision: Union[str, Sequence[str], None] = 'ce6ab882dab7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add mode column to stories
    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode', sa.Enum('full', 'light', name='storymode'), server_default='full', nullable=False))

    # Add 'briefing' to StoryStatus enum
    op.execute("ALTER TABLE stories MODIFY COLUMN status ENUM('preparing','briefing','clarifying','planning','designing','coding','verifying','done') NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove 'briefing' from StoryStatus enum
    op.execute("ALTER TABLE stories MODIFY COLUMN status ENUM('preparing','clarifying','planning','designing','coding','verifying','done') NOT NULL")

    with op.batch_alter_table('stories', schema=None) as batch_op:
        batch_op.drop_column('mode')
