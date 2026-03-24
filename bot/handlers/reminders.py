import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from datetime import datetime, timedelta
from bot.database.db import add_reminder, get_user_reminders, get_user_settings
from bot.services.text_parser import parse_date
from bot.i18n import t
from bot.i18n.translations import TIMEZONE_OFFSETS

logger = logging.getLogger(__name__)
router = Router()


class ReminderStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_date = State()


def get_reminders_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_reminder_add", lang), callback_data="reminder_add")],
        [InlineKeyboardButton(text=t("btn_reminder_list", lang), callback_data="reminder_list")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "menu_reminders")
async def cb_reminders_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("reminders_menu_title", lang),
        reply_markup=get_reminders_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "reminder_add")
async def cb_reminder_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderStates.waiting_for_text)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="reminder_cancel")]
    ])
    await callback.message.edit_text(
        t("reminder_add_text", lang), reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "reminder_cancel")
async def cb_reminder_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("reminders_menu_title", lang),
        reply_markup=get_reminders_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ReminderStates.waiting_for_text)
async def process_reminder_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text.strip())
    await state.set_state(ReminderStates.waiting_for_date)
    s = await get_user_settings(message.from_user.id)
    lang, tz = s["language"], s.get("timezone", "UTC")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="reminder_cancel")]
    ])
    prompt = t("reminder_add_date", lang) + f"\n\n🌍 <b>{tz}</b>"
    await message.answer(prompt, reply_markup=keyboard, parse_mode="HTML")


@router.message(ReminderStates.waiting_for_date)
async def process_reminder_date(message: Message, state: FSMContext):
    s = await get_user_settings(message.from_user.id)
    lang, tz = s["language"], s.get("timezone", "UTC")
    tz_offset = TIMEZONE_OFFSETS.get(tz, 0)
    remind_at = parse_date(message.text, tz_offset_hours=tz_offset)
    if not remind_at:
        await message.answer(t("reminder_date_error", lang), parse_mode="HTML")
        return

    # Reject times clearly in the past (allow 2-minute grace for clock rounding)
    utc_stored = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
    if utc_stored < datetime.utcnow() - timedelta(minutes=2):
        await message.answer(t("reminder_past_error", lang, tz=tz), parse_mode="HTML")
        return

    data = await state.get_data()
    await add_reminder(message.from_user.id, data["text"], remind_at)
    await state.clear()

    # Show time in user's local timezone
    utc_dt = datetime.fromisoformat(remind_at)
    local_dt = utc_dt + timedelta(hours=tz_offset)
    text = t("reminder_created", lang, text=data["text"], date=local_dt.strftime("%d.%m.%Y %H:%M"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_reminder_add_more", lang), callback_data="reminder_add")],
        [InlineKeyboardButton(text=t("btn_reminder_list", lang), callback_data="reminder_list")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "reminder_list")
async def cb_reminder_list(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, tz = s["language"], s.get("timezone", "UTC")
    tz_offset = TIMEZONE_OFFSETS.get(tz, 0)
    reminders = await get_user_reminders(callback.from_user.id)

    if not reminders:
        text = t("reminders_empty", lang)
    else:
        lines = [t("reminders_list_title", lang, count=len(reminders))]
        for r in reminders[:10]:
            try:
                utc_dt = datetime.fromisoformat(r["remind_at"])
                local_dt = utc_dt + timedelta(hours=tz_offset)
                dt_str = local_dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_str = r["remind_at"][:16]
            lines.append(f"• 📅 {dt_str} — {r['text']}")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_reminder_add", lang), callback_data="reminder_add")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_reminders")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
