"""notification settings and log

Revision ID: c9f4a2b8e1d7
Revises: b8e3f1c5d7a9
Create Date: 2026-09-22

Due tabelle nuove: preferenze delle notifiche per account e registro di
quelle già mandate. Nessun dato esistente viene toccato.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9f4a2b8e1d7'
down_revision: Union[str, None] = 'b8e3f1c5d7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('training', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('supplements', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('diary', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('recipes', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('progress', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('meal_prep', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('gym_hour', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_notification_settings_user_id'), 'notification_settings', ['user_id'])
    op.create_table(
        'notification_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=160), nullable=False),
        sa.Column('sent_on', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_notification_key'),
    )
    op.create_index(op.f('ix_notification_log_user_id'), 'notification_log', ['user_id'])
    op.create_index(op.f('ix_notification_log_sent_on'), 'notification_log', ['sent_on'])
    # Quale promemoria è già partito ora lo dice notification_log, con una
    # chiave per evento: la data sull'iscrizione non serve più.
    op.drop_column('push_subscriptions', 'last_sent_on')


def downgrade() -> None:
    op.add_column('push_subscriptions', sa.Column('last_sent_on', sa.Date(), nullable=True))
    op.drop_index(op.f('ix_notification_log_sent_on'), table_name='notification_log')
    op.drop_index(op.f('ix_notification_log_user_id'), table_name='notification_log')
    op.drop_table('notification_log')
    op.drop_index(op.f('ix_notification_settings_user_id'), table_name='notification_settings')
    op.drop_table('notification_settings')
