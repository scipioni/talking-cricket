"""Personalized behavioral dietician reports. See specs/dietician-reviews - ADDED and
MODIFIED Requirements."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from calobot.llm.content import TextContent
from calobot.persistence.models import Provenance

if TYPE_CHECKING:
    from calobot.llm.gateway import LLMGateway
    from calobot.persistence.models import FoodEntry
    from calobot.reporting.periods import Period

logger = logging.getLogger(__name__)

# Appended to DIETICIAN_SYSTEM_PROMPT depending on the report period, so the single
# actionable_tip field is framed as forward-looking for a week vs. a general habit
# for month/year (design.md - Decisions: tier the existing field, chosen in Python
# rather than left for the model to infer from the period value).
_WEEK_TIP_FRAMING = """
Per il campo actionable_tip: dai un consiglio pratico su cosa fare nei GIORNI RIMANENTI
di questa settimana, sulla base dell'andamento osservato finora.
"""

_GENERAL_HABIT_TIP_FRAMING = """
Per il campo actionable_tip: dai un consiglio pratico su un'ABITUDINE GENERALE di salute
da adottare, che affronti esplicitamente l'equilibrio tra proteine, grassi e carboidrati
in modo qualitativo (es. "assicurati una fonte proteica ad ogni pasto" o "alterna
carboidrati semplici e complessi"), senza mai indicare una quantità in grammi di un macronutriente:
questa analisi ragiona solo sui segnali indiretti sotto, non sui grammi di macronutrienti
(per quelli l'utente può chiedere un report dedicato).
"""

DIETICIAN_SYSTEM_PROMPT = """Sei un nutrizionista clinico italiano, empatico, professionale e incoraggiante. Il tuo compito è analizzare il riepilogo del diario alimentare dell'utente per fornire un feedback comportamentale e nutrizionale utile, senza giudicare.

Questa analisi si basa esclusivamente sui seguenti segnali indiretti ricavati dal diario alimentare dell'utente, non sui grammi di macronutrienti (che l'utente può ottenere con un report dedicato):

1. DENSITÀ CALORICA (kcal/100g):
   - Alimenti < 100 kcal/100g sono a bassa densità (es. verdure, frutta, zuppe). Favoriscono la sazietà volumetrica.
   - Alimenti > 300 kcal/100g sono ad alta densità (es. dolci, snack confezionati, formaggi stagionati). Offrono molta energia in piccoli volumi.

2. TIMING E ORARI DI CONSUMO:
   - Valuta se le calorie sono distribuite regolarmente o se si concentrano la sera tardi.
   - Identifica pattern di fame notturna o di digiuni prolungati seguiti da pasti abbondanti.

3. VARIETÀ E DIETA:
   - Guarda le descrizioni dei cibi. Mangiano sempre le stesse cose? Suggerisci di variare per ottenere micronutrienti migliori.

4. ACCURATEZZA DI REGISTRAZIONE (provenance):
   - 'etichetta' (da foto etichetta nutrizionale) e 'off' (OpenFoodFacts via barcode) sono fonti ad altissima precisione.
   - 'tabella' (tabelle alimentari integrate) è di precisione media.
   - 'llm' (stima IA) è una stima generica.
   - Incoraggia l'utente a usare più etichette/codici a barre se vedi troppe stime 'llm' su cibi confezionati.

REGOLE DI SCRITTURA:
- Scrivi in italiano corretto, fluido ed empatico. Usa sempre il "tu" rivolgendoti all'utente.
- Sii estremamente breve e coinciso: ogni campo della risposta deve contenere al massimo 2 o 3 frasi.
- Non inventare dati o grammi di macronutrienti (es. non dire "hai mangiato 80g di grassi" se non puoi dedurlo dai segnali sopra; parla invece di cibi ad alta densità calorica o zuccheri complessi).
- Fornisci UN SOLO consiglio pratico (actionable_tip), piccolo e realizzabile, per la settimana successiva.
"""


class DieticianReview(BaseModel):
    summary: str = Field(
        description="Breve sintesi empatica in italiano (max 2 frasi) sull'andamento generale e la costanza dell'utente."
    )
    density_insight: str = Field(
        description="Analisi in italiano (max 3 frasi) sulla densità calorica dei cibi consumati, collegata al senso di sazietà."
    )
    temporal_pattern_insight: str = Field(
        description="Analisi in italiano (max 3 frasi) sugli orari dei pasti, regolarità e calorie serali tardive."
    )
    sourcing_insight: str = Field(
        description="Analisi in italiano (max 3 frasi) sulla precisione del diario, evidenziando il rapporto tra fonti certe ('etichetta'/'off') ed stime ('llm')."
    )
    actionable_tip: str = Field(
        description=(
            "Un singolo consiglio pratico, concreto e incoraggiante in italiano (max 2 frasi): "
            "per un periodo settimanale, cosa fare nei giorni rimanenti della settimana; "
            "per un periodo mensile o annuale, un'abitudine generale di salute, incluso "
            "l'equilibrio qualitativo tra proteine, grassi e carboidrati, senza mai indicare grammi."
        )
    )


def get_dietician_signals(entries: list[FoodEntry], tz: Any) -> dict[str, Any]:
    """Extract indirect behavioral nutritional signals from raw FoodEntries."""
    if not entries:
        return {}

    total_kcal = sum(e.kcal for e in entries)
    total_grams = sum(e.grams for e in entries if e.grams is not None)
    avg_density = (total_kcal / total_grams * 100) if total_grams > 0 else 0.0

    low_density_items: set[str] = set()
    high_density_items: set[str] = set()
    descriptions_count: dict[str, int] = {}

    # Temporal categories: morning, afternoon, evening, late night
    time_distribution_kcal = {
        "mattina (05:00-11:59)": 0.0,
        "pomeriggio (12:00-17:59)": 0.0,
        "sera (18:00-21:59)": 0.0,
        "notte (22:00-04:59)": 0.0,
    }

    provenance_distribution = {
        "etichetta (foto etichetta)": 0,
        "off (barcode)": 0,
        "tabella (fct)": 0,
        "llm (stima)": 0,
    }

    for e in entries:
        # Calorie density grouping
        density = e.kcal_per_100g
        norm_desc = e.description.strip().lower()
        descriptions_count[norm_desc] = descriptions_count.get(norm_desc, 0) + 1

        if density < 100:
            low_density_items.add(e.description)
        elif density > 300:
            high_density_items.add(e.description)

        # Hour of consumption
        local_dt = e.consumed_at.astimezone(tz)
        hour = local_dt.hour
        if 5 <= hour < 12:
            time_distribution_kcal["mattina (05:00-11:59)"] += e.kcal
        elif 12 <= hour < 18:
            time_distribution_kcal["pomeriggio (12:00-17:59)"] += e.kcal
        elif 18 <= hour < 22:
            time_distribution_kcal["sera (18:00-21:59)"] += e.kcal
        else:
            time_distribution_kcal["notte (22:00-04:59)"] += e.kcal

        # Provenance distribution
        prov = e.provenance
        if prov == Provenance.etichetta:
            provenance_distribution["etichetta (foto etichetta)"] += 1
        elif prov == Provenance.off:
            provenance_distribution["off (barcode)"] += 1
        elif prov == Provenance.tabella:
            provenance_distribution["tabella (fct)"] += 1
        elif prov == Provenance.llm:
            provenance_distribution["llm (stima)"] += 1

    unique_days = {e.consumed_at.astimezone(tz).date() for e in entries}
    frequent_foods = sorted(descriptions_count.keys(), key=lambda k: descriptions_count[k], reverse=True)[:5]

    return {
        "total_kcal": round(total_kcal),
        "days_logged": len(unique_days),
        "average_kcal_density_per_100g": round(avg_density, 1),
        "high_density_items": sorted(list(high_density_items))[:6],
        "low_density_items": sorted(list(low_density_items))[:6],
        "time_distribution_kcal": {k: round(v) for k, v in time_distribution_kcal.items()},
        "provenance_distribution_count": provenance_distribution,
        "unique_foods_count": len(descriptions_count),
        "frequent_foods": frequent_foods,
    }


_AVOID_REPEATING_TEMPLATE = """
Non hai ancora ricevuto conferma che questo consiglio precedente sia stato seguito o
meno: "{previous_tip}"
Non ripeterlo testualmente: se e' ancora valido, riformulalo o proponi una sfumatura
diversa; se non lo e' piu', proponi un consiglio diverso.
"""


async def build_dietitian_review(
    gateway: LLMGateway,
    entries: list[FoodEntry],
    tz: Any,
    period: Period,
    *,
    avoid_repeating: str | None = None,
) -> DieticianReview | str | None:
    """Builds the dietician review. Returns DieticianReview if successful,
    a fallback string if there is insufficient data (< 3 distinct days logged),
    or None if no entries exist. `period` tiers the actionable_tip framing:
    rest-of-week for "week", general habit (with qualitative macro balance)
    for "month"/"year" (specs/dietician-reviews - Dietician review structured
    schema). `avoid_repeating`, when set, is the text of the user's most recent
    unresolved tip of the same period tier (specs/advice-memory - A recent
    unresolved actionable tip is not repeated verbatim)."""
    if not entries:
        return None

    unique_days = {e.consumed_at.astimezone(tz).date() for e in entries}
    if len(unique_days) < 3:
        return (
            "Per darti un parere nutrizionale personalizzato ho bisogno di almeno 3 giorni di "
            "registrazioni in questo periodo. Continua così e presto avrò abbastanza dati per aiutarti!"
        )

    signals = get_dietician_signals(entries, tz)

    import json
    prompt_content = (
        "Ecco il riepilogo statistico ricavato dal diario alimentare dell'utente:\n\n"
        f"{json.dumps(signals, indent=2, ensure_ascii=False)}"
    )

    tip_framing = _WEEK_TIP_FRAMING if period == "week" else _GENERAL_HABIT_TIP_FRAMING
    system_prompt = DIETICIAN_SYSTEM_PROMPT + tip_framing
    if avoid_repeating:
        system_prompt += _AVOID_REPEATING_TEMPLATE.format(previous_tip=avoid_repeating)

    try:
        review = await gateway.call_structured(
            step="extract",
            system_prompt=system_prompt,
            content=TextContent(text=prompt_content),
            schema=DieticianReview,
        )
        return review
    except Exception as exc:
        logger.error("Errore durante la generazione del parere del nutrizionista: %s", exc)
        return "Non è stato possibile generare il parere del nutrizionista in questo momento."


DAILY_ADVICE_SYSTEM_PROMPT = """Sei un nutrizionista clinico italiano, empatico, professionale e incoraggiante.
Dai un breve consiglio pratico su cosa mangiare o fare per il RESTO DELLA GIORNATA di oggi, sulla base di
quanto l'utente ha già mangiato oggi e delle calorie che gli restano nel budget giornaliero (già corretto
per l'attività fisica svolta, se presente).

Valuta l'equilibrio del pasto solo in modo qualitativo dalle descrizioni dei cibi (es. se sembra mancare
una fonte proteica, o se è stato tutto ad alta densità calorica): questo consiglio ragiona sulle descrizioni,
non sui grammi di macronutrienti, quindi non indicare mai una quantità in grammi di un macronutriente.

REGOLE DI SCRITTURA:
- Scrivi in italiano corretto, fluido ed empatico. Usa il "tu".
- Massimo 2 frasi, concreto e realizzabile.
- Non giudicare, non inventare dati.
"""


class DailyAdvice(BaseModel):
    advice: str = Field(
        description="Un consiglio pratico e breve in italiano (max 2 frasi) per il resto della giornata."
    )


async def build_daily_advice(
    gateway: LLMGateway,
    entries_today: list[FoodEntry],
    remaining_kcal: float | None,
    activity_credit_kcal: float,
    *,
    avoid_repeating: str | None = None,
) -> str | None:
    """Rest-of-day advice for the daily calorie report. Returns None when no food
    was logged today, or when the LLM call fails (specs/reporting - Calorie report
    contents: rest-of-day advice). `avoid_repeating` mirrors
    `build_dietitian_review`'s parameter of the same name."""
    if not entries_today:
        return None

    foods = [
        {"descrizione": e.description, "kcal": round(e.kcal), "kcal_per_100g": round(e.kcal_per_100g)}
        for e in entries_today
    ]

    import json

    signals: dict[str, Any] = {"cibi_mangiati_oggi": foods}
    if remaining_kcal is not None:
        signals["calorie_rimanenti_oggi"] = round(remaining_kcal)
    if activity_credit_kcal:
        signals["credito_da_attivita_fisica_kcal"] = round(activity_credit_kcal)

    prompt_content = (
        "Ecco cosa l'utente ha mangiato oggi finora:\n\n" f"{json.dumps(signals, indent=2, ensure_ascii=False)}"
    )

    system_prompt = DAILY_ADVICE_SYSTEM_PROMPT
    if avoid_repeating:
        system_prompt += _AVOID_REPEATING_TEMPLATE.format(previous_tip=avoid_repeating)

    try:
        result = await gateway.call_structured(
            step="extract",
            system_prompt=system_prompt,
            content=TextContent(text=prompt_content),
            schema=DailyAdvice,
        )
        return result.advice
    except Exception as exc:
        logger.error("Errore durante la generazione del consiglio giornaliero: %s", exc)
        return None


def format_dietician_review(review: DieticianReview | str | None) -> str:
    """Format the dietician review into beautiful Telegram Markdown in Italian."""
    if review is None:
        return ""
    if isinstance(review, str):
        return f"\n\n🍎 *IL PARERE DEL NUTRIZIONISTA*\n\n{review}"

    return (
        f"\n\n🍎 *IL PARERE DEL NUTRIZIONISTA*\n\n"
        f"• *Andamento generale:* {review.summary}\n"
        f"• *Sazietà e Volume:* {review.density_insight}\n"
        f"• *Orari e Pattern:* {review.temporal_pattern_insight}\n"
        f"• *Qualità del Diario:* {review.sourcing_insight}\n\n"
        f"💡 *IL CONSIGLIO DI QUESTA SETTIMANA*\n"
        f"{review.actionable_tip}"
    )

