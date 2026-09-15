"""split type on workout plans (more active plans at once)

Revision ID: d7a2c9e41f60
Revises: c5e8f1a2b3d4
Create Date: 2026-09-15

Solo aggiunte: le schede esistenti restano senza split (l'interfaccia usa il
nome).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7a2c9e41f60'
down_revision: Union[str, None] = 'c5e8f1a2b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workout_plans', sa.Column('split_type', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('workout_plans', 'split_type')
