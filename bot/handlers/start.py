import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from bot.database.db import get_subscription_status, get_user_settings
from bot.i18n import t

logger = logging.getLogger(__name__)
router = Router()


def get_main_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_income", lang), callback_data="menu_income"),
            InlineKeyboardButton(text=t("btn_clients", lang), callback_data="menu_clients"),
        ],
        [
            InlineKeyboardButton(text=t("btn_projects", lang), callback_data="menu_projects"),
            InlineKeyboardButton(text=t("btn_analytics", lang), callback_data="menu_analytics"),
        ],
        [
            InlineKeyboardButton(text=t("btn_reminders", lang), callback_data="menu_reminders"),
            InlineKeyboardButton(text=t("btn_subscription", lang), callback_data="menu_subscription"),
        ],
        [
            InlineKeyboardButton(text=t("btn_settings", lang), callback_data="menu_settings"),
            InlineKeyboardButton(text=t("btn_help", lang), callback_data="menu_help"),
        ],
    ])


def _sub_status_text(status: dict, lang: str) -> str:
    if status["type"] == "trial":
        return t("sub_trial", lang, days=status["days_left"])
    elif status["type"] == "subscription":
        return t("sub_active", lang, days=status["days_left"])
    return t("sub_inactive", lang)


@router.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    s = await get_user_settings(user.id)
    lang = s["language"]
    status = await get_subscription_status(user.id)
    sub_status = _sub_status_text(status, lang)

    text = t("greeting", lang, name=user.first_name, sub_status=sub_status)
    await message.answer(text, reply_markup=get_main_keyboard(lang), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    text = (
        f"{t('help_title', lang)}\n\n"
        f"{t('help_commands', lang)}\n\n"
        f"{t('help_quick_income', lang)}\n\n"
        f"{t('help_sections', lang)}\n\n"
        f"{t('help_support', lang)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_support", lang), url="https://t.me/donnyadm")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    status = await get_subscription_status(message.from_user.id)

    if status["type"] == "trial":
        text = t("sub_status_trial", lang, days=status["days_left"])
    elif status["type"] == "subscription":
        from datetime import datetime
        until = datetime.fromisoformat(status["until"]).strftime("%d.%m.%Y")
        text = t("sub_status_active", lang, until=until, days=status["days_left"])
    else:
        text = t("sub_status_inactive", lang)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_buy_extend", lang), callback_data="buy_menu")],
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery):
    user = callback.from_user
    s = await get_user_settings(user.id)
    lang = s["language"]
    status = await get_subscription_status(user.id)
    sub_status = _sub_status_text(status, lang)

    text = t("main_menu_return", lang, name=user.first_name, sub_status=sub_status)
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(lang), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "menu_subscription")
async def cb_subscription(callback: CallbackQuery):
    from bot.handlers.payment import cmd_buy
    await callback.message.delete()
    await cmd_buy(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu_help")
async def cb_help(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    text = (
        f"{t('help_title', lang)}\n\n"
        f"{t('help_commands', lang)}\n\n"
        f"{t('help_quick_income', lang)}\n\n"
        f"{t('help_sections', lang)}\n\n"
        f"{t('help_support', lang)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_support", lang), url="https://t.me/donnyadm")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
