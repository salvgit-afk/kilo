"""exercise duplicates across catalogs

Revision ID: e3b8f5a1c7d2
Revises: d7a2c9e41f60
Create Date: 2026-09-15

Solo aggiunte: `duplicate_of_id` indica l'esercizio che rappresenta lo stesso
movimento in un'altra fonte. Gli esercizi con il campo valorizzato restano nel
database (schede e preferenze li referenziano) ma escono dal catalogo.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e3b8f5a1c7d2'
down_revision: Union[str, None] = 'd7a2c9e41f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exercises', sa.Column('duplicate_of_id', sa.Integer(), nullable=True))
    op.create_index('ix_exercises_duplicate_of_id', 'exercises', ['duplicate_of_id'])
    op.create_foreign_key(
        'fk_exercises_duplicate_of_id', 'exercises', 'exercises',
        ['duplicate_of_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_exercises_duplicate_of_id', 'exercises', type_='foreignkey')
    op.drop_index('ix_exercises_duplicate_of_id', table_name='exercises')
    op.drop_column('exercises', 'duplicate_of_id')
