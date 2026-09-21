"""training weekdays per plan

Revision ID: f6c8d4a1b3e5
Revises: e5b7c3d9f2a4
Create Date: 2026-09-21

Solo aggiunte: una colonna nullable. Le schede esistenti restano senza
giorni salvati e ricevono la proposta di default per la loro frequenza.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6c8d4a1b3e5'
down_revision: Union[str, None] = 'e5b7c3d9f2a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workout_plans', sa.Column('training_weekdays', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('workout_plans', 'training_weekdays')
