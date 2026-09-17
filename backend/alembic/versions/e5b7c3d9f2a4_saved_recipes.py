"""saved recipes per profile

Revision ID: e5b7c3d9f2a4
Revises: d9a4b2c6e8f1
Create Date: 2026-09-17

Solo aggiunte: una tabella nuova.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b7c3d9f2a4'
down_revision: Union[str, None] = 'd9a4b2c6e8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_recipes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'source', 'external_id', name='uq_saved_recipe'),
    )
    op.create_index(op.f('ix_saved_recipes_profile_id'), 'saved_recipes', ['profile_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_saved_recipes_profile_id'), table_name='saved_recipes')
    op.drop_table('saved_recipes')
