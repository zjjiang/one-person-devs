"""add workspace_status and workspace_error to projects

Revision ID: a3f1b2c4d5e6
Revises: 9a8cf012c8b8
Create Date: 2026-02-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1b2c4d5e6'
down_revision: Union[str, Sequence[str], None] = '9a8cf012c8b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    # Check which columns already exist (handle partial migration)
    result = conn.execute(sa.text("SHOW COLUMNS FROM projects LIKE 'workspace_status'"))
    if not result.fetchone():
        op.add_column(
            'projects',
            sa.Column(
                'workspace_status',
                sa.Enum('pending', 'cloning', 'ready', 'error', name='workspacestatus'),
                server_default='pending',
                nullable=False,
            ),
        )
    result = conn.execute(sa.text("SHOW COLUMNS FROM projects LIKE 'workspace_error'"))
    if not result.fetchone():
        op.add_column(
            'projects',
            sa.Column('workspace_error', sa.String(2000), server_default='', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('workspace_error')
        batch_op.drop_column('workspace_status')
    op.execute("DROP TYPE IF EXISTS workspacestatus")
