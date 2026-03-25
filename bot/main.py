import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.database.db import init_db
from bot.handlers import start, income, clients, projects, analytics, reminders, payment, settings
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.utils.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    await init_db()
    logger.info("Database initialized")

    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # Router order matters — payment first for PreCheckoutQuery
    dp.include_router(payment.router)
    dp.include_router(start.router)
    dp.include_router(settings.router)
    dp.include_router(income.router)
    dp.include_router(clients.router)
    dp.include_router(projects.router)
    dp.include_router(analytics.router)
    dp.include_router(reminders.router)

    start_scheduler(bot)
    logger.info("FreelanceBot started!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        stop_scheduler()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
