"""Verifica che ogni ingrediente delle Ricette Kilo trovi l'alimento giusto.

Cerca su USDA dal vivo, come fa l'app, ma su un database SQLite temporaneo:
non scrive niente nel database vero. Stampa per ogni alimento cosa è stato
abbinato con i suoi valori per 100 g, poi i macro per porzione di ogni
ricetta. Da rileggere a occhio prima di committare ricette nuove: un
"chicken breast" abbinato a un pollo impanato si vede subito dalle kcal.

    cd backend && .venv/bin/python scripts/check_kilo_recipes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.data import kilo_recipes  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import meal_suggestions, recipe_analyzer  # noqa: E402


def main() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    grezze = [meal_suggestions.kilo_raw_recipe(r) for r in kilo_recipes.RECIPES]
    recipe_analyzer.prefetch_recipe_data(db, grezze)

    visti: set[str] = set()
    print("ALIMENTI")
    for r in kilo_recipes.RECIPES:
        for i in r.ingredients:
            if i.en in visti:
                continue
            visti.add(i.en)
            ing = recipe_analyzer._match_ingredient(db, i.en)
            if ing is None:
                print(f"  !! {i.en:32} NON TROVATO")
            else:
                print(
                    f"  {i.en:32} -> {ing.name[:60]:60} "
                    f"{ing.kcal_100g or 0:5.0f} kcal  P{ing.protein_100g or 0:5.1f}  "
                    f"C{ing.carbs_100g or 0:5.1f}  G{ing.fat_100g or 0:5.1f}"
                )

    print("\nRICETTE (per porzione)")
    for r, grezza in zip(kilo_recipes.RECIPES, grezze):
        a = recipe_analyzer.analyze_recipe(db, grezza, servings=r.servings, use_llm=False)
        mancanti = ", ".join(a.unresolved_names) or "-"
        print(
            f"  {r.name[:48]:48} {a.kcal_per_serving:5.0f} kcal  P{a.protein_per_serving:5.1f}  "
            f"C{a.carbs_per_serving:5.1f}  G{a.fat_per_serving:5.1f}  mancanti: {mancanti}"
        )


if __name__ == "__main__":
    main()
