"""indice trigram per la ricerca degli alimenti

Revision ID: a3f7c2e9d1b4
Revises: e8c1f5a3b7d2
Create Date: 2026-10-12

La ricerca degli alimenti (CREA, Ciqual, prodotti salvati) cerca parole
dentro il nome: `name ILIKE '%riso%'`. Un indice normale non serve a questo,
e la tabella `ingredients` cresce a ogni ricerca USDA o Open Food Facts. Con
`pg_trgm` (estensione standard, disponibile su Neon gratuito) Postgres usa
un indice GIN anche per questi confronti.

Solo aggiunte, nessun dato toccato. Su SQLite (i test) non fa niente.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a3f7c2e9d1b4'
down_revision: Union[str, None] = 'e8c1f5a3b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_ingredients_name_trgm",
        "ingredients",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
        if_not_exists=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index("ix_ingredients_name_trgm", table_name="ingredients", if_exists=True)
