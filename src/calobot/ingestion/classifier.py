"""Intent classification. See specs/message-ingestion - Classification of inbound
messages: classification precedes extraction and returns exactly one intent."""

from __future__ import annotations

from calobot.ingestion.schemas import Classification
from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway

SYSTEM_PROMPT = """\
Sei il classificatore di un bot italiano di tracciamento nutrizionale su Telegram.
Classifica il messaggio dell'utente in ESATTAMENTE uno di questi intent:

- food: l'utente ha mangiato o bevuto qualcosa.
  ESEMPI: "ho mangiato 10g di noci", "un piatto di pasta al pesto".
  IMPORTANTE: Cibi vaghi o senza quantità vanno classificati come food (es. "boh, pasta?", "ho fame, mi faccio una mela").
- weight: l'utente riporta una MISURAZIONE del proprio peso corporeo attuale.
  ESEMPI: "oggi peso 78kg", "78 e mezzo", "ho perso mezzo chilo".
- activity: l'utente ha svolto un'attività fisica.
  ESEMPI: "ho fatto una camminata di mezz'ora", "corsa 40 minuti".
- profile: l'utente sta IMPOSTANDO un dato del proprio profilo: sesso, data di
  nascita, altezza, peso obiettivo, livello di attività abituale, o ritmo.
  ESEMPI: "ora il mio peso obiettivo è 74kg", "sono alto 178". 
  Il peso obiettivo NON è una misurazione: "peso obiettivo 74kg" è profile, mentre "peso 74kg" (senza "obiettivo") è sempre weight.
- correction: l'utente sta correggendo una voce già registrata.
  ESEMPI: "no erano 20g", "non era pasta ma riso".
- report: l'utente chiede un report, un riepilogo o statistiche standard dei propri log (es. "report settimanale", "riepilogo di oggi", "statistiche peso").
- other: qualsiasi altra cosa puramente conversazionale, domande generiche, richieste di consiglio, o domande aperte/analitiche sul proprio andamento che NON includono un alimento, un peso o un'attività da registrare (es. domande sul funzionamento del bot, richieste di parere o stime teoriche sul peso perso basati sul deficit, come "quanti kg avrei dovuto perdere?", "perché non dimagrisco?", "sto andando bene?").

GESTIONE MULTI-INTENT E CONTRADDIZIONI:
- Se il messaggio contiene CONVERSAZIONE e un intent (es. "ho mangiato una mela, ecco i log", "ciao, 100g di pollo"), estrai l'intent ("food") e TRASCURA COMPLETAMENTE la conversazione (imposta ignored_text a null).
- Se il messaggio contiene PIÙ INTENT REGISTRABILI DIVERSI E INDIPENDENTI (es. "ho mangiato una mela e poi ho corso 30 minuti"), scegli l'intent DOMINANTE (food) e riporta in `ignored_text` SOLO il testo della parte REGISTRABILE che non stai classificando (es. "e poi ho corso 30 minuti").
- Se il messaggio contiene una CONTRADDIZIONE INTERNA o un cambio di idea sulla STESSA COSA (es. "stavo per registrare la pizza ma ho mangiato un'insalata"), NON usare `ignored_text`. Classifica l'intent FINALE ("food" per l'insalata) e imposta `ignored_text` a null.

REGOLA FONDAMENTALE SU IGNORED_TEXT:
`ignored_text` va usato ESCLUSIVAMENTE per intent registrabili aggiuntivi (altri cibi, pesi, attività). È severamente VIETATO usare `ignored_text` per:
1. Convenevoli, saluti ("ciao", "grazie")
2. Frasi di contesto o fluff conversazionale ("ecco i log", "li ho registrati nei logs", "ho segnato")
3. Intenti scartati dall'utente per ripensamento
4. Filler ("boh", "uhm", "allora")
Se l'unica cosa extra oltre all'intent dominante è una di queste, DEVI impostare `ignored_text` a null.
"""


async def classify(gateway: LLMGateway, content: MessageContent) -> Classification:
    return await gateway.call_structured(
        step="classify",
        system_prompt=SYSTEM_PROMPT,
        content=content,
        schema=Classification,
    )
