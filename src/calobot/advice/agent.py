"""The read-only advice agent for the `other` intent. See specs/advice-agent in
full, and design.md - Decision 3 for the two-phase gather/narrate shape this
implements: a bounded tool-calling loop that only retrieves data, followed by one
schema-constrained call that turns what was retrieved into the user-visible text.
"""

from __future__ import annotations

import json
import logging
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.advice.tools import build_tool_registry
from calobot.llm.content import MessageContent, TextContent
from calobot.llm.errors import LLMError
from calobot.llm.gateway import LLMGateway, ToolCallResult
from calobot.persistence.models import User
from calobot.safety.claims import asserts_a_record
from calobot.safety.conversation import handle_other
from calobot.safety.medical import REFUSAL_TEXT, is_medical_topic

logger = logging.getLogger(__name__)

GATHER_SYSTEM_PROMPT = """\
Sei l'assistente di un bot italiano di tracciamento nutrizionale. Un utente ha fatto
una domanda sui propri dati (cibo, peso, attivita') oppure ha scritto qualcosa di
conversazionale (saluto, domanda generica, richiesta di consiglio non legata ai suoi
dati).

Hai a disposizione strumenti di sola lettura per recuperare i suoi dati reali. Regole:

- Se la domanda riguarda i SUOI dati (quante calorie, come sta andando il peso, cosa
  ha mangiato, quanto budget resta), usa gli strumenti prima di rispondere. Non
  calcolare mai un totale, una media o una differenza a mente: gli strumenti la
  restituiscono gia' calcolata, e devi riportare esattamente quel numero.
- Se il messaggio non ha bisogno di dati (un saluto, una domanda su come funziona il
  bot), non chiamare nessuno strumento.
- Il bot NON traccia macronutrienti, sodio, zuccheri o altri valori nutrizionali oltre
  alle calorie: non esiste uno strumento per quelli, e non devi inventarli.
- Quando ritieni di avere abbastanza dati (o di non averne bisogno), fermati: non
  chiamare altri strumenti.
"""


def _narrate_system_prompt(bot_label: str) -> str:
    return f"""\
Sei {bot_label}, un bot italiano di tracciamento nutrizionale (non un consulente
medico). Ti sono stati forniti i risultati di alcuni strumenti che hanno interrogato
il diario dell'utente, in formato JSON, insieme alla sua domanda originale.

Regole:
- Rispondi in italiano, breve e cordiale, usando esclusivamente i numeri presenti nei
  risultati forniti. Non calcolare, arrotondare diversamente o correggere un valore:
  riportalo come e'.
- Se un risultato ha "no_data": true, significa che per quel periodo non ci sono dati,
  oppure che il bot non traccia quella informazione. In quel caso non stimare nulla:
  dillo chiaramente e imposta declined_reason.
- Se non ti e' stato fornito nessun risultato perche' la domanda non richiedeva dati
  (un saluto, una domanda generica), rispondi normalmente senza inventare numeri.
- NON dare consigli medici, clinici, su farmaci, diagnosi o disturbi alimentari: se
  la domanda lo richiede, rispondi che non sei uno strumento medico e suggerisci un
  professionista, senza aggiungere altro.
- Non affermare mai di aver registrato, salvato, modificato o eliminato qualcosa: puoi
  solo leggere e spiegare, non scrivere nulla nel diario.
"""


class AdviceAnswer(BaseModel):
    answer_text: str
    used_data: bool = Field(
        description="True se la risposta si basa sui risultati degli strumenti, False "
        "per un saluto o una domanda generica che non ne aveva bisogno."
    )
    declined_reason: str | None = Field(
        default=None,
        description="Impostato solo quando i dati necessari non esistono o non sono "
        "tracciati, spiegando perche' non e' possibile rispondere con un numero.",
    )


COULD_NOT_ANSWER_TEXT = (
    "Non sono riuscito a ricostruire una risposta con i dati disponibili. Puoi provare "
    "a essere piu' specifico, per esempio indicando un periodo preciso?"
)

UNFOUNDED_CLAIM_REPLACEMENT = (
    "Non ho toccato il tuo diario: posso solo leggere i tuoi dati e spiegarteli. Puoi "
    "riformulare la domanda?"
)


def _narration_prompt(raw_text: str, tool_results: list[ToolCallResult]) -> str:
    payload = [
        {"tool": r.tool, "arguments": r.arguments, "result": r.result} for r in tool_results
    ]
    return (
        f'Domanda originale dell\'utente: "{raw_text}"\n\n'
        f"Risultati degli strumenti (lista vuota se nessuno e' stato usato):\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


async def answer(
    session: AsyncSession,
    gateway: LLMGateway,
    user: User,
    tz: ZoneInfo,
    raw_text: str,
    content: MessageContent,
    bot_label: str,
    max_rounds: int,
) -> str:
    """Answers the `other` intent. Falls back to the plain conversational reply
    (`handle_other`) on any LLM failure or an exhausted retrieval bound
    (design.md - Decision 7), so a degraded model never surfaces as an error."""
    if is_medical_topic(raw_text):
        return REFUSAL_TEXT

    try:
        tools = await build_tool_registry(session, gateway, user, tz)
        gather = await gateway.call_agentic(
            step="advice_gather",
            system_prompt=GATHER_SYSTEM_PROMPT,
            content=content,
            tools=tools,
            max_rounds=max_rounds,
        )
        if gather.exhausted:
            return COULD_NOT_ANSWER_TEXT

        narration = TextContent(text=_narration_prompt(raw_text, gather.tool_results))
        result = await gateway.call_structured(
            step="advice_narrate",
            system_prompt=_narrate_system_prompt(bot_label),
            content=narration,
            schema=AdviceAnswer,
            extra_telemetry={
                "agent_turn_id": gather.agent_turn_id,
                "round_index": "narrate",
                "tool_name": None,
            },
        )
    except LLMError:
        logger.warning("advice agent failed, falling back to plain conversation", exc_info=True)
        return await handle_other(gateway, raw_text, content, bot_label)

    reply = result.answer_text
    if asserts_a_record(reply):
        logger.warning("suppressed an advice reply claiming a record was made: %r", reply)
        return UNFOUNDED_CLAIM_REPLACEMENT
    return reply
