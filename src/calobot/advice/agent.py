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
from calobot.telemetry.context import active_chat_id

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
- Se l'utente chiede un consiglio su cosa mangiare o una ricetta (es. "cosa mi
  consigli di mangiare stasera?"), usa SEMPRE sia `get_profile_and_budget` sia
  `get_recent_food_descriptions`, cosi' da conoscere sia le calorie rimanenti sia
  cosa ha gia' mangiato di recente.
- Per la categoria 2, NON chiamare nessuno strumento: non serve alcun dato personale
  per rispondere, la risposta verra' data dalle tue conoscenze generali.
- Il bot NON traccia macronutrienti, sodio, zuccheri o altri valori nutrizionali oltre
  alle calorie: non esiste uno strumento per quelli, e non devi inventarli.
- Quando ritieni di avere abbastanza dati (o di non averne bisogno), fermati: non
  chiamare altri strumenti.
- Se nel messaggio dell'utente ci sono pronomi o riferimenti ambigui (es. 'che proprietà hanno', 'quali sono le sue proprietà'), usa la cronologia dei messaggi inclusa nel prompt per identificare a quale alimento, peso o attività si riferisce l'utente.
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
- Se nella domanda originale dell'utente ci sono pronomi o riferimenti ambigui (es. 'che proprietà hanno'), usa la cronologia dei messaggi inclusa per comprendere a cosa si riferisce la domanda e rispondi specificando chiaramente di cosa stai parlando (es. spiegando le proprietà dei 'crauti fermentati' se la cronologia recente mostra che si parlava di quello).

RICETTE E SUGGERIMENTI DI PASTI:
- Se l'utente chiede idee su cosa mangiare o ricette (es. "cosa posso mangiare stasera?"), controlla se è stato usato lo strumento `get_profile_and_budget` per verificare le calorie rimanenti oggi (`remaining_today_kcal`):
  1. Se le calorie rimanenti sono POSITIVE (es. 400 kcal): suggerisci 1-2 ricette o idee di pasti sani e realistici che stiano perfettamente entro quel budget calorico residuo. Riporta esplicitamente il valore delle calorie rimanenti nella risposta per motivare le tue proposte.
  2. Se le calorie rimanenti sono ZERO o NEGATIVE (l'utente ha esaurito o superato il suo budget, es. -150 kcal): NON consigliare di saltare i pasti, digiunare o compensare eccessivamente. Fornisci invece un supporto empatico, rassicura l'utente che è normale sforare ogni tanto, e proponi opzioni di spuntini/pasti a bassissima densità calorica (< 100 kcal/100g, come finocchi, cetrioli o brodi caldi leggeri, restando sotto le 100 kcal totali) che danno sazietà e volume senza appesantire la giornata.
- Se è stato usato anche `get_recent_food_descriptions`, guarda le descrizioni dei
  pasti recenti in modo qualitativo (esattamente come faresti per la densità
  calorica) per capire se sembra mancare una fonte proteica, o se i pasti recenti
  sono stati prevalentemente ad alta densità calorica, e orienta la tua proposta
  di conseguenza (es. verso un secondo con proteine se ne è mancata una). Se
  "no_data" è true o non ci sono abbastanza informazioni, non inventare un
  pattern: suggerisci comunque la ricetta in base solo alle calorie rimanenti.
  Il bot NON traccia i macronutrienti (carboidrati, grassi, proteine): non
  indicare MAI una quantità in grammi di un macronutriente, ragiona solo in
  termini qualitativi sulle descrizioni dei cibi.
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


def _get_recent_history_context(chat_id: int | None) -> str:
    if chat_id is None:
        return ""
    from calobot.telemetry.history import telemetry_history
    events = telemetry_history.get_events(chat_id)
    if not events:
        return ""

    recent_lines = []
    for e in events:
        if e.get("type") == "incoming_update" and e.get("text"):
            recent_lines.append(f"User: {e['text']}")
        elif e.get("type") == "outgoing_response" and e.get("text"):
            recent_lines.append(f"Bot: {e['text'].strip()}")

    # Take the last 6 lines of conversation to keep it concise but contextual
    recent_lines = recent_lines[-6:]
    if not recent_lines:
        return ""

    return "\n".join(recent_lines)


def _narration_prompt(raw_text: str, tool_results: list[ToolCallResult], history_context: str = "") -> str:
    payload = [
        {"tool": r.tool, "arguments": r.arguments, "result": r.result} for r in tool_results
    ]
    history_part = f"Cronologia recente dei messaggi:\n{history_context}\n\n" if history_context else ""
    return (
        f"{history_part}"
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
        chat_id = active_chat_id.get(None)
        history_context = _get_recent_history_context(chat_id)

        enriched_content = content
        if history_context and isinstance(content, TextContent):
            prompt_text = (
                f"[Cronologia recente dei messaggi (usa questa cronologia per comprendere il contesto ed "
                f"eventuali riferimenti a pronomi o cibi nominati in precedenza)]:\n"
                f"{history_context}\n\n"
                f"[Nuovo messaggio dell'utente]:\n"
                f"{raw_text}"
            )
            enriched_content = TextContent(text=prompt_text)

        tools = await build_tool_registry(session, gateway, user, tz)
        gather = await gateway.call_agentic(
            step="advice_gather",
            system_prompt=GATHER_SYSTEM_PROMPT,
            content=enriched_content,
            tools=tools,
            max_rounds=max_rounds,
        )
        if gather.exhausted:
            return COULD_NOT_ANSWER_TEXT

        narration = TextContent(text=_narration_prompt(raw_text, gather.tool_results, history_context))
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
