import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Document, Message

from app.helpers.enums import LanguageEnum
from bot.api import (
    ClassifierClient,
    ClassifierError,
    InvalidEmailError,
    RateLimitedError,
)
from bot.eml import build_eml_from_message
from bot.formatting import format_card
from bot.i18n import t
from bot.language import get_language, toggle_language

logger = logging.getLogger(__name__)

MAX_DOCUMENT_BYTES = 1024 * 1024
EML_SUFFIX = ".eml"

router = Router(name="classify")

ERROR_KEYS = {
    InvalidEmailError: "error_invalid",
    RateLimitedError: "error_rate_limited",
}


def _language_of(message: Message) -> LanguageEnum:
    """Return the language to answer this message in.

    Args:
        message: Incoming Telegram message.

    Returns:
        The sender's chosen language, or the default for unknown senders.

    """
    return get_language(message.from_user.id) if message.from_user else LanguageEnum.UK


def _is_eml(document: Document) -> bool:
    """Check that a document looks like an .eml file.

    Args:
        document: Attached Telegram document.

    Returns:
        True if the file name ends in .eml.

    """
    return bool(document.file_name and document.file_name.lower().endswith(EML_SUFFIX))


async def _classify_and_reply(message: Message, eml: bytes, client: ClassifierClient) -> None:
    """Classify .eml bytes and answer with a result card or an error line.

    Args:
        message: Message to reply to.
        eml: Raw .eml bytes to classify.
        client: API client.

    """
    language = _language_of(message)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        outcome = await client.classify(eml, language)
    except ClassifierError as error:
        # Every API failure is already logged by the client; users see one line.
        await message.answer(t(language, ERROR_KEYS.get(type(error), "error_unavailable")))
        return

    await message.answer(format_card(outcome.payload, language, outcome.is_duplicate))


@router.message(CommandStart())
@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Answer /start and /help with what to send and the privacy note."""
    await message.answer(t(_language_of(message), "help"))


@router.message(Command("lang"))
async def handle_lang(message: Message) -> None:
    """Toggle the sender between Ukrainian and English."""
    if not message.from_user:
        return
    language = toggle_language(message.from_user.id)
    await message.answer(t(language, "language_set"))


@router.message(F.document)
async def handle_document(message: Message, client: ClassifierClient) -> None:
    """Classify an attached .eml file."""
    language = _language_of(message)
    document = message.document

    if not _is_eml(document):
        await message.answer(t(language, "hint"))
        return

    if (document.file_size or 0) > MAX_DOCUMENT_BYTES:
        await message.answer(t(language, "file_too_large"))
        return

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        buffer = await message.bot.download(document)
        eml = buffer.read()
    except Exception:
        logger.exception("Could not download document %s", document.file_id)
        await message.answer(t(language, "error_unavailable"))
        return

    await _classify_and_reply(message, eml, client)


@router.message(F.text)
async def handle_text(message: Message, client: ClassifierClient) -> None:
    """Classify a forwarded message or pasted email text."""
    language = _language_of(message)

    if not message.text.strip():
        await message.answer(t(language, "empty_text"))
        return

    await _classify_and_reply(message, build_eml_from_message(message), client)


@router.message()
async def handle_anything_else(message: Message) -> None:
    """Nudge the user when the message carries nothing classifiable."""
    await message.answer(t(_language_of(message), "hint"))
