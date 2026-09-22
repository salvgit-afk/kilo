"""push subscriptions for reminders

Revision ID: b8e3f1c5d7a9
Revises: a7d9e2b4c6f8
Create Date: 2026-09-22

Solo una tabella nuova: nessun dato esistente viene toccato.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8e3f1c5d7a9'
down_revision: Union[str, None] = 'a7d9e2b4c6f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(length=1024), nullable=False),
        sa.Column('p256dh', sa.String(length=255), nullable=False),
        sa.Column('auth', sa.String(length=255), nullable=False),
        sa.Column('reminder_hour', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('last_sent_on', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
    )
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_push_subscriptions_user_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
