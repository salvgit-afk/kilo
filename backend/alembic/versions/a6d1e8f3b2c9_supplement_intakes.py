"""daily supplement intakes (diary of doses taken)

Revision ID: a6d1e8f3b2c9
Revises: f4c9d2e6a8b1
Create Date: 2026-09-17

Solo aggiunte: una tabella nuova, nessun dato esistente toccato.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a6d1e8f3b2c9'
down_revision: Union[str, None] = 'f4c9d2e6a8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'supplement_intakes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplement_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('doses', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['supplement_id'], ['supplement_declarations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplement_id', 'date', name='uq_supplement_intake_day'),
    )
    op.create_index(op.f('ix_supplement_intakes_supplement_id'), 'supplement_intakes', ['supplement_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_supplement_intakes_supplement_id'), table_name='supplement_intakes')
    op.drop_table('supplement_intakes')
