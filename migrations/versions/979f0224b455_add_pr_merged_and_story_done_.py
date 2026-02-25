"""add pr_merged and story_done notification types

Revision ID: 979f0224b455
Revises: 1484875bc0e5
Create Date: 2026-02-25 19:33:14.658008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '979f0224b455'
down_revision: Union[str, Sequence[str], None] = '1484875bc0e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE notifications MODIFY COLUMN type "
        "ENUM('stage_completed','stage_failed','pr_created','pr_merged','story_done') NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TABLE notifications MODIFY COLUMN type "
        "ENUM('stage_completed','stage_failed','pr_created') NOT NULL"
    )
