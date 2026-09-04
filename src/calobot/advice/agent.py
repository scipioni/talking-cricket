"""The read-only advice agent for the `other` intent. See specs/advice-agent in
full, and design.md - Decision 3 for the two-phase gather/narrate shape this
implements: a bounded tool-calling loop that only retrieves data, followed by one
schema-constrained call that turns what was retrieved into the user-visible text.
"""

from __future__ import annotations

import json
import logging
from typing import Literal, NamedTuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.advice.tools import SuggestionMode, build_tool_registry
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
  consigli di mangiare stasera?"), usa `get_meal_suggestion_context`: ti restituisce
  gia' pronto tutto cio' che serve per rispondere.
- Per la categoria 2, NON chiamare nessuno strumento: non serve alcun dato personale
  per rispondere, la risposta verra' data dalle tue conoscenze generali.
- Il bot traccia anche i macronutrienti (proteine, grassi, carboidrati, fibre), ma tu
  non hai uno strumento per recuperarli in questa modalità conversazionale: non stimarli
  né inventarli. Se l'utente chiede valori precisi di macronutrienti, invitalo a
  chiedere un report sui macronutrienti (es. "distribuzione di proteine, grassi,
  carboidrati e fibre di questa settimana"). Il bot non traccia invece sodio, zuccheri o
  altri valori nutrizionali oltre a calorie e macronutrienti.
- Quando ritieni di avere abbastanza dati (o di non averne bisogno), fermati: non
  chiamare altri strumenti.
- Se nel messaggio dell'utente ci sono pronomi o riferimenti ambigui (es. 'che proprietà hanno', 'quali sono le sue proprietà'), usa la cronologia dei messaggi inclusa nel prompt per identificare a quale alimento, peso o attività si riferisce l'utente.
"""


def _narrate_base_prompt(bot_label: str) -> str:
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

"""


# One fragment per derived situation, appended to the base prompt by
# `_narrate_system_prompt`. Keeping them separate is what lets a test assert which
# situation the answer was composed for without invoking a model (design.md -
# Decision 2); the branch itself is decided in `calobot.advice.tools`, never here.

_SUGGESTION_COMMON = """\
- Guarda "recent_food" in modo qualitativo (come faresti per la densita' calorica) per
  capire se sembra mancare una fonte proteica o se i pasti recenti sono stati
  prevalentemente ad alta densita', e orienta la proposta di conseguenza. Se
  "no_data" e' true non inventare un pattern: non affermare nulla sulla varieta'
  recente.
- Anche se il bot traccia i macronutrienti (carboidrati, grassi, proteine, fibre) tramite
  il report dedicato, in questo suggerimento non indicare MAI una quantita' in grammi di
  un macronutriente: ragiona solo qualitativamente sulle descrizioni dei cibi, per non
  dare un suggerimento un tono clinico che non e' appropriato in questo contesto.
- Le calorie che attribuisci a un piatto che proponi sono una STIMA, non un dato del
  diario: presentale come approssimative (es. "circa 300 kcal") e non sommarle ne'
  sottrarle ai totali o al budget dell'utente.
- In `suggestion_mode` riporta esattamente il valore di "mode" che trovi nei risultati,
  e in `suggested_kcal_total` la tua stima in kcal del piatto che proponi.
"""

SUGGESTION_FRAGMENT_WITHIN_BUDGET = f"""

SUGGERIMENTO DI UN PASTO - all'utente restano calorie oggi:
- Il risultato di `get_meal_suggestion_context` contiene "remaining_today_kcal": quelle
  sono le calorie che gli restano oggi, gia' calcolate. Riportale esplicitamente nella
  risposta per motivare la proposta, senza ricalcolarle.
- Proponi 1-2 ricette o idee di pasti sani, realistici e italiani le cui calorie stimate
  stiano entro "ceiling_kcal".
{_SUGGESTION_COMMON}"""

SUGGESTION_FRAGMENT_OVER_BUDGET = f"""

SUGGERIMENTO DI UN PASTO - l'utente ha gia' esaurito o superato il budget di oggi:
- NON consigliare di saltare il pasto, di digiunare o di compensare. Rassicuralo: sforare
  ogni tanto e' normale.
- Rispondi in modo empatico e di supporto, poi proponi un'opzione a bassissima densita'
  calorica (meno di 100 kcal per 100 g: brodi caldi leggeri, finocchi, cetrioli, sedano)
  che dia sazieta' e volume.
- La proposta deve restare entro "ceiling_kcal" kcal totali: non proporre nulla di piu'
  sostanzioso, per quanto leggero ti sembri.
{_SUGGESTION_COMMON}"""

SUGGESTION_FRAGMENT_NO_BUDGET = f"""

SUGGERIMENTO DI UN PASTO - il profilo non e' completo, quindi non esiste un budget:
- NON indicare ne' lasciare intendere un numero di calorie rimanenti: per questo utente
  non e' calcolabile, e inventarlo non e' ammesso.
- Proponi comunque 1-2 idee di pasti sani, realistici e italiani, e invitalo a completare
  il profilo se vuole proposte tarate sul suo budget.
{_SUGGESTION_COMMON}"""

_SUGGESTION_FRAGMENTS: dict[SuggestionMode, str] = {
    "within_budget": SUGGESTION_FRAGMENT_WITHIN_BUDGET,
    "over_budget": SUGGESTION_FRAGMENT_OVER_BUDGET,
    "no_budget": SUGGESTION_FRAGMENT_NO_BUDGET,
}


def _narrate_system_prompt(bot_label: str, mode: SuggestionMode | None) -> str:
    """The base prompt plus exactly one situation fragment. `mode is None` - no
    suggestion was asked for - appends nothing, which is the non-prescriptive path
    unchanged."""
    base = _narrate_base_prompt(bot_label)
    if mode is None:
        return base
    return base + _SUGGESTION_FRAGMENTS[mode]


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
    suggestion_mode: Literal["none", "within_budget", "over_budget", "no_budget"] = Field(
        default="none",
        description="Se hai proposto un pasto, riporta esattamente il valore di 'mode' "
        "che hai trovato nei risultati degli strumenti. Resta 'none' per qualsiasi "
        "risposta che non proponga un pasto.",
    )
    suggested_kcal_total: int | None = Field(
        default=None,
        description="La tua stima in kcal del piatto che hai proposto, se ne hai "
        "proposto uno. Null altrimenti.",
    )


COULD_NOT_ANSWER_TEXT = (
    "Non sono riuscito a ricostruire una risposta con i dati disponibili. Puoi provare "
    "a essere piu' specifico, per esempio indicando un periodo preciso?"
)

UNFOUNDED_CLAIM_REPLACEMENT = (
    "Non ho toccato il tuo diario: posso solo leggere i tuoi dati e spiegarteli. Puoi "
    "riformulare la domanda?"
)

# Substituted when a composed suggestion does not match the situation that was derived
# (specs/advice-agent - An answer inconsistent with the determined situation is not
# delivered). These read as answers, not as diagnostics: the user asked something
# reasonable, and a confused meta-reply would serve them worse than a plain suggestion.
SUGGESTION_FALLBACK_TEXT: dict[SuggestionMode, str] = {
    "within_budget": (
        "Oggi ti restano ancora {remaining} kcal. Ti propongo qualcosa di semplice: "
        "del pesce bianco al forno con verdure di stagione, oppure un'insalata di ceci "
        "con pomodorini e un filo d'olio."
    ),
    "over_budget": (
        "Per oggi il budget e' finito, ma non e' il caso di saltare il pasto: capita a "
        "tutti di sforare, e domani si riparte. Se hai fame, vai su qualcosa di molto "
        "leggero come un brodo vegetale caldo, dei finocchi crudi o del sedano."
    ),
    "no_budget": (
        "Per proporti qualcosa di calibrato mi manca ancora qualche dato del tuo "
        "profilo. Intanto un'idea semplice: del pollo alla piastra con verdure grigliate, "
        "oppure una zuppa di legumi. Se completi il profilo posso tararti le proposte "
        "sulle calorie che ti restano."
    ),
}


def _suggestion_fallback(mode: SuggestionMode, remaining: int | None) -> str:
    return SUGGESTION_FALLBACK_TEXT[mode].format(remaining=remaining)


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


class _DerivedSuggestion(NamedTuple):
    mode: SuggestionMode
    ceiling_kcal: int | None
    remaining_kcal: int | None


def _derived_suggestion(tool_results: list[ToolCallResult]) -> _DerivedSuggestion | None:
    """The situation `get_meal_suggestion_context` derived, or None when the user was
    not asking what to eat. Read back off the tool result rather than recomputed, so
    exactly one computation decides which situation applies (specs/advice-agent - The
    suggestion situation is determined outside the language model)."""
    for call in reversed(tool_results):
        if call.tool != "get_meal_suggestion_context":
            continue
        mode = call.result.get("mode")
        if mode not in ("within_budget", "over_budget", "no_budget"):
            continue
        ceiling = call.result.get("ceiling_kcal")
        remaining = call.result.get("remaining_today_kcal")
        return _DerivedSuggestion(
            mode=mode,
            ceiling_kcal=ceiling if isinstance(ceiling, int) else None,
            remaining_kcal=remaining if isinstance(remaining, int) else None,
        )
    return None


def _suggestion_is_inconsistent(result: AdviceAnswer, derived: _DerivedSuggestion) -> bool:
    """Whether a composed answer contradicts the situation that was derived. Checks
    what the model declared about its own answer - see design.md - Decision 4 for why
    that trust boundary is accepted."""
    if result.suggestion_mode != derived.mode:
        return True
    if derived.mode == "over_budget" and derived.ceiling_kcal is not None:
        declared = result.suggested_kcal_total
        return declared is not None and declared > derived.ceiling_kcal
    return False


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

        derived = _derived_suggestion(gather.tool_results)
        narration = TextContent(text=_narration_prompt(raw_text, gather.tool_results, history_context))
        result = await gateway.call_structured(
            step="advice_narrate",
            system_prompt=_narrate_system_prompt(bot_label, derived.mode if derived else None),
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
    if derived is not None and _suggestion_is_inconsistent(result, derived):
        logger.warning(
            "suppressed a suggestion inconsistent with the derived situation "
            "(derived=%s ceiling=%s, declared=%s kcal=%s)",
            derived.mode,
            derived.ceiling_kcal,
            result.suggestion_mode,
            result.suggested_kcal_total,
        )
        return _suggestion_fallback(derived.mode, derived.remaining_kcal)
    return reply
