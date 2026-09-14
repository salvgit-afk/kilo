"""exercise library (free-exercise-db), italian translations, llm cache

Revision ID: a91c3e5d2b40
Revises: fd5373cb67e4
Create Date: 2026-09-11

Solo aggiunte: nessuna colonna esistente viene modificata o rimossa, quindi
le schede e le preferenze già salvate restano valide.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a91c3e5d2b40'
down_revision: Union[str, None] = 'fd5373cb67e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exercises', sa.Column('source', sa.String(length=32), server_default='wger', nullable=False))
    op.add_column('exercises', sa.Column('external_id', sa.String(length=160), nullable=True))
    op.add_column('exercises', sa.Column('level', sa.String(length=32), nullable=True))
    op.add_column('exercises', sa.Column('priority', sa.Integer(), server_default='100', nullable=False))
    op.add_column('exercises', sa.Column('instructions', sa.JSON(), nullable=True))
    op.add_column('exercises', sa.Column('demo_images', sa.JSON(), nullable=True))
    op.add_column('exercises', sa.Column('name_it', sa.String(length=255), nullable=True))
    op.add_column('exercises', sa.Column('instructions_it', sa.JSON(), nullable=True))
    op.add_column('exercises', sa.Column('focus_it', sa.JSON(), nullable=True))
    op.create_index(op.f('ix_exercises_source'), 'exercises', ['source'], unique=False)
    op.create_index(op.f('ix_exercises_external_id'), 'exercises', ['external_id'], unique=False)
    op.create_index(op.f('ix_exercises_name_it'), 'exercises', ['name_it'], unique=False)

    op.create_table(
        'llm_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'key', name='uq_llm_cache_kind_key'),
    )


def downgrade() -> None:
    op.drop_table('llm_cache')
    op.drop_index(op.f('ix_exercises_name_it'), table_name='exercises')
    op.drop_index(op.f('ix_exercises_external_id'), table_name='exercises')
    op.drop_index(op.f('ix_exercises_source'), table_name='exercises')
    for colonna in ('focus_it', 'instructions_it', 'name_it', 'demo_images',
                    'instructions', 'priority', 'level', 'external_id', 'source'):
        op.drop_column('exercises', colonna)
