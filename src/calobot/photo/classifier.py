"""Photo intent classification (tasks.md 2.1-2.3): a small, cheap first call that
routes a photo to the label, barcode, dish or unrecognizable path - mirroring the
text classify-then-extract split in ingestion/classifier.py, and for the same
reason (design.md - Photo classification is a separate, cheap first call).

The label-over-barcode preference (specs/photo-input - Package showing both a
barcode and a label) is resolved inside this single call rather than as a
compound signal: the prompt instructs the model to prefer "label" whenever a
nutrition label is legible, even if a barcode is also visible on the package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from calobot.llm.content import ImageContent
from calobot.llm.gateway import LLMGateway

PhotoKind = Literal["label", "barcode", "dish", "unrecognizable"]

SYSTEM_PROMPT = """\
Classifica la foto ricevuta in ESATTAMENTE una di queste categorie:

- label: la foto mostra una tabella nutrizionale leggibile su una confezione.
  Scegli questa categoria anche se la confezione mostra anche un codice a barre.
- barcode: la foto mostra un codice a barre leggibile, senza una tabella
  nutrizionale leggibile.
- dish: la foto mostra un piatto o un alimento senza confezione.
- unrecognizable: nessuna delle precedenti si applica con sufficiente sicurezza.

Se presente, usa anche la didascalia dell'utente come contesto.
"""


class PhotoClassification(BaseModel):
    kind: PhotoKind


async def classify_photo(gateway: LLMGateway, image: ImageContent) -> PhotoClassification:
    return await gateway.call_structured(
        step="classify",
        system_prompt=SYSTEM_PROMPT,
        content=image,
        schema=PhotoClassification,
    )
