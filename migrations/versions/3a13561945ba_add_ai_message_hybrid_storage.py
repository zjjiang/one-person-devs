"""add_ai_message_hybrid_storage

Revision ID: 3a13561945ba
Revises: b678a76002a8
Create Date: 2026-02-28 11:49:03.195938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a13561945ba'
down_revision: Union[str, Sequence[str], None] = 'b678a76002a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns for hybrid storage
    op.add_column('ai_messages', sa.Column(
        'storage_type', sa.String(20), nullable=False, server_default='inline'
    ))
    op.add_column('ai_messages', sa.Column(
        'content_compressed', sa.LargeBinary, nullable=True
    ))
    op.add_column('ai_messages', sa.Column(
        'content_file_path', sa.String(500), nullable=True
    ))
    op.add_column('ai_messages', sa.Column(
        'content_size', sa.Integer, nullable=False, server_default='0'
    ))

    # Create index on storage_type for query optimization
    op.create_index(
        'ix_ai_messages_storage_type', 'ai_messages', ['storage_type']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ai_messages_storage_type', table_name='ai_messages')
    op.drop_column('ai_messages', 'content_size')
    op.drop_column('ai_messages', 'content_file_path')
    op.drop_column('ai_messages', 'content_compressed')
    op.drop_column('ai_messages', 'storage_type')
