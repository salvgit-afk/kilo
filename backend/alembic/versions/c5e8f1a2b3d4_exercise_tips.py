"""exercise tips (everkinetic) and their italian translation

Revision ID: c5e8f1a2b3d4
Revises: a91c3e5d2b40
Create Date: 2026-09-13

Solo aggiunte.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e8f1a2b3d4'
down_revision: Union[str, None] = 'a91c3e5d2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exercises', sa.Column('tips', sa.JSON(), nullable=True))
    op.add_column('exercises', sa.Column('tips_it', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('exercises', 'tips_it')
    op.drop_column('exercises', 'tips')
