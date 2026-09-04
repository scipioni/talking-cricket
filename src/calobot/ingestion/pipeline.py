"""Message pipeline: classify -> extract -> draft/clarify -> resolve -> store.
Ties together the domain modules (food/activity/weight/corrections/reporting)
behind the single per-user entry point the telegram layer calls.

See specs/message-ingestion in full, and design.md - Drafts and the clarification
loop for the 'new message while a draft is open' policy implemented here.
"""

from __future__ import annotations

import base64
import datetime as dt
import re

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.activity import planner as activity_planner
from calobot.advice.agent import answer as advice_answer
from calobot.advice.memory import previous_unresolved_tip, record_advice
from calobot.corrections.service import amend_food_quantity
from calobot.food import planner as food_planner
from calobot.food.resolver import normalize_description, resolve_food_energy, write_resolution
from calobot.ingestion import drafts
from calobot.ingestion.classifier import classify
from calobot.ingestion.extractors import (
    extract_activity,
    extract_food,
    extract_profile_edit,
    extract_report,
    extract_weight,
)
from calobot.ingestion.responses import OutgoingMessage
from calobot.ingestion.schemas import FoodExtraction, FoodItemExtraction
from calobot.llm.content import ImageContent, MessageContent, TextContent
from calobot.llm.gateway import LLMGateway
from calobot.persistence.models import ActivityEntry, AdviceSurface, DraftIntent, FoodEntry, Provenance, User
from calobot.persistence.repository import get_entries_in_range, get_last_entry, get_latest_weight
from calobot.persistence.timeutil import period_bounds_utc, today_in_timezone
from calobot.photo.barcode import decode_barcode
from calobot.photo.classifier import classify_photo
from calobot.photo.dish import extract_dish, to_food_extraction
from calobot.photo.label import LabelUnreadable, resolve_from_label
from calobot.photo.openfoodfacts import ATTRIBUTION, LookupUnavailable, lookup_product
from calobot.profile.budget import is_goal_weight_unsafe
from calobot.profile.onboarding import OPTIONS as PROFILE_OPTIONS
from calobot.profile.onboarding import QUESTIONS as PROFILE_QUESTIONS
from calobot.profile.onboarding import parse_field_raw
from calobot.profile.service import (
    FIELD_LABELS,
    GOAL_WEIGHT_UNSAFE_MESSAGE,
    apply_onboarding_field,
    current_budget,
    describe_profile_change,
    format_field_value,
)
from calobot.reporting.aggregation import (
    build_activity_report,
    build_daily_kcal_breakdown,
    build_daily_macro_breakdown,
    build_food_report,
    build_macro_report,
    build_weight_report,
)
from calobot.reporting.charts import render_calorie_chart, render_macro_chart, render_weight_chart
from calobot.reporting.dietician import (
    DieticianReview,
    build_daily_advice,
    build_dietitian_review,
    format_dietician_review,
)
from calobot.reporting.periods import parse_period
from calobot.settings import Settings
from calobot.weight.normalizer import normalize_weight_text
from calobot.weight.service import NeedsConfirmation, Rejected, Stored, apply_weight

PHOTO_NOTICE = (
    "Le foto vengono elaborate e non conservate: uso l'immagine solo per "
    "interpretarla, poi la scarto.\n\n"
)

LOGGABLE_INTENTS = {"food", "weight", "activity", "profile", "report", "correction"}

_QUANTITY_WITH_GRAMS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:g|gr|grammi)\b")
_CORRECTION_MARKERS = [
    "non era",
    "non erano",
    "era invece",
    "erano invece",
    "veramente era",
    "in realtà",
    "no era",
    "no erano",
]


ABANDON_OPTION = "❌ lascia perdere"

# Wording for each successive ask about the same field. A user who did not understand
# the question is shown a differently worded one, which is the only chance the second
# attempt has of doing better than the first - the loop used to repeat "Non ho capito."
# verbatim until the draft expired.
#
# A fixed rotation rather than a model call: rephrasing costs latency at the exact
# moment the user is already stuck, to produce a sentence that can be written in
# advance, and it would make the wording non-deterministic for scenarios to assert on.
_REASK_PREFIXES = (
    "Non ho capito.",
    "Scusa, non riesco a ricavare il dato. Puoi usare uno dei pulsanti?",
    "Ancora non ci siamo: scegli un'opzione qui sotto oppure scrivi un numero in grammi.",
)


def _reask_prefix(attempt: int) -> str:
    """`attempt` is how many unusable answers have been given so far, so attempt 1 is
    the first re-ask. Clamped rather than wrapped: the give-up limit is reached before
    the rotation runs out (asserted in the tests), and clamping keeps the last, most
    explicit wording if the limit is ever configured higher."""
    return _REASK_PREFIXES[min(attempt, len(_REASK_PREFIXES)) - 1]


def _serialize_profile_value(value) -> str:
    """The draft payload is stored as JSON, which a `dt.date` doesn't round-trip
    through - so a parsed value is kept in the same string form `parse_field_raw`
    accepts back, and re-parsed at confirm time rather than stored typed. `isoformat`
    is one of the formats `parse_data_nascita` already tries, so this recovers the
    same date; every other field's value is already JSON-safe as a plain str."""
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def _single_food_extraction(description: str) -> FoodExtraction:
    """A one-food extraction with no quantity, in the same shape a typed message
    produces - used by the label and barcode photo paths so they feed the ordinary
    food draft/clarification loop unchanged (design.md - Photo-derived entries are
    ordinary entries)."""
    return FoodExtraction(items=[FoodItemExtraction(description=description)], when_text=None)


def _without(text: str, aside: str | None) -> str:
    """The message with the set-aside part removed, so what remains is the dominant
    content. Falls back to the whole message when the aside is not a literal slice of
    it - the classifier paraphrases sometimes, and a paraphrase is not something to
    subtract by string surgery."""
    if not aside:
        return text.strip()
    lowered, needle = text.lower(), aside.strip().lower()
    if needle not in lowered:
        return text.strip()
    start = lowered.index(needle)
    remainder = text[:start] + text[start + len(needle) :]
    return remainder.strip(" ,.;:-\n\t")


class MessagePipeline:
    def __init__(self, session: AsyncSession, gateway: LLMGateway, settings: Settings, user: User):
        self.session = session
        self.gateway = gateway
        self.settings = settings
        self.user = user
        self.tz = settings.timezone

    async def handle(self, content: MessageContent, raw_text: str) -> list[OutgoingMessage]:
        draft = await drafts.get_open_draft(self.session, self.user.id)
        if draft is not None and drafts.is_expired(draft, self.settings.draft_expiry_minutes):
            await drafts.discard_draft(self.session, self.user.id)
            draft = None

        if draft is not None:
            return await self._handle_with_open_draft(draft, content, raw_text)

        if isinstance(content, ImageContent):
            return await self._handle_photo(content)

        return await self._handle_fresh(content, raw_text)

    # -- fresh dispatch ---------------------------------------------------

    async def _handle_fresh(self, content: MessageContent, raw_text: str) -> list[OutgoingMessage]:
        classification = await classify(self.gateway, content)
        messages: list[OutgoingMessage] = []
        if classification.ignored_text:
            messages.append(
                OutgoingMessage(
                    text=(
                        f'Ho notato anche: "{classification.ignored_text}" - non l\'ho '
                        "registrato, scrivimelo di nuovo separatamente se vuoi tracciarlo."
                    )
                )
            )

        intent: str = classification.intent
        if intent == "other" and classification.ignored_text:
            intent, content = await self._reroute_self_contradiction(
                classification, content, raw_text
            )

        if intent == "food":
            messages += await self._start_food(content)
        elif intent == "weight":
            messages += await self._start_weight(content)
        elif intent == "activity":
            messages += await self._start_activity(content)
        elif intent == "profile":
            messages += await self._start_profile_edit(content)
        elif intent == "correction":
            messages += await self._handle_correction(raw_text)
        elif intent == "report":
            messages += await self._handle_report(content)
        else:
            reply = await advice_answer(
                self.session,
                self.gateway,
                self.user,
                self.tz,
                raw_text,
                content,
                self.settings.bot_label,
                self.settings.llm_advice_max_rounds,
            )
            messages.append(OutgoingMessage(text=reply))
        return messages

    async def _reroute_self_contradiction(
        self, classification, content: MessageContent, raw_text: str
    ) -> tuple[str, MessageContent]:
        """A classification of "conversation" that also reports loggable text it set
        aside contradicts itself, and the contradiction is the routing signal.

        This is what produced the worst failure the simulation harness found: a
        message stating a meal, a weight and a run came back as
        `{"intent": "other", "ignored_text": "peso oggi 89.3 kg, ho corso 4 km"}` -
        conversation, while reporting the parts it had chosen not to treat as
        dominant. The conversational reply then announced it had recorded all three
        and stored none (specs/message-ingestion - A message carrying a loggable
        intent is not conversation).

        The dominant content is the *remainder*, not the ignored text: the ignored
        text is what was set aside. Re-classifying the ignored text would have logged
        the weight and lost the meal.

        Costs one extra model call, and only in this contradictory case - an ordinary
        greeting reports no ignored text and never reaches here.
        """
        remainder = _without(raw_text, classification.ignored_text)
        if not remainder or not isinstance(content, TextContent):
            return classification.intent, content

        second = await classify(self.gateway, TextContent(text=remainder))
        if second.intent == "other":
            # The classifier stands by conversation once the aside is removed. Nothing
            # to log; the reply still has to survive the claim guard.
            return classification.intent, content

        return second.intent, TextContent(text=remainder)

    # -- photo --------------------------------------------------------------

    async def _first_photo_notice(self) -> str:
        """Prefixed onto the first photo reply only, so photos are established as
        'processed, not kept' and as still needing a portion answer before the user
        is surprised by either (tasks.md 7.1, 7.2)."""
        if self.user.photo_notice_shown:
            return ""
        self.user.photo_notice_shown = True
        await self.session.flush()
        return PHOTO_NOTICE

    async def _handle_photo(self, content: ImageContent) -> list[OutgoingMessage]:
        notice = await self._first_photo_notice()
        raw_bytes = base64.b64decode(content.base64_data)
        classification = await classify_photo(self.gateway, content)

        if classification.kind == "label":
            messages = await self._handle_label_photo(content)
        elif classification.kind == "barcode":
            messages = await self._handle_barcode_photo(raw_bytes)
        elif classification.kind == "dish":
            messages = await self._handle_dish_photo(content)
        else:
            messages = [
                OutgoingMessage(
                    text=(
                        "Non ho riconosciuto niente in questa foto: prova con una foto più "
                        "chiara, oppure scrivimi cosa hai mangiato."
                    )
                )
            ]

        if notice and messages:
            messages[0] = OutgoingMessage(
                text=notice + messages[0].text,
                buttons=messages[0].buttons,
                photo_png=messages[0].photo_png,
                entry_ref=messages[0].entry_ref,
            )
        return messages

    async def _handle_label_photo(self, content: ImageContent) -> list[OutgoingMessage]:
        try:
            result = await resolve_from_label(self.session, self.gateway, content)
        except LabelUnreadable:
            return [
                OutgoingMessage(
                    text=(
                        "Non sono riuscito a leggere l'etichetta con sicurezza: prova con "
                        "una foto più chiara e a fuoco, oppure scrivimi l'alimento."
                    )
                )
            ]
        items = food_planner.build_items(_single_food_extraction(result.display_name_it))
        return await self._start_food_from_items(items)

    async def _handle_barcode_photo(self, raw_bytes: bytes) -> list[OutgoingMessage]:
        code = decode_barcode(raw_bytes)
        if code is None:
            return [
                OutgoingMessage(
                    text=(
                        "Non sono riuscito a leggere il codice a barre: prova con una foto "
                        "più chiara, o fotografa l'etichetta nutrizionale."
                    )
                )
            ]
        try:
            product = await lookup_product(code, self.settings)
        except LookupUnavailable:
            return [
                OutgoingMessage(
                    text=(
                        "Il servizio di ricerca prodotti è temporaneamente non disponibile: "
                        "prova a fotografare l'etichetta nutrizionale."
                    )
                )
            ]
        if product is None:
            return [
                OutgoingMessage(
                    text=(
                        "Non ho trovato questo prodotto nel database: prova a fotografare "
                        "l'etichetta nutrizionale."
                    )
                )
            ]
        key = normalize_description(product.display_name_it)
        await write_resolution(
            self.session,
            key=key,
            kcal_per_100g=product.kcal_per_100g,
            provenance=Provenance.off,
            display_name_it=product.display_name_it,
        )
        items = food_planner.build_items(_single_food_extraction(product.display_name_it))
        return await self._start_food_from_items(items)

    async def _handle_dish_photo(self, content: ImageContent) -> list[OutgoingMessage]:
        dish = await extract_dish(self.gateway, content)
        if not dish.items:
            return [
                OutgoingMessage(
                    text=(
                        "Non ho riconosciuto alimenti in questa foto: prova con una foto più "
                        "chiara, oppure scrivimi cosa hai mangiato."
                    )
                )
            ]
        items = food_planner.build_items(to_food_extraction(dish))
        return await self._start_food_from_items(items)

    # -- open-draft dispatch ------------------------------------------------

    def _clarification_message(self, clarification, *, attempt: int = 0) -> OutgoingMessage:
        """The one place a clarification is turned into a message.

        Counting, varied wording and the visible way out all attach here. They used to
        be spread over three call sites that built the message themselves, which is
        part of why "ask again" drifted from "ask again differently" (design.md - One
        place assembles a clarification message).
        """
        text = clarification.question_text
        if attempt > 0:
            text = f"{_reask_prefix(attempt)} {text}"
        return OutgoingMessage(
            text=text,
            buttons=[*clarification.options, ABANDON_OPTION],
        )

    async def _give_up_on_draft(self, draft, item) -> list[OutgoingMessage]:
        """Stop asking, discard, store nothing, and name what was dropped.

        Naming it matters: after several exchanges about one portion, "non ho
        registrato niente" without saying *what* leaves the user unsure whether an
        earlier entry vanished too.
        """
        described = item.get("description") or item.get("activity_description") or "la voce"
        await drafts.discard_draft(self.session, self.user.id)
        return [
            OutgoingMessage(
                text=(
                    f"Lasciamo perdere: non ho registrato {described}, perché non sono "
                    "riuscito a capire la quantità. Se vuoi, riscrivimelo con la "
                    'quantità, per esempio "150g di riso".'
                )
            )
        ]

    async def _abandon_draft(self, draft) -> list[OutgoingMessage]:
        """A user-initiated abandon (the "lascia perdere" button), as opposed to
        `_give_up_on_draft`'s give-up-after-repeated-failures. Must not claim nothing
        was recorded when earlier items in the same draft already were - a dish photo
        with several foods stores each as soon as its portion is known, so an abandon
        on food 2 of 3 leaves food 1 stored (tasks.md 5.3)."""
        remaining = drafts.all_items(draft)[draft.payload["current_index"] :]
        described: list[str] = [
            d
            for item in remaining
            if (d := item.get("description") or item.get("activity_description"))
        ]
        await drafts.discard_draft(self.session, self.user.id)
        if not described:
            return [OutgoingMessage(text="Va bene, non ho registrato niente.")]
        text = "Va bene, non ho registrato: " + ", ".join(described) + "."
        return [OutgoingMessage(text=text)]

    async def _handle_with_open_draft(
        self, draft, content: MessageContent, raw_text: str
    ) -> list[OutgoingMessage]:
        if draft.intent == DraftIntent.weight:
            return await self._handle_weight_confirmation(draft, raw_text)
        if draft.intent == DraftIntent.correction:
            return await self._handle_correction_confirmation(draft, content, raw_text)
        if draft.intent == DraftIntent.profile:
            return await self._handle_profile_draft_answer(draft, raw_text)

        ALLOWED_PORTION_WORDS = {
            # Units
            "g", "gr", "grammi", "grammo", "kg", "kilo", "chili", "chilo", "etti", "etto", "hg", "h", "ore", "ora", "min", "minuti", "minuto",
            # Option adjectives
            "piccolo", "piccola", "medio", "media", "abbondante", "generoso", "generosa", "grande", "scarsi", "scarsa", "scarso",
            # Prepositions / Filler / Verbs
            "circa", "quasi", "all'incirca", "all", "incirca", "di", "da", "pesava", "pesano", "era", "erano", "sono", "un", "una", "uno", "e", "mezza", "mezzo", "più", "o", "meno", "piu", "le", "la", "il", "lo", "i", "gli", "per", "con", "a",
            # Number words
            "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta", "cento"
        }

        planner = food_planner if draft.intent == DraftIntent.food else activity_planner
        field = draft.awaiting_field
        item = drafts.current_item(draft)

        # Checked before the answer is parsed, so it can never be read as a quantity.
        if raw_text.strip() == ABANDON_OPTION:
            return await self._abandon_draft(draft)

        # Intercept fresh intents before trying to parse the answer, to avoid eagerly
        # reading quantities from completely unrelated new food/activity/weight logging.
        is_button_tap = False
        clarification = await planner.check_item(self.session, item)
        if clarification and clarification.options:
            if raw_text.strip() in clarification.options:
                is_button_tap = True

        # Check if the user's message is a simple portion/duration answer
        is_simple_ans = is_button_tap
        if not is_simple_ans:
            # Check if all words are within allowed portion-size/duration words
            cleaned = re.sub(r"[0-9.,~()'\-`’]", " ", raw_text.lower())
            words = [w for w in cleaned.split() if w]
            is_simple_ans = len(words) > 0 and all(w in ALLOWED_PORTION_WORDS for w in words)

        classification = None
        if not is_simple_ans:
            try:
                classification = await classify(self.gateway, content)
                is_fresh_intent = False

                if classification.intent in LOGGABLE_INTENTS:
                    if classification.intent not in ("food", "activity"):
                        is_fresh_intent = True
                    elif classification.intent == "food":
                        if draft.intent != DraftIntent.food:
                            is_fresh_intent = True
                        else:
                            extraction = await extract_food(self.gateway, content)
                            if extraction.items:
                                new_food_desc = extraction.items[0].description
                                if new_food_desc and new_food_desc.strip():
                                    draft_desc = item.get("description", "").lower().strip()
                                    new_desc = new_food_desc.lower().strip()
                                    if draft_desc not in new_desc and new_desc not in draft_desc:
                                        is_fresh_intent = True
                    elif classification.intent == "activity":
                        if draft.intent != DraftIntent.activity:
                            is_fresh_intent = True
                        else:
                            extraction = await extract_activity(self.gateway, content)
                            new_act_desc = extraction.activity_description
                            if new_act_desc and new_act_desc.strip():
                                draft_act = item.get("activity_description", "").lower().strip()
                                new_act = new_act_desc.lower().strip()
                                if draft_act not in new_act and new_act not in draft_act:
                                    is_fresh_intent = True

                if is_fresh_intent:
                    await drafts.discard_draft(self.session, self.user.id)
                    notice = OutgoingMessage(
                        text="Ho annullato la richiesta precedente per gestire questo nuovo messaggio."
                    )
                    return [notice, *await self._handle_fresh(content, raw_text)]
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error("Error checking fresh intent: %s", exc)

        resolved_before = dict(item.get("resolved", {}))
        updated_item = planner.apply_answer(item, field, raw_text)
        resolved_after = updated_item.get("resolved", {})
        answered = field in resolved_after and resolved_after.get(field) != resolved_before.get(
            field
        )

        if not answered:
            if classification is None:
                classification = await classify(self.gateway, content)
            if classification.intent in LOGGABLE_INTENTS:
                await drafts.discard_draft(self.session, self.user.id)
                notice = OutgoingMessage(
                    text="Ho annullato la richiesta precedente per gestire questo nuovo messaggio."
                )
                return [notice, *await self._handle_fresh(content, raw_text)]
            attempt = await drafts.record_failed_attempt(self.session, draft)
            if attempt >= self.settings.clarification_attempt_limit:
                return await self._give_up_on_draft(draft, item)

            clarification = await planner.check_item(self.session, item)
            return [self._clarification_message(clarification, attempt=attempt)]

        await drafts.reset_attempts(self.session, draft)
        await drafts.replace_current_item(self.session, draft, updated_item)
        if draft.intent == DraftIntent.food:
            return await self._advance_food_draft(draft)
        return await self._advance_activity_draft(draft)

    # -- food -----------------------------------------------------------

    async def _start_food(self, content: MessageContent) -> list[OutgoingMessage]:
        extraction = await extract_food(self.gateway, content)
        items = food_planner.build_items(extraction)
        draft = await drafts.create_draft(self.session, self.user.id, DraftIntent.food, items)
        return await self._advance_food_draft(draft)

    async def _start_food_from_items(self, items: list) -> list[OutgoingMessage]:
        """Shared by the label, barcode and dish photo paths: each produces one or
        more food items with no quantity, which then go through the ordinary food
        draft/clarification loop exactly like a typed message would (design.md -
        Photo-derived entries are ordinary entries)."""
        draft = await drafts.create_draft(self.session, self.user.id, DraftIntent.food, items)
        return await self._advance_food_draft(draft)

    async def _advance_food_draft(self, draft) -> list[OutgoingMessage]:
        messages: list[OutgoingMessage] = []
        while drafts.has_more_items(draft):
            item = drafts.current_item(draft)
            clarification = await food_planner.check_item(self.session, item)
            await drafts.replace_current_item(self.session, draft, item)
            if clarification is not None:
                await drafts.set_awaiting_field(self.session, draft, clarification.field)
                messages.append(self._clarification_message(clarification))
                return messages
            finalized = await food_planner.finalize_item(
                self.session, self.gateway, self.user.id, item, self.tz
            )
            messages.append(self._food_confirmation(finalized))
            await drafts.advance_to_next_item(self.session, draft)
        await drafts.discard_draft(self.session, self.user.id)
        return messages

    def _food_confirmation(self, finalized) -> OutgoingMessage:
        entry = finalized.entry
        if finalized.kcal_is_stated:
            text = f"Registrato: {entry.description} - {entry.kcal:.0f} kcal"
            if entry.grams is not None:
                text += f" (~{entry.grams:.0f}g stimati)"
            else:
                text += " (grammi non stimabili)"
        else:
            text = f"Registrato: {entry.description} {entry.grams:.0f}g - {entry.kcal:.0f} kcal"
        if finalized.is_estimate:
            text += " (stima)"
        if entry.provenance == Provenance.etichetta:
            text += " (da etichetta)"
        elif entry.provenance == Provenance.off:
            text += f" (da Open Food Facts)\n{ATTRIBUTION}"
        if finalized.quantity_is_estimated_from_count:
            text += f" [porzione stimata: {entry.grams:.0f}g]"
        return OutgoingMessage(text=text, entry_ref=("food", entry.id))

    # -- activity ---------------------------------------------------------

    async def _start_activity(self, content: MessageContent) -> list[OutgoingMessage]:
        weight = await get_latest_weight(self.session, self.user.id)
        if weight is None:
            return [
                OutgoingMessage(
                    text="Per calcolare le calorie di un'attività mi serve prima il tuo peso attuale: scrivimelo."
                )
            ]
        extraction = await extract_activity(self.gateway, content)
        items = activity_planner.build_items(extraction)
        draft = await drafts.create_draft(self.session, self.user.id, DraftIntent.activity, items)
        return await self._advance_activity_draft(draft)

    async def _advance_activity_draft(self, draft) -> list[OutgoingMessage]:
        messages: list[OutgoingMessage] = []
        weight = await get_latest_weight(self.session, self.user.id)
        if weight is None:
            await drafts.discard_draft(self.session, self.user.id)
            return [
                OutgoingMessage(
                    text="Mi serve il tuo peso attuale per le calorie: scrivimelo e ripeti l'attività."
                )
            ]
        while drafts.has_more_items(draft):
            item = drafts.current_item(draft)
            clarification = await activity_planner.check_item(self.session, item)
            await drafts.replace_current_item(self.session, draft, item)
            if clarification is not None:
                await drafts.set_awaiting_field(self.session, draft, clarification.field)
                messages.append(self._clarification_message(clarification))
                return messages
            finalized = await activity_planner.finalize_item(
                self.session, self.gateway, self.user.id, item, weight.kg, self.tz
            )
            messages.append(self._activity_confirmation(finalized))
            await drafts.advance_to_next_item(self.session, draft)
        await drafts.discard_draft(self.session, self.user.id)
        return messages

    def _activity_confirmation(self, finalized) -> OutgoingMessage:
        entry = finalized.entry
        text = (
            f"Registrato: {entry.activity} {entry.duration_minutes:.0f} min "
            f"- ~{entry.kcal:.0f} kcal"
        )
        if finalized.is_estimate:
            text += " (stima)"
        return OutgoingMessage(text=text, entry_ref=("activity", entry.id))

    # -- weight -----------------------------------------------------------

    async def _start_weight(self, content: MessageContent) -> list[OutgoingMessage]:
        extraction = await extract_weight(self.gateway, content)
        normalization = await normalize_weight_text(self.gateway, extraction.value_text)
        result = await apply_weight(
            self.session, self.user, normalization, extraction.when_text, self.tz
        )
        return await self._respond_to_weight_result(result, extraction.when_text)

    async def _respond_to_weight_result(self, result, when_text: str | None):
        if isinstance(result, Rejected):
            if result.reason == "no_previous_weight":
                return [
                    OutgoingMessage(
                        text="Non ho un peso precedente a cui riferirmi: dimmi il tuo peso attuale?"
                    )
                ]
            return [OutgoingMessage(text="Il peso indicato non è in un intervallo plausibile.")]

        if isinstance(result, NeedsConfirmation):
            draft = await drafts.create_draft(
                self.session,
                self.user.id,
                DraftIntent.weight,
                [{"proposed_kg": result.proposed_kg, "when_text": when_text, "resolved": {}}],
            )
            await drafts.set_awaiting_field(self.session, draft, "confirm_jump")
            return [
                OutgoingMessage(
                    text=(
                        f"Confermi {result.proposed_kg:.1f} kg? Sembra una variazione "
                        "piuttosto ampia rispetto all'ultima misurazione."
                    ),
                    buttons=["sì", "no"],
                )
            ]

        assert isinstance(result, Stored)
        text = f"Peso registrato: {result.entry.kg:.1f} kg"
        if result.replaced_previous:
            text += " (ho sostituito il valore precedente di oggi)"
        messages = [OutgoingMessage(text=text, entry_ref=("weight", result.entry.id))]
        if result.goal_reached:
            messages.append(
                OutgoingMessage(
                    text="Complimenti, obiettivo raggiunto! Vuoi impostarne uno nuovo o passare al mantenimento?"
                )
            )
        return messages

    async def _handle_weight_confirmation(self, draft, raw_text: str) -> list[OutgoingMessage]:
        item = drafts.current_item(draft)
        answer = raw_text.strip().lower()
        if answer in ("sì", "si", "yes", "ok", "conferma"):
            from calobot.weight.normalizer import WeightNormalization

            normalization = WeightNormalization(kg_absolute=item["proposed_kg"])
            result = await apply_weight(
                self.session, self.user, normalization, item.get("when_text"), self.tz, confirmed=True
            )
            await drafts.discard_draft(self.session, self.user.id)
            return await self._respond_to_weight_result(result, item.get("when_text"))
        if answer in ("no",):
            await drafts.discard_draft(self.session, self.user.id)
            return [OutgoingMessage(text="Ok, non ho salvato nulla. Dimmi il peso corretto quando vuoi.")]
        return [
            OutgoingMessage(
                text=f"Confermi {item['proposed_kg']:.1f} kg?", buttons=["sì", "no"]
            )
        ]

    # -- profile ------------------------------------------------------------

    async def _start_profile_edit(self, content: MessageContent) -> list[OutgoingMessage]:
        extraction = await extract_profile_edit(self.gateway, content)
        if extraction.field is None:
            return [
                OutgoingMessage(
                    text=(
                        "Quale dato del profilo vuoi cambiare, e a quale valore? Per "
                        'esempio: "la mia data di nascita è 16/5/1972".'
                    )
                )
            ]
        return await self._propose_profile_field_value(extraction.field, extraction.value_text)

    async def _propose_profile_field_value(
        self, field: str, value_text: str, draft=None
    ) -> list[OutgoingMessage]:
        """Parses a stated value for `field` deterministically (design.md - Extraction
        names the field and quotes the value; parsing stays deterministic) and either
        proposes the change for confirmation, or - if it can't be parsed - asks again,
        bounded by clarification_attempt_limit like any other clarification.

        `draft` is the open draft when this is a retry after an unparseable answer;
        None on the first attempt, straight from extraction."""
        value, error = parse_field_raw(field, value_text)

        if value is None:
            if draft is None:
                draft = await drafts.create_draft(
                    self.session,
                    self.user.id,
                    DraftIntent.profile,
                    [{"field": field, "resolved": {}}],
                )
                await drafts.set_awaiting_field(self.session, draft, "value")
                return [
                    OutgoingMessage(
                        text=error or PROFILE_QUESTIONS[field],
                        buttons=[*PROFILE_OPTIONS.get(field, []), ABANDON_OPTION],
                    )
                ]

            attempt = await drafts.record_failed_attempt(self.session, draft)
            if attempt >= self.settings.clarification_attempt_limit:
                await drafts.discard_draft(self.session, self.user.id)
                return [
                    OutgoingMessage(
                        text=(
                            f"Lasciamo perdere: non ho cambiato {FIELD_LABELS[field]}, "
                            "perché non sono riuscito a capire il valore. Riscrivimelo "
                            "quando vuoi."
                        )
                    )
                ]
            text = error or PROFILE_QUESTIONS[field]
            return [
                OutgoingMessage(
                    text=f"{_reask_prefix(attempt)} {text}",
                    buttons=[*PROFILE_OPTIONS.get(field, []), ABANDON_OPTION],
                )
            ]

        # Checked before asking for confirmation, so an edit that will be refused is
        # never confirmed first (design.md - safety limit cannot hold on one path and
        # not the other; apply_onboarding_field enforces the same check again at
        # apply time as the actual guard).
        if (
            field == "peso_obiettivo_kg"
            and self.user.altezza_cm is not None
            and is_goal_weight_unsafe(value, self.user.altezza_cm)
        ):
            if draft is not None:
                await drafts.discard_draft(self.session, self.user.id)
            return [OutgoingMessage(text=GOAL_WEIGHT_UNSAFE_MESSAGE)]

        description = await describe_profile_change(self.session, self.user, field, value)
        confirm_draft = await drafts.create_draft(
            self.session,
            self.user.id,
            DraftIntent.profile,
            [{"field": field, "value_text": _serialize_profile_value(value), "resolved": {}}],
        )
        await drafts.set_awaiting_field(self.session, confirm_draft, "confirm")
        return [OutgoingMessage(text=f"{description}\nConfermi?", buttons=["sì", "no"])]

    async def _handle_profile_draft_answer(self, draft, raw_text: str) -> list[OutgoingMessage]:
        item = drafts.current_item(draft)
        if raw_text.strip() == ABANDON_OPTION:
            await drafts.discard_draft(self.session, self.user.id)
            return [OutgoingMessage(text="Va bene, non ho cambiato nulla.")]
        if draft.awaiting_field == "confirm":
            return await self._handle_profile_confirm_answer(draft, item, raw_text)
        return await self._propose_profile_field_value(item["field"], raw_text, draft=draft)

    async def _handle_profile_confirm_answer(
        self, draft, item: dict, raw_text: str
    ) -> list[OutgoingMessage]:
        answer = raw_text.strip().lower()
        field = item["field"]
        if answer in ("sì", "si", "yes", "ok", "conferma"):
            value, _ = parse_field_raw(field, item["value_text"])
            error = await apply_onboarding_field(self.session, self.user, field, value)
            await drafts.discard_draft(self.session, self.user.id)
            if error:
                return [OutgoingMessage(text=error)]
            return [
                OutgoingMessage(
                    text=f"Fatto: {FIELD_LABELS[field]} aggiornato a "
                    f"{format_field_value(field, value)}."
                )
            ]
        if answer == "no":
            await drafts.discard_draft(self.session, self.user.id)
            return [OutgoingMessage(text="Ok, non ho cambiato nulla.")]
        return [
            OutgoingMessage(
                text=f"Confermi la modifica a {FIELD_LABELS[field]}?", buttons=["sì", "no"]
            )
        ]

    # -- corrections --------------------------------------------------------

    async def handle_targeted_correction(
        self, raw_text: str, kind: str, entry
    ) -> list[OutgoingMessage]:
        """Entry point for the telegram layer when a message is a reply to a
        confirmation, so targeting is deterministic rather than 'most recent'
        (specs/entry-correction - Deterministic targeting of an entry)."""
        return await self._handle_correction(raw_text, target=(kind, entry))

    async def _handle_correction(
        self,
        raw_text: str,
        target: tuple[str, object] | None = None,
        already_confirmed: bool = False,
    ) -> list[OutgoingMessage]:
        """target, when given, is a (kind, entry) pair already resolved by the
        telegram layer from a reply-to a confirmation message (specs/entry-correction
        - Replying to an earlier confirmation). Falls back to the most recent entry
        when the message carries no such targeting."""
        last = target or await get_last_entry(self.session, self.user.id)
        if last is None:
            return [OutgoingMessage(text="Non c'è nulla da correggere.")]
        kind, entry = last

        quantity_match = _QUANTITY_WITH_GRAMS.search(raw_text.lower())
        has_marker = already_confirmed or any(m in raw_text.lower() for m in _CORRECTION_MARKERS)

        if kind == "food" and isinstance(entry, FoodEntry) and quantity_match:
            grams = float(quantity_match.group(1).replace(",", "."))
            updated = await amend_food_quantity(self.session, entry, grams)
            return [
                OutgoingMessage(
                    text=f"Corretto: {updated.description} {updated.grams:.0f}g - {updated.kcal:.0f} kcal",
                    entry_ref=("food", updated.id),
                )
            ]

        if kind == "food" and isinstance(entry, FoodEntry) and has_marker:
            new_description = raw_text
            for marker in _CORRECTION_MARKERS:
                new_description = new_description.replace(marker, "")
            new_description = new_description.strip(" ,.")
            energy = await resolve_food_energy(self.session, self.gateway, new_description)
            entry.description = new_description
            entry.kcal_per_100g = energy.kcal_per_100g
            if entry.grams is not None:
                entry.kcal = energy.kcal_per_100g * entry.grams / 100.0
            elif energy.kcal_per_100g > 0:
                # grams was unknown because kcal had been stated directly (see
                # specs/food-logging) - kcal stays authoritative, grams is
                # re-derived against the corrected description's density.
                entry.grams = entry.kcal / energy.kcal_per_100g * 100.0
            entry.provenance = energy.provenance

            def scale_macro(per_100g: float | None) -> float | None:
                if per_100g is None or entry.grams is None:
                    return None
                return per_100g * entry.grams / 100.0

            entry.protein_g = scale_macro(energy.protein_per_100g)
            entry.fat_g = scale_macro(energy.fat_per_100g)
            entry.carbs_g = scale_macro(energy.carbs_per_100g)
            entry.fiber_g = scale_macro(energy.fiber_per_100g)
            await self.session.flush()
            grams_text = f"{entry.grams:.0f}g" if entry.grams is not None else "grammi non stimabili"
            return [
                OutgoingMessage(
                    text=f"Corretto: {entry.description} {grams_text} - {entry.kcal:.0f} kcal",
                    entry_ref=("food", entry.id),
                )
            ]

        if kind == "activity" and isinstance(entry, ActivityEntry):
            from calobot.activity.planner import _parse_minutes_free_text

            parsed_minutes = _parse_minutes_free_text(raw_text)
            if parsed_minutes is not None:
                weight = await get_latest_weight(self.session, self.user.id)
                weight_kg = weight.kg if weight else 70.0
                entry.duration_minutes = parsed_minutes
                entry.kcal = entry.met * weight_kg * (parsed_minutes / 60.0)
                await self.session.flush()
                return [
                    OutgoingMessage(
                        text=(
                            f"Corretto: {entry.activity} {entry.duration_minutes:.0f} min "
                            f"- ~{entry.kcal:.0f} kcal"
                        ),
                        entry_ref=("activity", entry.id),
                    )
                ]

        if kind == "activity" and isinstance(entry, ActivityEntry) and has_marker:
            new_activity = raw_text
            for marker in _CORRECTION_MARKERS:
                new_activity = new_activity.replace(marker, "")
            new_activity = new_activity.strip(" ,.")

            from calobot.activity.planner import _parse_minutes_free_text

            new_minutes = _parse_minutes_free_text(new_activity)
            if new_minutes is not None:
                pass
            else:
                new_minutes = entry.duration_minutes

            from calobot.activity.resolver import resolve_met

            met_result = await resolve_met(self.session, self.gateway, new_activity, None)
            weight = await get_latest_weight(self.session, self.user.id)
            weight_kg = weight.kg if weight else 70.0

            entry.activity = new_activity
            entry.duration_minutes = new_minutes
            entry.met = met_result.met
            entry.kcal = met_result.met * weight_kg * (new_minutes / 60.0)
            entry.provenance = met_result.provenance
            await self.session.flush()
            return [
                OutgoingMessage(
                    text=(
                        f"Corretto: {entry.activity} {entry.duration_minutes:.0f} min "
                        f"- ~{entry.kcal:.0f} kcal"
                    ),
                    entry_ref=("activity", entry.id),
                )
            ]

        if not has_marker and not quantity_match:
            draft = await drafts.create_draft(
                self.session,
                self.user.id,
                DraftIntent.correction,
                [{"raw_text": raw_text, "resolved": {}}],
            )
            await drafts.set_awaiting_field(self.session, draft, "is_correction")
            return [
                OutgoingMessage(
                    text="Intendi correggere l'ultima voce registrata o è una voce nuova?",
                    buttons=["è una correzione", "è una voce nuova"],
                )
            ]

        return [
            OutgoingMessage(
                text="Per correggere questo tipo di voce usa i pulsanti sulla conferma originale."
            )
        ]

    async def _handle_correction_confirmation(
        self, draft, content: MessageContent, raw_text: str
    ) -> list[OutgoingMessage]:
        item = drafts.current_item(draft)
        answer = raw_text.strip().lower()
        await drafts.discard_draft(self.session, self.user.id)
        if "nuova" in answer:
            return await self._handle_fresh(TextContent(text=item["raw_text"]), item["raw_text"])
        return await self._handle_correction(item["raw_text"], already_confirmed=True)

    # -- reports ------------------------------------------------------------

    async def _handle_report(self, content: MessageContent) -> list[OutgoingMessage]:
        extraction = await extract_report(self.gateway, content)
        period = parse_period(extraction.period_text)
        reference_day = today_in_timezone(self.tz)
        budget = await current_budget(self.session, self.user)
        budget_kcal = budget.target_kcal if budget else None

        messages: list[OutgoingMessage] = []

        if extraction.topic in ("food", "all"):
            activity_kcal_today = 0.0
            if period == "day":
                activity_today = await build_activity_report(
                    self.session, self.user.id, "day", reference_day, self.tz
                )
                activity_kcal_today = activity_today.total_kcal if activity_today.has_data else 0.0

            food_report = await build_food_report(
                self.session,
                self.user.id,
                period,
                reference_day,
                self.tz,
                budget_kcal,
                activity_kcal_today=activity_kcal_today,
            )
            if not food_report.has_data:
                from calobot.reporting.empty_reports import generate_empty_report_response
                empty_msg = await generate_empty_report_response(self.gateway, period, budget_kcal)
                messages.append(OutgoingMessage(text=empty_msg))
            else:
                text = (
                    f"Calorie ({period}): totale {food_report.total_kcal:.0f} kcal, "
                    f"media giornaliera {food_report.daily_average_kcal:.0f} kcal"
                )
                if budget_kcal is not None:
                    if food_report.activity_credit_kcal:
                        text += (
                            f" (budget {budget_kcal:.0f} kcal + {food_report.activity_credit_kcal:.0f} "
                            f"credito attività, differenza {food_report.difference_kcal:+.0f})"
                        )
                    else:
                        text += f" (budget {budget_kcal:.0f} kcal, differenza {food_report.difference_kcal:+.0f})"
                if food_report.days_with_no_data:
                    days_text = ", ".join(d.isoformat() for d in food_report.days_with_no_data)
                    text += f"\nGiorni senza dati: {days_text}"
                photo = None
                if period != "day":
                    breakdown = await build_daily_kcal_breakdown(
                        self.session, self.user.id, period, reference_day, self.tz
                    )
                    photo = render_calorie_chart(breakdown, budget_kcal)

                    # Add dietician review for weekly/monthly food reports
                    start, end = period_bounds_utc(period, reference_day, self.tz)
                    entries = await get_entries_in_range(self.session, "food", self.user.id, start, end)
                    tip_category = "dietician_tip_week" if period == "week" else "dietician_tip_general"
                    avoid_repeating = await previous_unresolved_tip(self.session, self.user, tip_category)
                    review = await build_dietitian_review(
                        self.gateway, entries, self.tz, period, avoid_repeating=avoid_repeating
                    )
                    if review:
                        text += format_dietician_review(review)
                    if isinstance(review, DieticianReview):
                        await record_advice(
                            self.session,
                            self.user,
                            AdviceSurface.dietician_review,
                            tip_category,
                            review.actionable_tip,
                            situation=f"period={period}",
                        )
                else:
                    start, end = period_bounds_utc(period, reference_day, self.tz)
                    entries_today = await get_entries_in_range(self.session, "food", self.user.id, start, end)
                    remaining_kcal = (
                        (budget_kcal + food_report.activity_credit_kcal) - food_report.total_kcal
                        if budget_kcal is not None
                        else None
                    )
                    avoid_repeating = await previous_unresolved_tip(self.session, self.user, "daily_rest_of_day")
                    advice = await build_daily_advice(
                        self.gateway,
                        entries_today,
                        remaining_kcal,
                        food_report.activity_credit_kcal,
                        avoid_repeating=avoid_repeating,
                    )
                    if advice:
                        text += f"\n\n💡 {advice}"
                        await record_advice(
                            self.session,
                            self.user,
                            AdviceSurface.daily_advice,
                            "daily_rest_of_day",
                            advice,
                            situation="daily_report",
                        )

                messages.append(OutgoingMessage(text=text, photo_png=photo))

        if extraction.topic == "macros":
            macro_report = await build_macro_report(
                self.session, self.user.id, period, reference_day, self.tz
            )
            if not macro_report.has_data:
                messages.append(
                    OutgoingMessage(text="Non ci sono dati sui macronutrienti per questo periodo.")
                )
            else:
                text = (
                    f"Macronutrienti ({period}): "
                    f"proteine {macro_report.protein_total_g:.0f}g (media {macro_report.protein_avg_g:.0f}g/giorno), "
                    f"grassi {macro_report.fat_total_g:.0f}g (media {macro_report.fat_avg_g:.0f}g/giorno), "
                    f"carboidrati {macro_report.carbs_total_g:.0f}g (media {macro_report.carbs_avg_g:.0f}g/giorno), "
                    f"fibre {macro_report.fiber_total_g:.0f}g (media {macro_report.fiber_avg_g:.0f}g/giorno)"
                )
                if macro_report.days_with_no_data:
                    days_text = ", ".join(d.isoformat() for d in macro_report.days_with_no_data)
                    text += f"\nGiorni senza dati: {days_text}"
                photo = None
                if period != "day":
                    daily_macros = await build_daily_macro_breakdown(
                        self.session, self.user.id, period, reference_day, self.tz
                    )
                    photo = render_macro_chart(daily_macros)
                messages.append(OutgoingMessage(text=text, photo_png=photo))

        if extraction.topic in ("weight", "all"):
            goal_kg = self.user.peso_obiettivo_kg
            weight_report = await build_weight_report(
                self.session, self.user.id, period, reference_day, self.tz, goal_kg
            )
            if not weight_report.has_data:
                # Only answer the absence when the user asked about weight. On an
                # unscoped report they asked for a report, not about weight, and saying
                # so is noise (specs/reporting - An unscoped report reports only the
                # topics that have data).
                if extraction.topic == "weight":
                    messages.append(
                        OutgoingMessage(text="Non ci sono dati sul peso per questo periodo.")
                    )
            else:
                if weight_report.start_kg == weight_report.end_kg:
                    text = f"Peso ({period}): {weight_report.end_kg:.1f} kg"
                else:
                    text = (
                        f"Peso ({period}): da {weight_report.start_kg:.1f} a {weight_report.end_kg:.1f} kg "
                        f"({weight_report.change_kg:+.1f} kg)"
                    )
                if weight_report.remaining_to_goal_kg is not None:
                    text += f", mancano {weight_report.remaining_to_goal_kg:+.1f} kg all'obiettivo"
                if weight_report.projected_date:
                    projected = weight_report.projected_date.isoformat()
                    text += f"\nAl ritmo attuale, obiettivo previsto per il {projected}"
                elif weight_report.projection_unavailable_reason:
                    text += f"\n(proiezione non disponibile: {weight_report.projection_unavailable_reason})"
                photo = None
                if period != "day":
                    photo = render_weight_chart(
                        weight_report.points, goal_kg, weight_report.projected_date
                    )
                messages.append(OutgoingMessage(text=text, photo_png=photo))

        if extraction.topic in ("activity", "all"):
            activity_report = await build_activity_report(
                self.session, self.user.id, period, reference_day, self.tz
            )
            if not activity_report.has_data:
                # As above: reported only when the user scoped the request to activity.
                if extraction.topic == "activity":
                    messages.append(
                        OutgoingMessage(text="Non ci sono dati sull'attività per questo periodo.")
                    )
            else:
                messages.append(
                    OutgoingMessage(
                        text=(
                            f"Attività ({period}): {activity_report.total_minutes:.0f} min su "
                            f"{activity_report.days_with_activity} giorni, "
                            f"~{activity_report.total_kcal:.0f} kcal"
                        )
                    )
                )

        return messages
