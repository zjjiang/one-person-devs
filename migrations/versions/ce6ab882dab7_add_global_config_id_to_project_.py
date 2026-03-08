"""add global_config_id to project_capability_configs

Revision ID: ce6ab882dab7
Revises: 2770394660a4
Create Date: 2026-03-08 23:14:54.189552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce6ab882dab7'
down_revision: Union[str, Sequence[str], None] = '2770394660a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('project_capability_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('global_config_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_pcc_global_config_id', 'global_capability_configs',
            ['global_config_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('project_capability_configs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pcc_global_config_id', type_='foreignkey')
        batch_op.drop_column('global_config_id')
