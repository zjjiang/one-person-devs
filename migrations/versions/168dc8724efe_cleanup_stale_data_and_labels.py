"""cleanup_stale_data_and_labels

Revision ID: 168dc8724efe
Revises: 9b7ecc1b0933
Create Date: 2026-02-24 09:37:12.339511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '168dc8724efe'
down_revision: Union[str, Sequence[str], None] = '9b7ecc1b0933'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Clean up stale data from pre-composite-key era."""
    # Delete rows with empty provider (stale data from before composite key migration)
    op.execute("DELETE FROM global_capability_configs WHERE provider = ''")
    # Clear old labels that are just capability names (not user-customized)
    op.execute("UPDATE global_capability_configs SET label = NULL")


def downgrade() -> None:
    """No-op: data cleanup is not reversible."""
    pass
