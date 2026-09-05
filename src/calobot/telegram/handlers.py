"""aiogram handlers. Translates Telegram updates into MessagePipeline calls and
OutgoingMessage results into actual Bot API calls (text/buttons/photo/entry controls).

See specs/message-ingestion - Responsiveness feedback (typing indicator),
specs/entry-correction - Deterministic targeting of an entry (controls + reply-to).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.corrections.service import (
    Deleted,
    delete_by_target,
    find_entry_by_confirmation_message,
    set_confirmation_message_id,
    undo_last,
)
from calobot.ingestion.pipeline import MessagePipeline
from calobot.ingestion.responses import OutgoingMessage
from calobot.llm.content import ImageContent, TextContent
from calobot.llm.errors import LLMUnavailableError, LLMValidationExhaustedError
from calobot.llm.gateway import LLMGateway
from calobot.persistence.engine import get_session_factory
from calobot.persistence.models import User
from calobot.persistence.repository import get_user_by_telegram_id
from calobot.photo.intake import UnprocessableImage, downscale, to_base64
from calobot.profile.onboarding import (
    OPTIONS,
    QUESTIONS,
    extract_onboarding_fields,
    parse_and_validate,
    parse_field_raw,
)
from calobot.profile.service import (
    apply_onboarding_field,
    delete_all_user_data,
    format_profile_summary,
    maybe_complete_onboarding,
    next_onboarding_question,
    register_or_get_user,
)
from calobot.settings import Settings
from calobot.telegram.keyboards import CALLBACK_NUDGE_STOP, entry_controls_keyboard, options_keyboard

logger = logging.getLogger(__name__)


class TestAndProdTelemetryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat_id = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message is not None else event.from_user.id

        if chat_id is not None:
            from calobot.telemetry.context import (
                active_chat_id,
                active_no_retention,
                no_retention_chats,
            )

            token_chat = active_chat_id.set(chat_id)
            token_no_retention = active_no_retention.set(chat_id in no_retention_chats)
            try:
                return await handler(event, data)
            finally:
                active_chat_id.reset(token_chat)
                active_no_retention.reset(token_no_retention)
        else:
            return await handler(event, data)


router = Router()
router.message.outer_middleware(TestAndProdTelemetryMiddleware())
router.callback_query.outer_middleware(TestAndProdTelemetryMiddleware())

def _disclaimer(bot_label: str) -> str:
    return (
        f"Ricorda: {bot_label} è uno strumento di supporto, non un consulente medico o "
        "un nutrizionista. Per obiettivi di salute specifici parla con un professionista."
    )


def _welcome_message(bot_label: str) -> str:
    return (
        f"Ciao! Sono {bot_label} 🤖, il tuo assistente per il tracciamento di cibo, "
        "peso e attività fisica.\n\n"
        "Scrivimi in chat o inviami foto proprio come faresti con un amico! Ad esempio:\n"
        "🍎 <i>\"Ho mangiato una mela\"</i> (o invia la foto di un piatto)\n"
        "⚖️ <i>\"Oggi peso 78.5 kg\"</i>\n"
        "🏃‍♂️ <i>\"30 minuti di corsa leggera\"</i>\n"
        "📊 <i>\"Mostrami il report settimanale\"</i>\n"
        "❓ <i>\"Come sono andato questa settimana?\"</i>\n"
        "🍽️ <i>\"Cosa posso mangiare stasera?\"</i>\n\n"
        "🥦 Tengo il conto di calorie e macronutrienti (non di sodio o zuccheri), e se "
        "vuoi posso essere io a scriverti ogni tanto, quando noto qualcosa che vale la "
        "pena - lo puoi attivare quando vuoi.\n\n"
        "⚠️ <i>Nota: Questo è un software sperimentale e non sostituisce un parere medico. "
        "Per obiettivi di salute rivolgiti sempre a un professionista.</i>\n\n"
        "Iniziamo impostando il tuo profilo per calcolare il budget calorico!"
    )

UNAVAILABLE_TEXT = "Il servizio è temporaneamente non disponibile, riprova tra poco."
REPHRASE_TEXT = "Non sono riuscito a capire, puoi riscrivere il messaggio?"

HELP_TEXT = (
    "Comandi disponibili:\n"
    "/start - avvia la registrazione o mostra il tuo profilo\n"
    "/profilo - mostra i tuoi dati e il budget calorico\n"
    "/annulla - elimina l'ultima voce registrata\n"
    "/cancellami - elimina definitivamente tutti i tuoi dati\n"
    "/memory_off - attiva la modalità nessuna ritenzione (per testare il bot senza salvare i dati)\n"
    "/memory_on - riattiva la modalità normale\n"
    "/notifiche_on - ricevi ogni tanto un messaggio se c'è qualcosa di rilevante da dirti\n"
    "/notifiche_off - disattiva questi messaggi (disattivati di default)\n"
    "/help - mostra questo messaggio\n\n"
    "Per registrare dati, scrivimi semplicemente in chat! Ad esempio:\n"
    "🍎 Cibo: <i>\"ho mangiato una mela\"</i>, <i>\"pasta al pomodoro ieri sera\"</i>\n"
    "🏃‍♂️ Attività: <i>\"un'ora di camminata\"</i>, <i>\"mezz'ora di corsa stamattina\"</i>\n"
    "⚖️ Peso: <i>\"oggi peso 78kg\"</i>\n"
    "📊 Report: <i>\"report settimanale\"</i>, <i>\"come è andato il mese\"</i> - "
    "da una settimana in su ci aggiungo anche un commento del nutrizionista\n"
    "🥩 Macronutrienti: <i>\"distribuzione di proteine, grassi, carboidrati e fibre "
    "delle ultime 2 settimane\"</i>\n\n"
    "Puoi farmi domande sui tuoi dati e chiedermi consigli:\n"
    "❓ <i>\"come sono andato questa settimana?\"</i>, <i>\"sto perdendo peso?\"</i>, "
    "<i>\"cosa ho mangiato ieri?\"</i>\n"
    "🍽️ <i>\"cosa posso mangiare stasera?\"</i> - ti propongo qualche idea in base "
    "alle calorie che ti restano oggi e a cosa hai mangiato di recente\n"
    "💡 Rispondo anche a domande generiche, tipo <i>\"quando conviene pesarsi?\"</i>\n\n"
    "Se hai sbagliato a registrare, correggi subito nello stesso modo: "
    "<i>\"no, erano 200g\"</i>, <i>\"era pasta integrale, non normale\"</i> - "
    "aggiorno l'ultima voce registrata; con /annulla la elimini del tutto.\n\n"
    "🔔 Posso anche essere io a scriverti, ogni tanto, ma solo se me lo chiedi tu "
    "con /notifiche_on (o semplicemente scrivimelo: \"voglio ricevere le "
    "notifiche\"): ti faccio sapere se non ti fai sentire da qualche giorno, "
    "se raggiungi il tuo obiettivo di peso, o se un mio consiglio è rimasto senza "
    "risposta. Sono disattivate di default e puoi spegnerle in ogni momento "
    "rispondendo a quel messaggio, con /notifiche_off, o dicendomi semplicemente "
    "\"basta notifiche\".\n\n"
    "Puoi anche inviarmi una FOTO di:\n"
    "- Un piatto o alimento per estrarre e registrare gli ingredienti\n"
    "- Una tabella nutrizionale sulla confezione di un prodotto per leggerla\n"
    "- Un codice a barre per cercare l'alimento su OpenFoodFacts\n\n"
    "Per correggere un dato del tuo profilo, scrivimelo direttamente (es. \"la mia "
    "data di nascita è 16/5/1990\", \"ora il mio peso obiettivo è 74kg\") - te lo "
    "chiedo prima di applicarlo.\n\n"
    "ℹ️ Tengo il conto di <b>calorie</b> e macronutrienti (proteine, grassi, carboidrati "
    "e fibre); non traccio invece sodio o zuccheri, quindi su quelli non posso darti numeri."
)


def _gateway(settings: Settings) -> LLMGateway:
    return LLMGateway(settings)


def _telegram_user_id(message: Message) -> int | None:
    """None only for message types Telegram doesn't attach a sender to (e.g. an
    anonymous channel post) - not a realistic case for a private-chat bot, but
    guarded rather than assumed."""
    return message.from_user.id if message.from_user is not None else None


async def _send_outgoing(
    bot: Bot, chat_id: int, session: AsyncSession, message: OutgoingMessage
) -> None:
    reply_markup = options_keyboard(message.buttons) if message.buttons else None

    if message.photo_png is not None:
        if len(message.text) <= 1024:
            sent = await bot.send_photo(
                chat_id,
                BufferedInputFile(message.photo_png, filename="report.png"),
                caption=message.text,
            )
        else:
            # Split the message to avoid Telegram's 1024 character caption limit truncation.
            # Try to find a logical split point like dietician review separator, double newline, or single newline.
            split_idx = message.text.find("\n\n🍎")
            if split_idx == -1:
                split_idx = message.text.rfind("\n\n", 0, 1024)
            if split_idx == -1:
                split_idx = message.text.rfind("\n", 0, 1024)
            if split_idx == -1 or split_idx == 0:
                split_idx = 1024

            caption = message.text[:split_idx].strip()
            remaining_text = message.text[split_idx:].strip()

            sent = await bot.send_photo(
                chat_id,
                BufferedInputFile(message.photo_png, filename="report.png"),
                caption=caption,
            )
            if remaining_text:
                await bot.send_message(chat_id, remaining_text, reply_markup=reply_markup)
    else:
        sent = await bot.send_message(chat_id, message.text, reply_markup=reply_markup)

    if message.entry_ref is not None:
        kind, entry_id = message.entry_ref
        await set_confirmation_message_id(session, kind, entry_id, sent.message_id)
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=sent.message_id,
            reply_markup=entry_controls_keyboard(kind, entry_id),
        )


async def _advance_onboarding(
    bot: Bot, chat_id: int, session: AsyncSession, user: User, settings: Settings
) -> None:
    """Sends the next onboarding question, or completes onboarding and sends the
    disclaimer + profile summary. Shared by /start, free-text answers and button
    answers, so all three entry points stay in sync on what "the next step" is -
    the bug this fixes was exactly these paths drifting apart (see
    on_answer_callback)."""
    next_field = await next_onboarding_question(session, user)
    if next_field is None:
        completed = await maybe_complete_onboarding(session, user)
        await session.commit()
        if completed:
            summary = await format_profile_summary(session, user)
            await bot.send_message(chat_id, f"{_disclaimer(settings.bot_label)}\n\n{summary}")
        return
    question = QUESTIONS[next_field]
    await bot.send_message(chat_id, question, reply_markup=options_keyboard(OPTIONS.get(next_field, [])))


async def _run_pipeline_and_reply(
    bot: Bot,
    settings: Settings,
    chat_id: int,
    user: User,
    content,
    raw_text: str,
    reply_to_message_id: int | None = None,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        # re-attach the user to this session
        reloaded_user = await get_user_by_telegram_id(session, user.telegram_user_id)
        if reloaded_user is None:
            return  # e.g. the user ran /cancellami between the original lookup and now
        user = reloaded_user
        gateway = _gateway(settings)
        await bot.send_chat_action(chat_id, "typing")
        try:
            pipeline = MessagePipeline(session, gateway, settings, user)
            targeted = None
            if reply_to_message_id is not None:
                targeted = await find_entry_by_confirmation_message(session, reply_to_message_id)
            if targeted is not None:
                kind, entry = targeted
                messages = await pipeline.handle_targeted_correction(raw_text, kind, entry)
            else:
                messages = await pipeline.handle(content, raw_text)
        except LLMUnavailableError:
            await session.rollback()
            await bot.send_message(chat_id, UNAVAILABLE_TEXT)
            return
        except LLMValidationExhaustedError:
            await session.rollback()
            await bot.send_message(chat_id, REPHRASE_TEXT)
            return

        for msg in messages:
            await _send_outgoing(bot, chat_id, session, msg)
        await session.commit()


@router.message(CommandStart())
async def on_start(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        reg = await register_or_get_user(session, telegram_user_id)
        await session.commit()

        if reg.onboarding_complete:
            summary = await format_profile_summary(session, reg.user)
            await message.answer(f"Bentornato! Ecco il tuo profilo:\n{summary}")
            return

        if reg.is_new:
            await message.answer(_welcome_message(settings.bot_label))

        await _advance_onboarding(bot, message.chat.id, session, reg.user, settings)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("memory_off"))
async def on_memory_off(message: Message) -> None:
    from calobot.telemetry.context import no_retention_chats, save_no_retention_chats
    chat_id = message.chat.id
    no_retention_chats.add(chat_id)
    save_no_retention_chats()
    await message.answer(
        "Modalità \"nessuna ritenzione\" attivata. Le tue prossime azioni "
        "non verranno salvate nel database. Usa /memory_on per tornare alla "
        "modalità normale."
    )


@router.message(Command("memory_on"))
async def on_memory_on(message: Message) -> None:
    from calobot.telemetry.context import no_retention_chats, save_no_retention_chats
    chat_id = message.chat.id
    no_retention_chats.discard(chat_id)
    save_no_retention_chats()
    await message.answer(
        "Modalità normale riattivata. Le tue prossime azioni verranno "
        "regolarmente salvate nel database."
    )


@router.message(Command("notifiche_on"))
async def on_nudges_on(message: Message) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            await message.answer("Usa prima /start per registrarti.")
            return
        user.nudges_enabled = True
        await session.commit()
    await message.answer(
        "Notifiche attivate. Potresti ricevere un messaggio ogni tanto se c'è "
        "qualcosa di rilevante da dirti (mai più di uno ogni pochi giorni). "
        "Usa /notifiche_off per disattivarle in qualsiasi momento."
    )


@router.message(Command("notifiche_off"))
async def on_nudges_off(message: Message) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            return
        user.nudges_enabled = False
        await session.commit()
    await message.answer("Notifiche disattivate.")


@router.callback_query(F.data == CALLBACK_NUDGE_STOP)
async def on_nudge_stop_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.message is None:
        return
    chat_id = callback.message.chat.id
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if user is not None:
            user.nudges_enabled = False
            await session.commit()
    await callback.answer("Notifiche disattivate.")
    await bot.send_message(chat_id, "Notifiche disattivate. Puoi riattivarle quando vuoi con /notifiche_on.")


@router.message(Command("annulla"))
async def on_undo(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            await message.answer("Devi registrarti prima con /start.")
            return
        result = await undo_last(session, user.id)
        await session.commit()
        if isinstance(result, Deleted):
            await message.answer(f"Eliminata l'ultima voce ({result.kind}).")
        else:
            await message.answer("Non c'è nulla da annullare.")


@router.message(Command("profilo"))
async def on_profile(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            await message.answer("Devi registrarti prima con /start.")
            return
        summary = await format_profile_summary(session, user)

        from calobot.telemetry.context import no_retention_chats

        is_off = message.chat.id in no_retention_chats
        status_text = "OFF" if is_off else "ON"
        await message.answer(f"{summary}\nStato memoria: {status_text}\nID Chat: {message.chat.id}")


@router.message(Command("cancellami"))
async def on_delete_all(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            await message.answer("Non ho dati tuoi da cancellare.")
            return
        await delete_all_user_data(session, user)
        await message.answer("Ho cancellato permanentemente tutti i tuoi dati.")


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    if telegram_user_id is None or not message.photo:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_user_id)
        if user is None:
            await message.answer("Usa prima /start per registrarti.")
            return

    await bot.send_chat_action(message.chat.id, "typing")
    file = await bot.get_file(message.photo[-1].file_id)
    if file.file_path is None:
        return
    file_bytes = await bot.download_file(file.file_path)
    if file_bytes is None:
        return

    raw_bytes = file_bytes.read()
    try:
        general = downscale(raw_bytes, settings.photo_max_dimension_px)
        label = downscale(raw_bytes, settings.photo_label_max_dimension_px)
    except UnprocessableImage:
        await message.answer("Non riesco a leggere questo file come immagine: prova con un'altra foto.")
        return

    content = ImageContent(
        base64_data=to_base64(general),
        caption=message.caption,
        label_base64_data=to_base64(label),
    )
    await _run_pipeline_and_reply(
        bot, settings, message.chat.id, user, content, message.caption or ""
    )


@router.message(F.text)
async def on_text(message: Message, bot: Bot, settings: Settings) -> None:
    telegram_user_id = _telegram_user_id(message)
    text = message.text
    if telegram_user_id is None or not text:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        reg = await register_or_get_user(session, telegram_user_id)
        await session.commit()
        user = reg.user

        if not user.onboarding_complete:
            gateway = _gateway(settings)
            pending_field = await next_onboarding_question(session, user)
            try:
                extraction = await extract_onboarding_fields(
                    gateway, TextContent(text=text), expected_field=pending_field
                )
            except (LLMUnavailableError, LLMValidationExhaustedError):
                await message.answer(UNAVAILABLE_TEXT)
                return
            parsed, errors = parse_and_validate(extraction)
            if pending_field and pending_field not in parsed:
                # The LLM extraction can miss a lexically bare answer (e.g. "54") that
                # doesn't explicitly name a unit/field; fall back to parsing the raw
                # message against the field we know is pending, so a valid answer never
                # results in the same question being re-sent.
                value, error = parse_field_raw(pending_field, text)
                if error:
                    errors.append(error)
                elif value is not None:
                    parsed[pending_field] = value
            for field, value in parsed.items():
                error = await apply_onboarding_field(session, user, field, value)
                if error:
                    errors.append(error)
            await session.commit()

            for err in errors:
                await message.answer(err)

            await _advance_onboarding(bot, message.chat.id, session, user, settings)
            return

    reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None
    await _run_pipeline_and_reply(
        bot,
        settings,
        message.chat.id,
        user,
        TextContent(text=text),
        text,
        reply_to_message_id=reply_to_id,
    )


@router.callback_query(F.data.startswith("ans:"))
async def on_answer_callback(callback: CallbackQuery, bot: Bot, settings: Settings) -> None:
    if not callback.data or callback.message is None:
        return
    answer_text = callback.data.removeprefix("ans:")
    chat_id = callback.message.chat.id
    await callback.answer()

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if user is None:
            return

        if not user.onboarding_complete:
            # Buttons only appear for onboarding's enum fields (sesso, livello di
            # attività, ritmo); the tapped label IS the raw value for whichever
            # field is currently awaited - no LLM call needed, and applying it
            # deterministically is what was missing here before (see
            # _advance_onboarding docstring for why this bug happened).
            next_field = await next_onboarding_question(session, user)
            if next_field in OPTIONS and answer_text in OPTIONS[next_field]:
                error = await apply_onboarding_field(session, user, next_field, answer_text)
                await session.commit()
                if error:
                    await bot.send_message(chat_id, error)
                    return
            # A stale or mismatched tap (e.g. an old keyboard from an already
            # -answered question): ignore the value, just re-show the current step.
            await _advance_onboarding(bot, chat_id, session, user, settings)
            return

    await _run_pipeline_and_reply(
        bot, settings, chat_id, user, TextContent(text=answer_text), answer_text
    )


@router.callback_query(F.data.startswith("entry:"))
async def on_entry_control_callback(callback: CallbackQuery, bot: Bot, settings: Settings) -> None:
    if not callback.data or callback.message is None:
        return
    _, action, kind, entry_id_str = callback.data.split(":")
    entry_id = int(entry_id_str)
    chat_id = callback.message.chat.id
    session_factory = get_session_factory()
    async with session_factory() as session:
        if action == "elimina":
            result = await delete_by_target(session, kind, entry_id)  # type: ignore[arg-type]
            await session.commit()
            if isinstance(result, Deleted):
                await callback.answer("Eliminata.")
                await bot.send_message(chat_id, "Voce eliminata.")
            else:
                await callback.answer("Già eliminata o non trovata.")
        elif action == "modifica":
            await callback.answer()
            if kind == "activity":
                example = "no erano 20 minuti"
            elif kind == "weight":
                example = "no erano 77.5kg"
            else:
                example = "no erano 20g"
            sent = await bot.send_message(
                chat_id,
                "Rispondi a questo messaggio (o al messaggio della voce) con la correzione, "
                f"es. '{example}'.",
            )
            await set_confirmation_message_id(session, kind, entry_id, sent.message_id)
            await session.commit()
