import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from bot.database.db import get_pending_reminders, mark_reminder_sent, get_user_settings
from bot.i18n import t

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def check_and_send_reminders(bot: Bot):
    """Check and send all overdue reminders"""
    try:
        reminders = await get_pending_reminders()
        for reminder in reminders:
            try:
                s = await get_user_settings(reminder["user_id"])
                lang = s.get("language", "ru")
                await bot.send_message(
                    chat_id=reminder["user_id"],
                    text=t("reminder_notification", lang, text=reminder["text"]),
                    parse_mode="HTML",
                )
                await mark_reminder_sent(reminder["id"])
                logger.info(f"Reminder {reminder['id']} sent to {reminder['user_id']}")
            except Exception as e:
                logger.error(f"Error sending reminder {reminder['id']}: {e}")
    except Exception as e:
        logger.error(f"Error checking reminders: {e}")


def start_scheduler(bot: Bot):
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        seconds=30,
        args=[bot],
        id="reminders_check",
        replace_existing=True,
        next_run_time=datetime.utcnow(),  # run immediately on startup
    )
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
