"""add_workspace_lock_fields

Revision ID: b678a76002a8
Revises: 979f0224b455
Create Date: 2026-02-25 23:41:53.230096

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b678a76002a8'
down_revision: Union[str, Sequence[str], None] = '979f0224b455'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add workspace lock fields to projects table
    op.add_column('projects', sa.Column('locked_by_story_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('locked_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_project_locked_story', 'projects', 'stories',
        ['locked_by_story_id'], ['id'], ondelete='SET NULL'
    )

    # Add workspace lock holder flag to stories table
    op.add_column('stories', sa.Column('has_workspace_lock', sa.Boolean(),
                                       server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove workspace lock fields
    op.drop_constraint('fk_project_locked_story', 'projects', type_='foreignkey')
    op.drop_column('projects', 'locked_at')
    op.drop_column('projects', 'locked_by_story_id')
    op.drop_column('stories', 'has_workspace_lock')
