"""daily usage counters for costly endpoints (chat, LLM translations)

Revision ID: c8f3a1d5e7b2
Revises: b7e2f9a4c1d3
Create Date: 2026-09-17

Solo aggiunte: una tabella nuova.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8f3a1d5e7b2'
down_revision: Union[str, None] = 'b7e2f9a4c1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'day', 'kind', name='uq_api_usage_day'),
    )
    op.create_index(op.f('ix_api_usage_user_id'), 'api_usage', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_usage_user_id'), table_name='api_usage')
    op.drop_table('api_usage')
