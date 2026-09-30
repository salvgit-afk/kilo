"""email verification codes and password reset

Revision ID: c4f9a1d7e2b6
Revises: b3e8f2a6d9c1
Create Date: 2026-09-30

Una tabella per i codici e due colonne sugli account. Gli account che
esistono già contano come verificati: sono stati creati prima della verifica
e chi li usa ci entra da tempo.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4f9a1d7e2b6'
down_revision: Union[str, None] = 'b3e8f2a6d9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('purpose', sa.String(length=16), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', 'purpose', name='uq_email_code'),
    )
    op.create_index(op.f('ix_email_codes_email'), 'email_codes', ['email'], unique=False)
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('password_changed_at')
        batch.drop_column('email_verified_at')
    op.drop_index(op.f('ix_email_codes_email'), table_name='email_codes')
    op.drop_table('email_codes')
