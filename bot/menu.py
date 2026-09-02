import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.helpers.enums import LanguageEnum
from bot.i18n import t
from bot.language import DEFAULT_LANGUAGE, UKRAINIAN_CLIENT_CODES

logger = logging.getLogger(__name__)

# The commands Telegram shows in the menu button, in the order they appear.
MENU_COMMANDS: tuple[tuple[str, str], ...] = (
    ("help", "cmd_help"),
    ("lang", "cmd_lang"),
)


def commands_for(language: LanguageEnum) -> list[BotCommand]:
    """Build the menu in one language.

    Args:
        language: Language to render the descriptions in.

    Returns:
        The command list Telegram expects, in menu order.

    """
    return [BotCommand(command=name, description=t(language, key)) for name, key in MENU_COMMANDS]


async def set_default_menu(bot: Bot) -> None:
    """Publish the menu every private chat starts with.

    Telegram picks a menu by the client's interface language, using the same
    mapping the replies do: Ukrainian for Ukrainian and Russian clients, and the
    untranslated default — English — for everyone else.

    Args:
        bot: Bot whose menu is being set.

    """
    scope = BotCommandScopeAllPrivateChats()

    for code in sorted(UKRAINIAN_CLIENT_CODES):
        await bot.set_my_commands(commands_for(LanguageEnum.UK), scope=scope, language_code=code)

    await bot.set_my_commands(commands_for(DEFAULT_LANGUAGE), scope=scope)


async def set_chat_menu(bot: Bot, chat_id: int, language: LanguageEnum) -> None:
    """Re-publish the menu of a single chat after its language changed.

    A chat-scoped menu outranks the language-based default, so this follows the
    user's own choice rather than their Telegram interface language. The menu is
    cosmetic: a failure here is logged and never breaks the reply.

    Args:
        bot: Bot whose menu is being set.
        chat_id: Chat to set the menu for.
        language: Language to render the descriptions in.

    """
    try:
        await bot.set_my_commands(commands_for(language), scope=BotCommandScopeChat(chat_id=chat_id))
    except Exception:
        logger.warning("Could not update the menu of chat %s", chat_id, exc_info=True)
