"""saved foods ("I miei prodotti")

Revision ID: b3e8f2a6d9c1
Revises: a7d3e9f1c4b2
Create Date: 2026-09-29

Una tabella nuova, riempita con i prodotti già segnati: chi ha scansionato
qualcosa prima di questa versione lo ritrova subito in lista.
"""
import datetime as dt
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3e8f2a6d9c1'
down_revision: Union[str, None] = 'a7d3e9f1c4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_foods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('ingredient_id', sa.Integer(), nullable=False),
        sa.Column('starred', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_grams', sa.Float(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'ingredient_id', name='uq_saved_food'),
    )
    op.create_index(op.f('ix_saved_foods_profile_id'), 'saved_foods', ['profile_id'], unique=False)

    # Prodotti con codice a barre o copiati dall'etichetta già nel diario:
    # quante volte, l'ultima quantità e quando.
    conn = op.get_bind()
    righe = conn.execute(
        sa.text(
            """
            SELECT m.profile_id, i.ingredient_id, i.quantity_g, m.date
            FROM meal_items i
            JOIN meal_logs m ON m.id = i.meal_log_id
            JOIN ingredients g ON g.id = i.ingredient_id
            WHERE m.is_planned = :falso
              AND (g.barcode IS NOT NULL OR g.source = 'manual')
            ORDER BY m.date, i.id
            """
        ),
        {"falso": False},
    ).all()
    raccolta: dict[tuple[int, int], dict] = {}
    for profilo, ingrediente, grammi, giorno in righe:
        voce = raccolta.setdefault((profilo, ingrediente), {"uses": 0})
        voce["uses"] += 1
        voce["last_grams"] = grammi
        voce["giorno"] = giorno
    if raccolta:
        tabella = sa.table(
            'saved_foods',
            sa.column('profile_id', sa.Integer),
            sa.column('ingredient_id', sa.Integer),
            sa.column('starred', sa.Boolean),
            sa.column('uses', sa.Integer),
            sa.column('last_grams', sa.Float),
            sa.column('last_used_at', sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            tabella,
            [
                {
                    "profile_id": profilo,
                    "ingredient_id": ingrediente,
                    "starred": True,
                    "uses": v["uses"],
                    "last_grams": v["last_grams"],
                    "last_used_at": dt.datetime.combine(
                        v["giorno"] if isinstance(v["giorno"], dt.date) else dt.date.fromisoformat(str(v["giorno"])),
                        dt.time(12),
                        tzinfo=dt.timezone.utc,
                    ),
                }
                for (profilo, ingrediente), v in raccolta.items()
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_saved_foods_profile_id'), table_name='saved_foods')
    op.drop_table('saved_foods')
