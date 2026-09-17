"""Target nutrizionali, diario alimentare e suggerimenti di ricette.

Le due funzionalità hanno precisione diversa, e l'API lo rende esplicito:

  - il **diario** è un conteggio: l'utente sceglie l'alimento dalla ricerca e
    ne indica i grammi, quindi non resta nulla da stimare;
  - i **suggerimenti di ricette** portano una stima nutrizionale, con la
    copertura degli ingredienti dichiarata in risposta.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ingredient, IngredientSource, MealItem, MealLog, User, UserProfile
from app.routers.auth import current_user
from app.routers.profile import ensure_owner, owned_profile
from app.schemas import (
    BarcodeFoodOut,
    DiaryOut,
    FoodNamesIn,
    FoodSearchOut,
    GapFoodOut,
    GapSuggestionsOut,
    ManualProductIn,
    MealItemIn,
    MealItemOut,
    MealOut,
    NutritionTargetsOut,
    RecipeSuggestionOut,
)
from app.services import (
    food_diary,
    gap_filler,
    meal_suggestions,
    nutrition_targets,
    off_client,
    rate_limit,
    supplements,
    translation,
)

router = APIRouter(
    prefix="/nutrition", tags=["nutrizione"], dependencies=[Depends(current_user)]
)

# Cucine di TheMealDB (campo `strArea`), in italiano.
AREA_IT = {
    "American": "Americana", "British": "Britannica", "Canadian": "Canadese",
    "Chinese": "Cinese", "Croatian": "Croata", "Dutch": "Olandese",
    "Egyptian": "Egiziana", "Filipino": "Filippina", "French": "Francese",
    "Greek": "Greca", "Indian": "Indiana", "Irish": "Irlandese",
    "Italian": "Italiana", "Jamaican": "Giamaicana", "Japanese": "Giapponese",
    "Kenyan": "Keniota", "Malaysian": "Malese", "Mexican": "Messicana",
    "Moroccan": "Marocchina", "Polish": "Polacca", "Portuguese": "Portoghese",
    "Russian": "Russa", "Spanish": "Spagnola", "Thai": "Thailandese",
    "Tunisian": "Tunisina", "Turkish": "Turca", "Ukrainian": "Ucraina",
    "Vietnamese": "Vietnamita", "Unknown": None,
    # Alcune ricette usano il nome del paese invece dell'aggettivo.
    "France": "Francese", "India": "Indiana", "Italy": "Italiana", "Spain": "Spagnola",
    "Mexico": "Messicana", "Japan": "Giapponese", "China": "Cinese", "Greece": "Greca",
    "Thailand": "Thailandese", "Morocco": "Marocchina", "Turkey": "Turca",
    "Vietnam": "Vietnamita", "Australian": "Australiana", "Brazilian": "Brasiliana",
    "German": "Tedesca", "Argentine": "Argentina", "Lebanese": "Libanese",
    "Peruvian": "Peruviana", "Algerian": "Algerina", "Syrian": "Siriana",
    "Saudi Arabian": "Saudita", "Norwegian": "Norvegese", "Slovak": "Slovacca",
    "Uruguayan": "Uruguaiana", "Venezuelan": "Venezuelana",
}


def _area_it(originale: str | None, tradotta: str | None) -> str | None:
    """Cucina in italiano: dalla traduzione della ricetta se c'è, altrimenti
    dal dizionario (le traduzioni in cache più vecchie non la includono)."""
    if tradotta and tradotta != originale:
        return tradotta
    return AREA_IT.get(originale or "", originale)


def _targets_out(targets) -> NutritionTargetsOut:
    return NutritionTargetsOut(
        tdee_kcal=targets.tdee_kcal,
        target_kcal=targets.target_kcal,
        calorie_adjustment_pct=targets.calorie_adjustment_pct,
        protein_g=targets.protein_g,
        carbs_g=targets.carbs_g,
        fat_g=targets.fat_g,
        fiber_g=targets.fiber_g,
        free_sugars_max_g=targets.free_sugars_max_g,
        water_l=targets.water_l,
        protein_g_per_kg=targets.protein_g_per_kg,
        protein_pct=targets.protein_pct,
        carbs_pct=targets.carbs_pct,
        fat_pct=targets.fat_pct,
        rationale=targets.rationale,
        warnings=targets.warnings,
        knowledge_tags=targets.knowledge_tags,
    )


def _compute_targets(profile: UserProfile):
    try:
        return profile, nutrition_targets.compute_targets(
            profile, training_days=profile.training_days_per_week
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/targets", response_model=NutritionTargetsOut)
def read_targets(profile: UserProfile = Depends(owned_profile)) -> NutritionTargetsOut:
    """Target giornalieri calcolati dal profilo.

    Le proteine sono in g/kg di peso corporeo e non come percentuale delle
    calorie: il fabbisogno dipende dalla massa da mantenere, non da quanto si
    mangia.
    """
    _, targets = _compute_targets(profile)
    return _targets_out(targets)


@router.post("/targets/save", response_model=NutritionTargetsOut, status_code=201)
def save_targets(
    db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> NutritionTargetsOut:
    profile, targets = _compute_targets(profile)
    nutrition_targets.persist_plan(db, profile, targets)
    return _targets_out(targets)


@router.get("/foods/search", response_model=list[FoodSearchOut])
def search_foods(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=15, ge=1, le=40),
    db: Session = Depends(get_db),
) -> list[FoodSearchOut]:
    """Cerca un alimento su USDA (generici) e wger/Open Food Facts (di marca).

    Restituisce **tutti** i candidati con i loro valori: la scelta spetta
    all'utente. È la differenza fra un conteggio e una stima, e protegge dal
    problema dei dati inseriti dagli utenti, dove voci con lo stesso nome
    hanno a volte valori molto diversi.
    """
    risultati = food_diary.search_foods(db, q, limit=limit)[:limit]
    # Solo i nomi già tradotti: la traduzione dei nuovi arriva con una
    # seconda chiamata, così i risultati compaiono subito.
    nomi_it = translation.cached_food_names(db, [r.ingredient.id for r in risultati])
    return [
        FoodSearchOut(
            ingredient_id=r.ingredient.id,
            name=r.ingredient.name,
            name_it=nomi_it.get(r.ingredient.id),
            source_label=r.source_label,
            is_generic=r.is_generic,
            kcal_100g=r.kcal_100g,
            protein_100g=r.protein_100g,
            carbs_100g=r.carbs_100g,
            fat_100g=r.fat_100g,
        )
        for r in risultati
    ]


def _food_out(ingrediente: Ingredient) -> dict:
    return dict(
        ingredient_id=ingrediente.id,
        name=ingrediente.name,
        name_it=None,
        source_label=food_diary.source_label(ingrediente),
        is_generic=ingrediente.source == IngredientSource.USDA,
        kcal_100g=ingrediente.kcal_100g,
        protein_100g=ingrediente.protein_100g,
        carbs_100g=ingrediente.carbs_100g,
        fat_100g=ingrediente.fat_100g,
    )


@router.get("/foods/barcode/{barcode}", response_model=BarcodeFoodOut)
def food_by_barcode(
    barcode: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> BarcodeFoodOut:
    """Prodotto dal codice a barre, con i valori per 100 g.

    Il metodo più preciso per i prodotti confezionati: identifica il prodotto
    esatto invece di scegliere fra voci con lo stesso nome. Una seconda
    scansione dello stesso codice legge la cache, senza chiamare Open Food
    Facts. Codice sconosciuto o valori incompleti rispondono 404, con un
    messaggio che invita a inserire il prodotto a mano.
    """
    try:
        codice = off_client.normalize_barcode(barcode)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # La quota si consuma solo se il prodotto non è già in cache.
    gia_noto = db.scalar(select(Ingredient.id).where(Ingredient.barcode == codice).limit(1))
    if gia_noto is None:
        try:
            rate_limit.consume_daily(db, user.id, "barcode_lookup")
        except rate_limit.RateLimited as e:
            raise HTTPException(
                status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)}
            ) from e

    try:
        esito = food_diary.lookup_barcode(db, codice, user_id=user.id)
    except off_client.ProductNotFound as e:
        raise HTTPException(
            status_code=404,
            detail="Prodotto non trovato, vuoi inserirlo manualmente?",
        ) from e
    except off_client.IncompleteProduct as e:
        raise HTTPException(
            status_code=404,
            detail=f"{e} Vuoi inserirlo manualmente?",
        ) from e
    except off_client.OffError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return BarcodeFoodOut(**_food_out(esito.ingredient), barcode=codice, cached=esito.cached)


@router.post("/foods/manual", response_model=FoodSearchOut, status_code=201)
def create_manual_food(
    payload: ManualProductIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> FoodSearchOut:
    """Prodotto inserito dall'etichetta (visibile solo a chi lo inserisce).

    Con il codice a barre, la prossima scansione dello stesso prodotto lo
    ritrova subito.
    """
    try:
        ingrediente = food_diary.create_manual_product(db, user_id=user.id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return FoodSearchOut(**_food_out(ingrediente))


@router.post("/foods/names", response_model=dict[int, str])
def translate_food_names(
    payload: FoodNamesIn, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[int, str]:
    """Nomi italiani degli alimenti indicati (USDA li fornisce in inglese)."""
    try:
        rate_limit.consume_daily(db, user.id, "food_names")
    except rate_limit.RateLimited as e:
        raise HTTPException(
            status_code=429, detail=str(e), headers={"Retry-After": str(e.retry_after)}
        ) from e
    ingredienti = db.scalars(
        select(Ingredient).where(Ingredient.id.in_(payload.ids[:25]))
    ).all()
    return translation.translate_food_names(db, list(ingredienti))


@router.get("/diary/fill-gap", response_model=GapSuggestionsOut)
def fill_gap(
    db: Session = Depends(get_db), profile: UserProfile = Depends(owned_profile)
) -> GapSuggestionsOut:
    """Con quali alimenti, e quanti grammi, chiudere le proteine di oggi
    restando nelle calorie rimaste. Proposte: l'utente conferma."""
    profile, targets = _compute_targets(profile)
    totali = food_diary.daily_totals(db, profile)
    proteine_integratori = supplements.protein_from_supplements(db, profile)
    if proteine_integratori:
        totali.protein_g += proteine_integratori
        totali.kcal += proteine_integratori * nutrition_targets.KCAL_PER_G_PROTEIN

    rimanenti = totali.remaining_against(targets)
    esito = gap_filler.suggest(
        db, profile, protein_left_g=rimanenti["protein_g"], kcal_left=rimanenti["kcal"]
    )
    nomi = translation.translate_food_names(db, [f.ingredient for f in esito.foods])
    return GapSuggestionsOut(
        protein_left_g=round(max(0.0, esito.protein_left_g), 1),
        kcal_left=round(esito.kcal_left),
        message=esito.message,
        foods=[
            GapFoodOut(
                ingredient_id=f.ingredient.id,
                name=nomi.get(f.ingredient.id, f.ingredient.name),
                grams=f.grams,
                kcal=f.kcal,
                protein_g=f.protein_g,
                carbs_g=f.carbs_g,
                fat_g=f.fat_g,
                habitual=f.habitual,
                source_label=(
                    "generico (USDA)"
                    if f.ingredient.source == IngredientSource.USDA
                    else "prodotto di marca"
                ),
            )
            for f in esito.foods
        ],
    )


@router.post("/diary/items", response_model=MealItemOut, status_code=201)
def add_food(
    payload: MealItemIn,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> MealItem:
    ingrediente = db.get(Ingredient, payload.ingredient_id)
    # I prodotti inseriti a mano appartengono a chi li ha inseriti.
    if ingrediente is None or (
        ingrediente.created_by_user_id is not None and ingrediente.created_by_user_id != profile.user_id
    ):
        raise HTTPException(status_code=404, detail="Alimento non trovato")

    pasto = food_diary.get_or_create_meal(
        db, profile, date=payload.date, meal_type=payload.meal_type
    )
    voce = food_diary.add_food(db, pasto, ingrediente, grams=payload.grams)
    # La voce del diario conserva il nome: se la traduzione esiste già, si
    # salva quella, così il diario si legge in italiano.
    nome_it = translation.cached_food_names(db, [ingrediente.id]).get(ingrediente.id)
    if nome_it and voce.name != nome_it:
        voce.name = nome_it
        db.commit()
        db.refresh(voce)
    return voce


def _owned_item(db: Session, item_id: int, user: User) -> MealItem:
    """Una voce del diario, solo se il pasto è di un profilo dell'utente."""
    item = db.get(MealItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    ensure_owner(db, item.meal_log.profile_id, user, "Voce non trovata")
    return item


@router.patch("/diary/items/{item_id}", response_model=MealItemOut)
def update_quantity(
    item_id: int,
    grams: float = Query(gt=0, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MealItem:
    item = _owned_item(db, item_id, user)
    return food_diary.update_quantity(db, item, grams)


@router.delete("/diary/items/{item_id}", status_code=204, response_model=None)
def remove_food(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    item = _owned_item(db, item_id, user)
    food_diary.remove_food(db, item)


@router.get("/diary", response_model=DiaryOut)
def read_diary(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> DiaryOut:
    """Giornata completa con il confronto rispetto ai target.

    Le proteine dagli integratori dichiarati vengono **sommate** al totale,
    perché il target è l'apporto proteico giornaliero e non l'integratore in
    sé.
    """
    profile, targets = _compute_targets(profile)
    giorno = date or dt.date.today()

    pasti = db.scalars(
        select(MealLog).where(
            MealLog.profile_id == profile.id,
            MealLog.date == giorno,
            MealLog.is_planned.is_(False),
        )
    ).all()

    totali = food_diary.daily_totals(db, profile, date=giorno)

    proteine_integratori = supplements.protein_from_supplements(db, profile)
    if proteine_integratori:
        totali.protein_g += proteine_integratori
        totali.kcal += proteine_integratori * nutrition_targets.KCAL_PER_G_PROTEIN

    return DiaryOut(
        date=giorno,
        meals=[
            MealOut(
                id=p.id,
                meal_type=p.meal_type,
                items=[MealItemOut.model_validate(i) for i in p.items],
                **{
                    k: v
                    for k, v in vars(food_diary.meal_totals(p)).items()
                    if k in ("kcal", "protein_g", "carbs_g", "fat_g")
                },
            )
            for p in pasti
        ],
        totals=vars(totali),
        targets=_targets_out(targets),
        remaining=totali.remaining_against(targets),
        progress=totali.progress_against(targets),
    )


@router.get("/recipes/suggest", response_model=list[RecipeSuggestionOut])
def suggest_recipes(
    query: str | None = Query(default=None, max_length=100),
    consumed_kcal: float = 0.0,
    consumed_protein_g: float = 0.0,
    top: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
    profile: UserProfile = Depends(owned_profile),
) -> list[RecipeSuggestionOut]:
    """Ricette che avvicinano ai target rimasti per la giornata.

    Attenzione alla natura del dato: i valori nutrizionali sono **stimati**,
    perché le quantità delle ricette sono in linguaggio comune ("¼ cup") e
    vanno convertite. Il campo `coverage` dice quanti ingredienti sono stati
    riconosciuti; sotto il 75% la ricetta non viene proposta affatto.
    """
    profile, targets = _compute_targets(profile)

    try:
        suggerimenti = meal_suggestions.suggest_meals(
            db, profile, targets,
            query=query,
            consumed_kcal=consumed_kcal,
            consumed_protein_g=consumed_protein_g,
            top=top,
        )
    except meal_suggestions.RecipeSourceUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # I macro sono già calcolati sugli ingredienti originali: la traduzione
    # riguarda solo il testo mostrato, non tocca nessun numero.
    tradotte = translation.translate_recipes(
        db,
        [
            {
                "meal_id": s.analyzed.recipe.meal_id,
                "name": s.analyzed.recipe.name,
                "category": s.analyzed.recipe.category,
                "area": s.analyzed.recipe.area,
                "ingredients": [
                    f"{i.measure} {i.name}".strip() for i in s.analyzed.ingredients
                ],
                "instructions": s.analyzed.recipe.instructions,
            }
            for s in suggerimenti
        ],
    )

    return [
        RecipeSuggestionOut(
            name=t["name"],
            original_name=(
                s.analyzed.recipe.name if t["name"] != s.analyzed.recipe.name else None
            ),
            category=t["category"],
            area=_area_it(s.analyzed.recipe.area, t.get("area")),
            thumbnail_url=s.analyzed.recipe.thumbnail_url,
            youtube_url=s.analyzed.recipe.youtube_url,
            instructions=t["instructions"],
            kcal_per_serving=round(s.analyzed.kcal_per_serving),
            protein_per_serving=round(s.analyzed.protein_per_serving, 1),
            carbs_per_serving=round(s.analyzed.carbs_per_serving, 1),
            fat_per_serving=round(s.analyzed.fat_per_serving, 1),
            fiber_per_serving=round(s.analyzed.fiber_per_serving, 1),
            servings=s.analyzed.servings,
            coverage=round(s.analyzed.coverage, 2),
            fit_score=round(s.fit_score, 1),
            reasons=s.reasons,
            ingredients=t["ingredients"],
        )
        for s, t in zip(suggerimenti, tradotte)
    ]
