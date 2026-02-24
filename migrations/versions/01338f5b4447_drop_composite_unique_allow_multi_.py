"""drop_composite_unique_allow_multi_instance

Revision ID: 01338f5b4447
Revises: 168dc8724efe
Create Date: 2026-02-24 09:49:00.425708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01338f5b4447'
down_revision: Union[str, Sequence[str], None] = '168dc8724efe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop composite unique constraint to allow multiple instances of same provider."""
    op.drop_constraint("uq_cap_provider", "global_capability_configs", type_="unique")


def downgrade() -> None:
    """Restore composite unique constraint."""
    op.create_unique_constraint(
        "uq_cap_provider", "global_capability_configs", ["capability", "provider"],
    )
