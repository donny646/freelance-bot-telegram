import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.db import get_user_settings, set_user_language, set_user_currency, set_user_timezone
from bot.i18n import t
from bot.i18n.translations import LANGUAGE_NAMES, CURRENCY_NAMES, TIMEZONE_NAMES

logger = logging.getLogger(__name__)
router = Router()


def _settings_text(lang: str, currency: str, timezone: str) -> str:
    return t("settings_title", lang,
             lang_name=LANGUAGE_NAMES.get(lang, lang),
             currency=CURRENCY_NAMES.get(currency, currency),
             timezone=TIMEZONE_NAMES.get(timezone, timezone))


def get_settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t("btn_settings_lang", lang), callback_data="settings_lang"),
            InlineKeyboardButton(text=t("btn_settings_currency", lang), callback_data="settings_currency"),
        ],
        [InlineKeyboardButton(text=t("btn_settings_tz", lang), callback_data="settings_tz")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "menu_settings")
async def cb_settings_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency, tz = s["language"], s["currency"], s["timezone"]
    await callback.message.edit_text(
        _settings_text(lang, currency, tz),
        reply_markup=get_settings_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings_lang")
async def cb_settings_lang(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]

    buttons = []
    for code, name in LANGUAGE_NAMES.items():
        check = " ✓" if code == lang else ""
        buttons.append([InlineKeyboardButton(text=f"{name}{check}", callback_data=f"set_lang_{code}")])
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")])

    await callback.message.edit_text(
        t("settings_lang_title", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_lang_"))
async def cb_set_lang(callback: CallbackQuery):
    new_lang = callback.data.replace("set_lang_", "")
    if new_lang not in LANGUAGE_NAMES:
        await callback.answer("Unknown language", show_alert=True)
        return

    await set_user_language(callback.from_user.id, new_lang)
    s = await get_user_settings(callback.from_user.id)
    lang, currency, tz = s["language"], s["currency"], s["timezone"]

    await callback.answer(t("settings_lang_set", lang))
    await callback.message.edit_text(
        _settings_text(lang, currency, tz),
        reply_markup=get_settings_keyboard(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings_currency")
async def cb_settings_currency(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]

    buttons = []
    for code, name in CURRENCY_NAMES.items():
        check = " ✓" if code == currency else ""
        buttons.append([InlineKeyboardButton(text=f"{name}{check}", callback_data=f"set_currency_{code}")])
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")])

    await callback.message.edit_text(
        t("settings_currency_title", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_currency_"))
async def cb_set_currency(callback: CallbackQuery):
    new_currency = callback.data.replace("set_currency_", "")
    if new_currency not in CURRENCY_NAMES:
        await callback.answer("Unknown currency", show_alert=True)
        return

    await set_user_currency(callback.from_user.id, new_currency)
    s = await get_user_settings(callback.from_user.id)
    lang, currency, tz = s["language"], s["currency"], s["timezone"]

    await callback.answer(t("settings_currency_set", lang))
    await callback.message.edit_text(
        _settings_text(lang, currency, tz),
        reply_markup=get_settings_keyboard(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings_tz")
async def cb_settings_tz(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, tz = s["language"], s["timezone"]

    buttons = []
    for code, name in TIMEZONE_NAMES.items():
        check = " ✓" if code == tz else ""
        buttons.append([InlineKeyboardButton(text=f"{name}{check}", callback_data=f"set_tz_{code}")])
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_settings")])

    await callback.message.edit_text(
        t("settings_tz_title", lang, current=TIMEZONE_NAMES.get(tz, tz)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_tz_"))
async def cb_set_tz(callback: CallbackQuery):
    new_tz = callback.data.replace("set_tz_", "")
    if new_tz not in TIMEZONE_NAMES:
        await callback.answer("Unknown timezone", show_alert=True)
        return

    await set_user_timezone(callback.from_user.id, new_tz)
    s = await get_user_settings(callback.from_user.id)
    lang, currency, tz = s["language"], s["currency"], s["timezone"]

    await callback.answer(t("settings_tz_set", lang))
    await callback.message.edit_text(
        _settings_text(lang, currency, tz),
        reply_markup=get_settings_keyboard(lang),
        parse_mode="HTML",
    )
