"""add global_capability_configs table

Revision ID: b4e2c3d5f6a7
Revises: a3f1b2c4d5e6
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa

revision = "b4e2c3d5f6a7"
down_revision = "a3f1b2c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "global_capability_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("capability", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability"),
    )


def downgrade() -> None:
    op.drop_table("global_capability_configs")
