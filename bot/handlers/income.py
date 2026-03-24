import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import add_income, get_incomes, get_user_settings
from bot.services.text_parser import parse_income_message
from bot.i18n import t, format_amount

logger = logging.getLogger(__name__)
router = Router()


class IncomeStates(StatesGroup):
    waiting_for_income = State()


def get_income_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_income_add", lang), callback_data="income_add")],
        [InlineKeyboardButton(text=t("btn_income_list", lang), callback_data="income_list")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "menu_income")
async def cb_income_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("income_menu_title", lang),
        reply_markup=get_income_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "income_add")
async def cb_income_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(IncomeStates.waiting_for_income)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="income_cancel")]
    ])
    await callback.message.edit_text(
        t("income_add_title", lang), reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "income_cancel")
async def cb_income_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("income_menu_title", lang),
        reply_markup=get_income_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IncomeStates.waiting_for_income)
async def process_income_state(message: Message, state: FSMContext):
    s = await get_user_settings(message.from_user.id)
    lang, currency = s["language"], s["currency"]

    result = parse_income_message(message.text)
    if result:
        description, amount = result
        await add_income(message.from_user.id, description, amount)
        await state.clear()
        text = t("income_added", lang, description=description, amount=format_amount(amount, currency))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_income_add_more", lang), callback_data="income_add")],
            [InlineKeyboardButton(text=t("btn_income_list", lang), callback_data="income_list")],
            [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(t("income_parse_error", lang), parse_mode="HTML")


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def process_quick_income(message: Message):
    """Quick income entry — only fires when no FSM state is active."""
    result = parse_income_message(message.text)
    if result:
        description, amount = result
        s = await get_user_settings(message.from_user.id)
        lang, currency = s["language"], s["currency"]

        await add_income(message.from_user.id, description, amount)
        text = t("income_added", lang, description=description, amount=format_amount(amount, currency))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_income_add_more", lang), callback_data="income_add")],
            [InlineKeyboardButton(text=t("btn_income_list", lang), callback_data="income_list")],
            [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
        ])
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "income_list")
async def cb_income_list(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]
    incomes = await get_incomes(callback.from_user.id, limit=10)

    if not incomes:
        text = t("income_empty", lang)
    else:
        total = sum(i["amount"] for i in incomes)
        lines = [t("income_history_title", lang)]
        for inc in incomes:
            dt = datetime.fromisoformat(inc["created_at"]).strftime("%d.%m")
            lines.append(f"• {dt} — {inc['description']}: <b>{format_amount(inc['amount'], currency)}</b>")
        lines.append(t("income_total", lang, total=format_amount(total, currency)))
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_income_add", lang), callback_data="income_add")],
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_income")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
