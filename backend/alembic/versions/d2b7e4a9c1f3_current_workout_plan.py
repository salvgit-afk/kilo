"""current workout plan

Revision ID: d2b7e4a9c1f3
Revises: c4f9a1d7e2b6
Create Date: 2026-10-07

Con più schede attive, quale è in uso: la sceglie l'utente nel menu della
Scheda e da lì vengono i giorni di allenamento di promemoria e notifiche.
Solo un'aggiunta: le schede esistenti partono tutte non scelte, e finché non
se ne sceglie una vale la più recente, come prima.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2b7e4a9c1f3'
down_revision: Union[str, None] = 'c4f9a1d7e2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workout_plans',
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('workout_plans', 'is_current')
