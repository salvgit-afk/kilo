"""workout session start and end time

Revision ID: a7d9e2b4c6f8
Revises: f6c8d4a1b3e5
Create Date: 2026-09-21

Solo aggiunte: due colonne nullable. Le sessioni registrate prima restano
senza orari (durata non nota).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d9e2b4c6f8'
down_revision: Union[str, None] = 'f6c8d4a1b3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workout_sessions', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('workout_sessions', sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('workout_sessions', 'ended_at')
    op.drop_column('workout_sessions', 'started_at')
