"""dismissed agent notes (Kilo's proactive notes closed by the user)

Revision ID: b7e2f9a4c1d3
Revises: a6d1e8f3b2c9
Create Date: 2026-09-17

Solo aggiunte: una tabella nuova.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e2f9a4c1d3'
down_revision: Union[str, None] = 'a6d1e8f3b2c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_note_dismissals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('note_key', sa.String(length=160), nullable=False),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'note_key', name='uq_agent_note_dismissal'),
    )
    op.create_index(op.f('ix_agent_note_dismissals_profile_id'), 'agent_note_dismissals', ['profile_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_note_dismissals_profile_id'), table_name='agent_note_dismissals')
    op.drop_table('agent_note_dismissals')
