"""add_active_round_id_to_stories

Revision ID: 2770394660a4
Revises: fb1f6833e072
Create Date: 2026-02-28 17:58:57.195441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2770394660a4'
down_revision: Union[str, Sequence[str], None] = 'fb1f6833e072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add active_round_id column
    op.add_column('stories', sa.Column('active_round_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_stories_active_round_id', 'stories', 'rounds',
        ['active_round_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index('ix_stories_active_round_id', 'stories', ['active_round_id'])

    # Populate active_round_id for existing stories
    op.execute("""
        UPDATE stories s
        JOIN rounds r ON r.story_id = s.id AND r.status = 'active'
        SET s.active_round_id = r.id
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_stories_active_round_id', table_name='stories')
    op.drop_constraint('fk_stories_active_round_id', 'stories', type_='foreignkey')
    op.drop_column('stories', 'active_round_id')
