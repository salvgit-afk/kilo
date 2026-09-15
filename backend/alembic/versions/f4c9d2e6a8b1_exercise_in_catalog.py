"""exercises no longer provided by their source leave the catalog

Revision ID: f4c9d2e6a8b1
Revises: e3b8f5a1c7d2
Create Date: 2026-09-15

Solo aggiunte: `in_catalog` parte vero per tutti. La sincronizzazione lo spegne
per le voci che la fonte non fornisce più o che le regole di import escludono,
senza cancellarle (schede e preferenze possono usarle).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f4c9d2e6a8b1'
down_revision: Union[str, None] = 'e3b8f5a1c7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column('in_catalog', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('exercises', 'in_catalog')
