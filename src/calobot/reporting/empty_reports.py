"""Conversational fallback for empty reports. See specs/reporting - Period with no data at all."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from calobot.llm.content import TextContent
from calobot.llm.gateway import LLMGateway
from calobot.reporting.periods import Period

logger = logging.getLogger(__name__)

EMPTY_REPORT_SYSTEM_PROMPT = """Sei il Grillo Parlante, un bot italiano empatico e incoraggiante per il tracciamento nutrizionale.
L'utente ti ha chiesto un report delle calorie per un certo periodo, ma NON ha registrato alcun pasto in quel periodo.

Il tuo compito è rispondergli in modo amichevole.
1. Informa l'utente che il diario è vuoto per il periodo richiesto.
2. Se il periodo è oggi ('day'), rassicuralo che ha a disposizione tutto il suo budget calorico (indicato nel prompt) per mangiare ciò che preferisce, e chiedigli cosa gli andrebbe.
3. Se il periodo è più lungo ('week', 'month', 'year'), incoraggialo semplicemente a iniziare a registrare i pasti per vedere le statistiche.

REGOLE DI SCRITTURA:
- Scrivi in italiano corretto, fluido ed empatico. Usa il "tu".
- Massimo 2 o 3 frasi.
- NON dare consigli medici.
"""


class EmptyReportResponse(BaseModel):
    message: str = Field(
        description="Il messaggio conversazionale da inviare all'utente, max 3 frasi."
    )


async def generate_empty_report_response(
    gateway: LLMGateway,
    period: Period,
    budget_kcal: float | None,
) -> str:
    """Generates a conversational response when a user asks for a calorie report
    but has no logged food data in the requested period."""

    import json

    context: dict[str, Any] = {"periodo_richiesto": period}
    if budget_kcal is not None:
        context["budget_giornaliero_kcal"] = round(budget_kcal)

    prompt_content = (
        "L'utente ha chiesto un report, ma non ha dati.\n\n"
        f"{json.dumps(context, indent=2, ensure_ascii=False)}"
    )

    try:
        result = await gateway.call_structured(
            step="empty_report",
            system_prompt=EMPTY_REPORT_SYSTEM_PROMPT,
            content=TextContent(text=prompt_content),
            schema=EmptyReportResponse,
        )
        return result.message
    except Exception as exc:
        logger.error("Errore durante la generazione del report vuoto conversazionale: %s", exc)
        return "Non ci sono dati sul cibo per questo periodo."
