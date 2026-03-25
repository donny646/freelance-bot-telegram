import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.database.db import check_subscription, create_or_update_user

logger = logging.getLogger(__name__)

ADMIN_IDS = {6502920835}
FREE_COMMANDS = {"/start", "/help", "/buy", "/status", "/admin"}

# Callback prefixes that are allowed without a subscription
FREE_CALLBACK_PREFIXES = (
    "buy_",
    "back_to_menu",
    "menu_help",
    "menu_settings",
    "menu_subscription",
    "settings_",
    "set_lang_",
    "set_currency_",
    "crypto_",
    "cplan_",
    "casset_",
    "ccheck_",
    "stars_menu",
    "settings_tz",
    "set_tz_",
)


class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware checks subscription on every action.
    Free commands and settings are always accessible.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
            text = event.text or ""

            if user:
                await create_or_update_user(user.id, user.username or "", user.full_name or "")

            if user and user.id in ADMIN_IDS:
                return await handler(event, data)

            for cmd in FREE_COMMANDS:
                if text.startswith(cmd):
                    return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            user = event.from_user
            cb_data = event.data or ""

            if user:
                await create_or_update_user(user.id, user.username or "", user.full_name or "")

            if user and user.id in ADMIN_IDS:
                return await handler(event, data)

            for prefix in FREE_CALLBACK_PREFIXES:
                if cb_data.startswith(prefix):
                    return await handler(event, data)

        else:
            # PreCheckoutQuery and other event types — allow through
            return await handler(event, data)

        if user is None:
            return await handler(event, data)

        has_access = await check_subscription(user.id)

        if not has_access:
            from bot.handlers.payment import send_paywall
            if isinstance(event, Message):
                await send_paywall(event)
            elif isinstance(event, CallbackQuery):
                await send_paywall(event.message, edit=True)
                await event.answer()
            return

        return await handler(event, data)
