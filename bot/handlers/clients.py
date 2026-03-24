import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import add_client, get_clients, get_client, get_user_settings
from bot.i18n import t

logger = logging.getLogger(__name__)
router = Router()


class ClientStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_notes = State()


def get_clients_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_client_add", lang), callback_data="client_add")],
        [InlineKeyboardButton(text=t("btn_client_list", lang), callback_data="client_list")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "menu_clients")
async def cb_clients_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("clients_menu_title", lang),
        reply_markup=get_clients_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "client_add")
async def cb_client_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClientStates.waiting_for_name)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="client_cancel")]
    ])
    await callback.message.edit_text(
        t("client_add_name", lang), reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "client_cancel")
async def cb_client_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("clients_menu_title", lang),
        reply_markup=get_clients_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ClientStates.waiting_for_name)
async def process_client_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ClientStates.waiting_for_contact)
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="client_skip_contact")]
    ])
    await message.answer(t("client_add_contact", lang), reply_markup=keyboard)


@router.callback_query(F.data == "client_skip_contact", ClientStates.waiting_for_contact)
async def cb_skip_contact(callback: CallbackQuery, state: FSMContext):
    await state.update_data(contact=None)
    await state.set_state(ClientStates.waiting_for_notes)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="client_skip_notes")]
    ])
    await callback.message.edit_text(t("client_add_notes", lang), reply_markup=keyboard)
    await callback.answer()


@router.message(ClientStates.waiting_for_contact)
async def process_client_contact(message: Message, state: FSMContext):
    await state.update_data(contact=message.text.strip())
    await state.set_state(ClientStates.waiting_for_notes)
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="client_skip_notes")]
    ])
    await message.answer(t("client_add_notes", lang), reply_markup=keyboard)


@router.callback_query(F.data == "client_skip_notes", ClientStates.waiting_for_notes)
async def cb_skip_notes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _save_client(callback.message, state, data["name"], data.get("contact"), None, callback.from_user.id)
    await callback.answer()


@router.message(ClientStates.waiting_for_notes)
async def process_client_notes(message: Message, state: FSMContext):
    data = await state.get_data()
    await _save_client(message, state, data["name"], data.get("contact"), message.text.strip(), message.from_user.id)


async def _save_client(message: Message, state: FSMContext, name: str, contact: str, notes: str, user_id: int):
    s = await get_user_settings(user_id)
    lang = s["language"]
    await add_client(user_id, name, contact, notes)
    await state.clear()

    contact_line = t("client_contact_line", lang, contact=contact) if contact else ""
    notes_line = t("client_notes_line", lang, notes=notes) if notes else ""
    text = t("client_added", lang, name=name, contact=contact_line, notes=notes_line)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_client_add_more", lang), callback_data="client_add")],
        [InlineKeyboardButton(text=t("btn_client_list", lang), callback_data="client_list")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "client_list")
async def cb_client_list(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    clients = await get_clients(callback.from_user.id)

    if not clients:
        text = t("clients_empty", lang)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_client_add", lang), callback_data="client_add")],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_clients")],
        ])
    else:
        text = t("clients_list_title", lang, count=len(clients))
        buttons = []
        for c in clients[:20]:
            contact_short = f" — {c['contact'][:20]}" if c["contact"] else ""
            buttons.append([
                InlineKeyboardButton(
                    text=f"👤 {c['name']}{contact_short}",
                    callback_data=f"client_view_{c['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text=t("btn_client_add", lang), callback_data="client_add")])
        buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_clients")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("client_view_"))
async def cb_client_view(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    client_id = int(callback.data.split("_")[-1])
    client = await get_client(client_id, callback.from_user.id)

    if not client:
        await callback.answer(t("client_not_found", lang), show_alert=True)
        return

    created = datetime.fromisoformat(client["created_at"]).strftime("%d.%m.%Y")
    contact_line = t("client_contact_line", lang, contact=client["contact"]) if client["contact"] else ""
    notes_line = t("client_notes_line", lang, notes=client["notes"]) if client["notes"] else ""
    added_line = t("client_added_line", lang, date=created)

    text = f"👤 <b>{client['name']}</b>{contact_line}{notes_line}{added_line}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_client_list", lang), callback_data="client_list")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
