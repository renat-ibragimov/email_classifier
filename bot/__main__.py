import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.api import ClassifierClient
from bot.config import get_settings
from bot.handlers import router

logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the bot with long polling until interrupted."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    client = ClassifierClient(settings.api_base_url)

    # Handlers declare `client` as a parameter; the dispatcher injects it by name.
    dispatcher = Dispatcher(client=client)
    dispatcher.include_router(router)

    logger.info("Bot starting, API at %s", settings.api_base_url)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
