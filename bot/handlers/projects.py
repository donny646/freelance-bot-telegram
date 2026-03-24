import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import (
    add_project, get_projects, get_project, update_project_status,
    get_clients, get_user_settings,
)
from bot.services.text_parser import parse_date
from bot.i18n import t, format_amount

logger = logging.getLogger(__name__)
router = Router()


class ProjectStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_client = State()
    waiting_for_amount = State()
    waiting_for_deadline = State()


def status_label(status: str, lang: str) -> str:
    key_map = {
        "in_progress": "status_in_progress",
        "completed": "status_completed",
        "paid": "status_paid",
    }
    return t(key_map.get(status, "status_in_progress"), lang)


def get_projects_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_project_add", lang), callback_data="project_add")],
        [
            InlineKeyboardButton(text=t("status_in_progress", lang), callback_data="project_list_in_progress"),
            InlineKeyboardButton(text=t("status_completed", lang), callback_data="project_list_completed"),
        ],
        [InlineKeyboardButton(text=t("status_paid", lang), callback_data="project_list_paid")],
        [InlineKeyboardButton(text=t("btn_project_list_all", lang), callback_data="project_list_all")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "menu_projects")
async def cb_projects_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("projects_menu_title", lang),
        reply_markup=get_projects_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "project_add")
async def cb_project_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProjectStates.waiting_for_title)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="project_cancel")]
    ])
    await callback.message.edit_text(
        t("project_add_title", lang), reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "project_cancel")
async def cb_project_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    await callback.message.edit_text(
        t("projects_menu_title", lang),
        reply_markup=get_projects_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ProjectStates.waiting_for_title)
async def process_project_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ProjectStates.waiting_for_client)
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]

    clients = await get_clients(message.from_user.id)
    if clients:
        buttons = []
        for c in clients[:10]:
            buttons.append([
                InlineKeyboardButton(text=f"👤 {c['name']}", callback_data=f"proj_client_{c['id']}")
            ])
        buttons.append([InlineKeyboardButton(text=t("btn_no_client", lang), callback_data="proj_client_none")])
        await message.answer(t("project_add_client", lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await state.update_data(client_id=None)
        await state.set_state(ProjectStates.waiting_for_amount)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="proj_amount_skip")]
        ])
        await message.answer(t("project_add_amount", lang), reply_markup=keyboard)


@router.callback_query(F.data.startswith("proj_client_"))
async def cb_project_client(callback: CallbackQuery, state: FSMContext):
    client_str = callback.data.replace("proj_client_", "")
    client_id = None if client_str == "none" else int(client_str)
    await state.update_data(client_id=client_id)
    await state.set_state(ProjectStates.waiting_for_amount)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_skip", lang), callback_data="proj_amount_skip")]
    ])
    await callback.message.edit_text(t("project_add_amount", lang), reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "proj_amount_skip", ProjectStates.waiting_for_amount)
async def cb_project_amount_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(amount=0)
    await state.set_state(ProjectStates.waiting_for_deadline)
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_no_deadline", lang), callback_data="proj_deadline_skip")]
    ])
    await callback.message.edit_text(t("project_add_deadline", lang), reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.message(ProjectStates.waiting_for_amount)
async def process_project_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", ".").replace("₽", "").replace("$", "").replace("€", "").replace("£", "").replace("₴", "").strip())
    except ValueError:
        amount = 0
    await state.update_data(amount=amount)
    await state.set_state(ProjectStates.waiting_for_deadline)
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_no_deadline", lang), callback_data="proj_deadline_skip")]
    ])
    await message.answer(t("project_add_deadline", lang), reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "proj_deadline_skip", ProjectStates.waiting_for_deadline)
async def cb_deadline_skip(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _save_project(callback.message, state, data, deadline=None, user_id=callback.from_user.id)
    await callback.answer()


@router.message(ProjectStates.waiting_for_deadline)
async def process_project_deadline(message: Message, state: FSMContext):
    deadline = parse_date(message.text)
    data = await state.get_data()
    await _save_project(message, state, data, deadline=deadline, user_id=message.from_user.id)


async def _save_project(message: Message, state: FSMContext, data: dict, deadline: str, user_id: int):
    s = await get_user_settings(user_id)
    lang, currency = s["language"], s["currency"]

    await add_project(
        user_id=user_id,
        title=data["title"],
        client_id=data.get("client_id"),
        deadline=deadline,
        amount=data.get("amount", 0),
    )
    await state.clear()

    amount_line = t("project_amount_line", lang, amount=format_amount(data.get("amount", 0), currency)) if data.get("amount") else ""
    deadline_line = ""
    if deadline:
        try:
            dt = datetime.fromisoformat(deadline)
            deadline_line = t("project_deadline_line", lang, date=dt.strftime("%d.%m.%Y"))
        except Exception:
            pass

    text = t("project_created", lang, title=data["title"], amount=amount_line, deadline=deadline_line)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_project_add_more", lang), callback_data="project_add")],
        [InlineKeyboardButton(text=t("btn_project_list_all", lang), callback_data="project_list_all")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("project_list_"))
async def cb_project_list(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]

    filter_map = {
        "project_list_in_progress": "in_progress",
        "project_list_completed": "completed",
        "project_list_paid": "paid",
        "project_list_all": None,
    }
    status_filter = filter_map.get(callback.data)
    projects = await get_projects(callback.from_user.id, status=status_filter)

    if not projects:
        text = t("projects_empty", lang)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t("btn_project_add", lang), callback_data="project_add")],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_projects")],
        ])
    else:
        title_label = status_label(status_filter, lang) if status_filter else t("btn_project_list_all", lang)
        text = f"<b>{title_label}</b> ({len(projects)})\n\n"
        buttons = []
        for p in projects[:15]:
            client_str = f" · {p['client_name']}" if p.get("client_name") else ""
            slabel = status_label(p["status"], lang)
            amount_str = f" · {format_amount(p['amount'], currency)}" if p.get("amount") else ""
            buttons.append([
                InlineKeyboardButton(
                    text=f"{slabel} {p['title']}{client_str}{amount_str}",
                    callback_data=f"project_view_{p['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton(text=t("btn_project_add", lang), callback_data="project_add")])
        buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu_projects")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("project_view_"))
async def cb_project_view(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]
    project_id = int(callback.data.split("_")[-1])
    project = await get_project(project_id, callback.from_user.id)

    if not project:
        await callback.answer(t("project_not_found", lang), show_alert=True)
        return

    created = datetime.fromisoformat(project["created_at"]).strftime("%d.%m.%Y")
    slabel = status_label(project["status"], lang)
    client_line = f"\n👤 <b>{'Client' if lang == 'en' else 'Клієнт' if lang == 'uk' else 'Клиент'}:</b> {project['client_name']}" if project.get("client_name") else ""
    amount_line = t("project_amount_line", lang, amount=format_amount(project["amount"], currency)) if project.get("amount") else ""
    deadline_line = ""
    if project.get("deadline"):
        try:
            dl = datetime.fromisoformat(project["deadline"]).strftime("%d.%m.%Y")
            deadline_line = t("project_deadline_line", lang, date=dl)
        except Exception:
            pass

    text = (
        f"📁 <b>{project['title']}</b>\n"
        f"{t('status_in_progress', lang) if project['status'] == 'in_progress' else slabel}{client_line}{amount_line}{deadline_line}"
        f"{t('project_created_at', lang, date=created)}"
    )

    status_buttons = []
    if project["status"] != "in_progress":
        status_buttons.append(InlineKeyboardButton(text=t("status_in_progress", lang), callback_data=f"proj_status_{project_id}_in_progress"))
    if project["status"] != "completed":
        status_buttons.append(InlineKeyboardButton(text=t("status_completed", lang), callback_data=f"proj_status_{project_id}_completed"))
    if project["status"] != "paid":
        status_buttons.append(InlineKeyboardButton(text=t("status_paid", lang), callback_data=f"proj_status_{project_id}_paid"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        status_buttons,
        [InlineKeyboardButton(text=t("btn_project_list_all", lang), callback_data="project_list_all")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("proj_status_"))
async def cb_update_status(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]
    parts = callback.data.split("_")
    project_id = int(parts[2])
    new_status = "_".join(parts[3:])

    await update_project_status(project_id, callback.from_user.id, new_status)
    await callback.answer(status_label(new_status, lang))

    project = await get_project(project_id, callback.from_user.id)
    if project:
        slabel = status_label(project["status"], lang)
        client_line = f"\n👤 <b>{'Client' if lang == 'en' else 'Клієнт' if lang == 'uk' else 'Клиент'}:</b> {project['client_name']}" if project.get("client_name") else ""
        amount_line = t("project_amount_line", lang, amount=format_amount(project["amount"], currency)) if project.get("amount") else ""

        text = f"📁 <b>{project['title']}</b>\n{slabel}{client_line}{amount_line}"

        status_buttons = []
        if project["status"] != "in_progress":
            status_buttons.append(InlineKeyboardButton(text=t("status_in_progress", lang), callback_data=f"proj_status_{project_id}_in_progress"))
        if project["status"] != "completed":
            status_buttons.append(InlineKeyboardButton(text=t("status_completed", lang), callback_data=f"proj_status_{project_id}_completed"))
        if project["status"] != "paid":
            status_buttons.append(InlineKeyboardButton(text=t("status_paid", lang), callback_data=f"proj_status_{project_id}_paid"))

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            status_buttons,
            [InlineKeyboardButton(text=t("btn_project_list_all", lang), callback_data="project_list_all")],
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
