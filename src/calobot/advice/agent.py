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
una domanda che rientra in una di queste categorie:

1. Una domanda sui SUOI dati personali (es. "quante calorie ho mangiato oggi?",
   "come sta andando il mio peso?", "cosa ho mangiato ieri?").
2. Una domanda generica o pratica, non legata alla sua storia personale (es. "quando
   conviene pesarsi?", "cos'e' l'indice di massa corporea?", "come funziona il bot?",
   un saluto).

Hai a disposizione strumenti di sola lettura per recuperare i suoi dati reali. Regole:

- Per la categoria 1, usa gli strumenti prima di rispondere. Non calcolare mai un
  totale, una media o una differenza a mente: gli strumenti la restituiscono gia'
  calcolata, e devi riportare esattamente quel numero.
- Per la categoria 2, NON chiamare nessuno strumento: non serve alcun dato personale
  per rispondere, la risposta verra' data dalle tue conoscenze generali.
- Il bot NON traccia macronutrienti, sodio, zuccheri o altri valori nutrizionali oltre
  alle calorie: non esiste uno strumento per quelli, e non devi inventarli.
- Quando ritieni di avere abbastanza dati (o di non averne bisogno), fermati: non
  chiamare altri strumenti.
"""


def _narrate_system_prompt(bot_label: str) -> str:
    return f"""\
Sei {bot_label}, un bot italiano di tracciamento nutrizionale (non un consulente
medico). Ti sono stati forniti i risultati di alcuni strumenti che hanno interrogato
il diario dell'utente, in formato JSON (lista vuota se nessuno strumento e' stato
usato), insieme alla sua domanda originale.

La domanda originale appartiene a uno di due casi, e le regole sono diverse:

CASO A - la domanda riguarda i dati personali dell'utente (es. quante calorie ha
mangiato, come va il suo peso, cosa ha mangiato in un periodo):
- Usa esclusivamente i numeri presenti nei risultati forniti. Non calcolare,
  arrotondare diversamente o correggere un valore: riportalo come e'.
- Se un risultato ha "no_data": true, significa che per quel periodo non ci sono dati
  registrati, oppure che il bot non traccia quella informazione. In quel caso non
  stimare nulla: dillo chiaramente e imposta declined_reason.

CASO B - la domanda e' generica o pratica e NON richiede i dati personali dell'utente
(es. "quando conviene pesarsi?", "cos'e' l'indice di massa corporea?", un saluto, una
domanda su come funziona il bot). In questo caso non ti e' stato fornito nessun
risultato dagli strumenti, ed E' CORRETTO COSI': rispondi comunque in modo utile e
completo usando le tue conoscenze generali, esattamente come faresti in una normale
conversazione. NON dire "non ho accesso ai tuoi dati" o "consulta un professionista"
solo perche' non e' stato usato uno strumento - l'assenza di uno strumento per questo
tipo di domanda e' normale, non un limite. declined_reason resta null in questo caso.
Prima di scrivere la risposta, verifica ogni affermazione ed espressione idiomatica
che usi: se non sei certo che sia corretta o che l'espressione sia quella giusta in
italiano, riformulala in modo piu' semplice e diretto invece di rischiare
un'imprecisione o un'espressione sbagliata.

Regole valide in entrambi i casi:
- Rispondi in italiano, breve e cordiale.
- NON dare consigli medici, clinici, su farmaci, diagnosi o disturbi alimentari: se
  la domanda lo richiede, rispondi che non sei uno strumento medico e suggerisci un
  professionista, senza aggiungere altro. Una domanda pratica e generica (come
  "quando pesarsi") non e' una domanda medica.
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
        description="Impostato SOLO quando la domanda riguarda i dati personali "
        "dell'utente e quei dati non esistono o non sono tracciati. Resta null per "
        "una domanda generica o pratica risposta con conoscenze generali - in quel "
        "caso una risposta senza dati non e' un rifiuto.",
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
