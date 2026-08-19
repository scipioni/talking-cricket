"""Intent classification. See specs/message-ingestion - Classification of inbound
messages: classification precedes extraction and returns exactly one intent."""

from __future__ import annotations

from calobot.ingestion.schemas import Classification
from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway

SYSTEM_PROMPT = """\
Sei il classificatore di un bot italiano di tracciamento nutrizionale su Telegram.
Classifica il messaggio dell'utente in ESATTAMENTE uno di questi intent:

- food: l'utente ha mangiato o bevuto qualcosa (es. "ho mangiato 10g di noci",
  "un piatto di pasta al pesto")
- weight: l'utente riporta una MISURAZIONE del proprio peso corporeo attuale
  (es. "oggi peso 78kg", "78 e mezzo", "ho perso mezzo chilo")
- activity: l'utente ha svolto un'attività fisica (es. "ho fatto una camminata
  di mezz'ora", "corsa 40 minuti")
- profile: l'utente sta IMPOSTANDO un dato del proprio profilo: sesso, data di
  nascita, altezza, peso obiettivo, livello di attività abituale, o ritmo (es.
  "la mia data di nascita è 16/5/72", "ora il mio peso obiettivo è 74kg", "sono
  alto 178"). Il peso obiettivo NON è una misurazione: "peso obiettivo 74kg" è
  profile, mentre "peso 74kg" (senza "obiettivo") è sempre weight.
- correction: l'utente sta correggendo una voce già registrata (es. "no erano
  20g", "non era pasta ma riso")
- report: l'utente chiede un riepilogo/statistiche (es. "report settimanale",
  "quante calorie ho mangiato oggi?")
- other: qualsiasi altra cosa (saluti, domande generiche, richieste di consiglio)

Se il messaggio contiene più di un intent (es. "ho mangiato una mela e peso
77kg"), scegli l'intent DOMINANTE e riporta in ignored_text il testo verbatim
della parte che non stai classificando, così non viene perso silenziosamente.
Se c'è un solo intent, ignored_text deve essere null. Non inserire MAI l'intero
messaggio in ignored_text: fallo solo se ci sono intent aggiuntivi non classificati.
"""


async def classify(gateway: LLMGateway, content: MessageContent) -> Classification:
    return await gateway.call_structured(
        step="classify",
        system_prompt=SYSTEM_PROMPT,
        content=content,
        schema=Classification,
    )
