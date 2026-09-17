"""barcode and owner on ingredients (scan with Open Food Facts, manual products)

Revision ID: d9a4b2c6e8f1
Revises: c8f3a1d5e7b2
Create Date: 2026-09-17

Solo aggiunte: due colonne facoltative.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd9a4b2c6e8f1'
down_revision: Union[str, None] = 'c8f3a1d5e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ingredients', sa.Column('barcode', sa.String(length=32), nullable=True))
    op.add_column('ingredients', sa.Column('created_by_user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_ingredients_barcode'), 'ingredients', ['barcode'], unique=False)
    op.create_index(op.f('ix_ingredients_created_by_user_id'), 'ingredients', ['created_by_user_id'], unique=False)
    op.create_foreign_key(
        'fk_ingredients_created_by_user_id', 'ingredients', 'users',
        ['created_by_user_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_ingredients_created_by_user_id', 'ingredients', type_='foreignkey')
    op.drop_index(op.f('ix_ingredients_created_by_user_id'), table_name='ingredients')
    op.drop_index(op.f('ix_ingredients_barcode'), table_name='ingredients')
    op.drop_column('ingredients', 'created_by_user_id')
    op.drop_column('ingredients', 'barcode')
