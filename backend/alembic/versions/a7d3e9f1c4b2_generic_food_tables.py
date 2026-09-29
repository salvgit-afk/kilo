"""alimenti generici CIQUAL e CREA

Revision ID: a7d3e9f1c4b2
Revises: c9f4a2b8e1d7
Create Date: 2026-09-29

Aggiunge a `ingredients` la colonna `portion_g` (porzione tipica) e carica
gli alimenti di due tabelle di composizione:

- CIQUAL 2025 di Anses (source = "ciqual"), da `app/data/ciqual_2025.json`;
- CREA Alimenti e Nutrizione (source = "crea"), da `app/data/crea_2019.json`,
  con nome italiano e porzione.

Solo righe nuove: nessun dato esistente viene toccato. La migrazione non
importa i modelli dell'app, così resta valida anche se cambiano.
"""
import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d3e9f1c4b2'
down_revision: Union[str, None] = 'c9f4a2b8e1d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DATA_DIR = Path(__file__).resolve().parents[2] / "app" / "data"
FONTI = (("ciqual", "ciqual_2025.json"), ("crea", "crea_2019.json"))

ingredients = sa.table(
    "ingredients",
    sa.column("source", sa.String),
    sa.column("source_id", sa.String),
    sa.column("name", sa.String),
    sa.column("kcal_100g", sa.Float),
    sa.column("protein_100g", sa.Float),
    sa.column("carbs_100g", sa.Float),
    sa.column("fat_100g", sa.Float),
    sa.column("sugars_100g", sa.Float),
    sa.column("fiber_100g", sa.Float),
    sa.column("saturated_fat_100g", sa.Float),
    sa.column("portion_g", sa.Float),
)


def upgrade() -> None:
    op.add_column("ingredients", sa.Column("portion_g", sa.Float(), nullable=True))
    conn = op.get_bind()
    for fonte, file in FONTI:
        gia = {
            r[0]
            for r in conn.execute(
                sa.select(ingredients.c.source_id).where(ingredients.c.source == fonte)
            )
        }
        voci = json.loads((DATA_DIR / file).read_text(encoding="utf-8"))["alimenti"]
        righe = [
            {
                "source": fonte,
                "source_id": v["id"],
                "name": v["name"][:255],
                "kcal_100g": v["kcal"],
                "protein_100g": v["protein"],
                "carbs_100g": v["carbs"],
                "fat_100g": v["fat"],
                "sugars_100g": v.get("sugars"),
                "fiber_100g": v.get("fiber"),
                "saturated_fat_100g": v.get("saturated"),
                "portion_g": v.get("portion_g"),
            }
            for v in voci
            if v["id"] not in gia
        ]
        for i in range(0, len(righe), 500):
            op.bulk_insert(ingredients, righe[i : i + 500])


def downgrade() -> None:
    op.execute(ingredients.delete().where(ingredients.c.source.in_(["ciqual", "crea"])))
    op.drop_column("ingredients", "portion_g")
