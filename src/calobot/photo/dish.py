"""Dish recognition (tasks.md 5.1): identifies the foods visible in a photo, with
no quantities - a photo never establishes quantity (design.md), so every item
this produces still goes through the ordinary clarification loop for its portion,
via the same `food.planner` machinery a typed multi-food message uses."""

from __future__ import annotations

from pydantic import BaseModel

from calobot.ingestion.schemas import FoodExtraction, FoodItemExtraction
from calobot.llm.content import ImageContent
from calobot.llm.gateway import LLMGateway

SYSTEM_PROMPT = """\
Identifica gli alimenti distinti visibili nella foto di un piatto. Per ognuno
riporta solo il nome (in italiano) e, se evidente, il metodo di preparazione
(es. "fritto", "bollito", "al forno"). NON stimare quantità o pesi: la foto non
permette di stabilire la porzione con affidabilità, quella verrà chiesta
separatamente. Se presente, usa anche la didascalia dell'utente come contesto.
"""


class DishItem(BaseModel):
    description: str
    preparation: str | None = None


class DishExtraction(BaseModel):
    items: list[DishItem]


async def extract_dish(gateway: LLMGateway, image: ImageContent) -> DishExtraction:
    return await gateway.call_structured(
        step="extract", system_prompt=SYSTEM_PROMPT, content=image, schema=DishExtraction
    )


def to_food_extraction(dish: DishExtraction) -> FoodExtraction:
    """Adapts a dish identification into the same shape a typed multi-food message
    produces, so it can be handed to `food.planner.build_items` unchanged and
    resolved through the existing clarification loop, one draft per food."""
    return FoodExtraction(
        items=[
            FoodItemExtraction(description=item.description, preparation=item.preparation)
            for item in dish.items
        ],
        when_text=None,
    )
