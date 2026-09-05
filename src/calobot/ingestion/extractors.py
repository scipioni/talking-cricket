"""Per-intent extraction. Each call uses a small flat schema (schemas.py) and the
'extract' pipeline step, which can be pointed at a different model than classification
(design.md - Per-step model configuration)."""

from __future__ import annotations

from calobot.ingestion.schemas import (
    ActivityExtraction,
    ClarificationReplyExtraction,
    CorrectionExtraction,
    FoodExtraction,
    NudgesExtraction,
    ProfileEditExtraction,
    ReportExtraction,
    WeightExtraction,
)
from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway

FOOD_PROMPT = """\
Estrai gli alimenti menzionati nel messaggio dell'utente. Se sono menzionati più
alimenti, restituiscili come elementi separati nella lista items.

Per ogni alimento:
- description: il nome dell'alimento così come inteso (in italiano)
- stated_kcal: SOLO se l'utente indica direttamente un valore di calorie/kcal
  (es. "100kcal di melanzane sott'olio" -> 100) - in questo caso NON compilare
  quantity_grams né quantity_count, anche se nel messaggio appare un solo numero
- quantity_grams: SOLO se la quantità è esplicitamente data in grammi o millilitri
- quantity_count: SOLO se la quantità è espressa come un numero di unità
  numerabili, incluso "un/una/uno" che vale 1 (es. "due mele" -> 2, "una pesca" -> 1)
- count_unit_hint: SEMPRE quando quantity_count è compilato, il singolare dell'unità
  effettivamente contata, anche quando ripete description (es. "una pesca" ->
  "pesca", "2 fette di pane" -> "fetta di pane", "un cucchiaio di olio" -> "cucchiaio")
- typical_unit_weight_g: SOLO se quantity_count è compilato, il peso tipico in
  grammi di UNA singola unità di questo alimento (es. "mela" -> 180, "mandorla" -> 1.2)
- household_measure: SOLO se la quantità è espressa in modo vago/non numerabile
  (es. "un piatto", "una porzione", "un po'") - NON stimare i grammi in questo caso
- portion_small_g, portion_medium_g, portion_generous_g: SOLO se la quantità è vaga
  o assente (quindi anche quando l'utente ha solo nominato l'alimento, senza una
  misura domestica), tre stime in grammi (piccola/media/abbondante) plausibili per
  QUESTO alimento specifico - una salsa e un piatto di pasta non condividono la stessa
  scala di porzioni, quindi calibra i valori sul tipo di alimento (es. un condimento va
  stimato in decine di grammi, un primo piatto in centinaia). Sono solo proposte
  tra cui l'utente sceglie, mai un peso assunto.
- preparation: il metodo di preparazione se menzionato (es. "fritto", "bollito",
  "al forno"), altrimenti null
- preparation_material_but_unstated: true SOLO se il modo di preparazione di questo
  alimento cambia sensibilmente le calorie (es. pollo fritto vs bollito) e non è
  stato specificato; false altrimenti, incluso quando la preparazione non è
  rilevante per le calorie
- preparation_options: SOLO se preparation_material_but_unstated è true, da 2 a 4
  preparazioni plausibili PER QUESTO alimento specifico, in italiano e in forma
  breve (es. per un uovo: ["sodo", "strapazzato", "in camicia", "fritto"]);
  lista vuota altrimenti

when_text: quando è stato consumato, se indicato (es. "ieri sera"), altrimenti null.
"""

WEIGHT_PROMPT = """\
Estrai il testo relativo al peso corporeo dal messaggio dell'utente.
value_text: riporta ESATTAMENTE la parte del messaggio che indica il valore o la
variazione di peso, senza interpretarla (es. "78 e mezzo", "ho perso mezzo chilo",
"stamattina 77,4").
when_text: il giorno a cui si riferisce, se indicato (es. "ieri"), altrimenti null.
"""

ACTIVITY_PROMPT = """\
Estrai l'attività fisica menzionata nel messaggio dell'utente.
activity_description: il nome dell'attività in italiano (es. "camminata", "corsa").
duration_minutes: la durata in minuti, se indicata, altrimenti null.
intensity_text: intensità o ritmo se indicato (es. "svelta", "leggera"), altrimenti null.
when_text: quando è stata svolta, se indicato, altrimenti null.
"""

PROFILE_EDIT_PROMPT = """\
L'utente sta impostando un dato del proprio profilo (non una misurazione da
registrare). Identifica quale di questi campi sta impostando:
- sesso (maschio o femmina)
- data_nascita (data di nascita o età)
- altezza_cm (altezza)
- peso_obiettivo_kg (peso obiettivo, il peso che vuole raggiungere - NON il peso
  attuale/corporeo, che non è un campo di questo tipo)
- livello_attivita (livello di attività abituale)
- ritmo (ritmo desiderato per raggiungere l'obiettivo)

field: il campo tra questi impostato dal messaggio, oppure null se non è chiaro quale.
value_text: il valore indicato, verbatim (senza interpretarlo), es. "16/5/72", "74kg".
"""

CORRECTION_PROMPT = """\
L'utente sta correggendo una voce già registrata. Riporta in correction_text il
testo verbatim del messaggio, senza interpretarlo.
"""

REPORT_PROMPT = """\
L'utente chiede un report/riepilogo. Estrai:
period_text: il periodo richiesto in linguaggio naturale (es. "questa settimana",
"questo mese"), oppure null se non specificato.
topic: "food" se chiede solo di calorie/cibo, "weight" se chiede solo di peso,
"activity" se chiede solo di attività, "macros" se chiede di proteine, grassi,
carboidrati o fibre (singolarmente o come distribuzione/ripartizione), altrimenti
"all".
"""


async def extract_food(gateway: LLMGateway, content: MessageContent) -> FoodExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=FOOD_PROMPT, content=content, schema=FoodExtraction
    )


async def extract_weight(gateway: LLMGateway, content: MessageContent) -> WeightExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=WEIGHT_PROMPT, content=content, schema=WeightExtraction
    )


async def extract_activity(gateway: LLMGateway, content: MessageContent) -> ActivityExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=ACTIVITY_PROMPT, content=content, schema=ActivityExtraction
    )


async def extract_profile_edit(
    gateway: LLMGateway, content: MessageContent
) -> ProfileEditExtraction:
    return await gateway.call_structured(
        step="extract",
        system_prompt=PROFILE_EDIT_PROMPT,
        content=content,
        schema=ProfileEditExtraction,
    )


async def extract_correction(gateway: LLMGateway, content: MessageContent) -> CorrectionExtraction:
    return await gateway.call_structured(
        step="extract",
        system_prompt=CORRECTION_PROMPT,
        content=content,
        schema=CorrectionExtraction,
    )


async def extract_report(gateway: LLMGateway, content: MessageContent) -> ReportExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=REPORT_PROMPT, content=content, schema=ReportExtraction
    )


NUDGES_PROMPT = """\
L'utente sta impostando la preferenza sui messaggi proattivi del bot. Estrai:
action: "enable" se vuole riceverli ("voglio ricevere le notifiche", "avvisami se
smetto di registrare"), "disable" se non li vuole più ("basta notifiche", "non
scrivermi più per tua iniziativa").
"""


async def extract_nudges(gateway: LLMGateway, content: MessageContent) -> NudgesExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=NUDGES_PROMPT, content=content, schema=NudgesExtraction
    )


async def extract_clarification_reply(
    gateway: LLMGateway, content: MessageContent, *, field_being_asked: str, question_text: str
) -> ClarificationReplyExtraction:
    prompt = (
        "L'utente sta rispondendo a questa domanda del bot: "
        f'"{question_text}"\n'
        f"Estrai il valore per il campo '{field_being_asked}' dalla risposta. "
        "Se la risposta non contiene un valore utilizzabile, restituisci null."
    )
    return await gateway.call_structured(
        step="extract",
        system_prompt=prompt,
        content=content,
        schema=ClarificationReplyExtraction,
    )
