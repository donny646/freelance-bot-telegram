import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.db import (
    admin_get_stats, admin_get_recent_users, admin_grant_subscription,
    admin_get_all_user_ids,
)

logger = logging.getLogger(__name__)
router = Router()

ADMIN_IDS = {6502920835}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AdminStates(StatesGroup):
    waiting_grant_user_id = State()
    waiting_grant_months = State()
    waiting_broadcast = State()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton(text="🎁 Grant Subscription", callback_data="admin_grant"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
        ],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👑 <b>Admin Panel</b>\n\nChoose an action:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    stats = await admin_get_stats()
    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{stats['total_users']}</b>\n"
        f"✅ Active subscriptions: <b>{stats['active_subs']}</b>\n"
        f"🕐 On trial: <b>{stats['on_trial']}</b>\n"
        f"❌ Expired / no access: <b>{stats['expired']}</b>\n\n"
        f"💰 Total income recorded: <b>{stats['total_income']:.0f}</b>\n"
        f"📁 Total projects: <b>{stats['total_projects']}</b>\n"
        f"👤 Total clients: <b>{stats['total_clients']}</b>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    users = await admin_get_recent_users(limit=15)
    if not users:
        text = "👥 No users yet."
    else:
        lines = ["👥 <b>Recent Users</b> (last 15)\n"]
        for u in users:
            name = u.get("full_name") or "—"
            username = f"@{u['username']}" if u.get("username") else "no username"
            uid = u["user_id"]
            sub = u.get("subscription_until")
            trial = u.get("trial_started")
            if sub:
                status = "✅ sub"
            elif trial:
                status = "🕐 trial"
            else:
                status = "❌"
            lines.append(f"• <code>{uid}</code> {name} ({username}) — {status}")
        text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_grant")
async def cb_admin_grant(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_grant_user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")],
    ])
    await callback.message.edit_text(
        "🎁 <b>Grant Subscription</b>\n\nEnter the user's Telegram ID:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_grant_user_id)
async def admin_grant_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Please send a valid numeric user ID.")
        return
    await state.update_data(target_user_id=int(text))
    await state.set_state(AdminStates.waiting_grant_months)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 month", callback_data="grant_months_1"),
            InlineKeyboardButton(text="3 months", callback_data="grant_months_3"),
            InlineKeyboardButton(text="12 months", callback_data="grant_months_12"),
        ],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")],
    ])
    await message.answer(
        f"✅ User ID: <code>{text}</code>\n\nHow many months to grant?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("grant_months_"))
async def cb_grant_months(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    months = int(callback.data.split("_")[-1])
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await callback.answer("Error: no user selected.", show_alert=True)
        await state.clear()
        return
    await admin_grant_subscription(target_user_id, months)
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Menu", callback_data="admin_back")],
    ])
    await callback.message.edit_text(
        f"✅ Granted <b>{months} month(s)</b> to user <code>{target_user_id}</code>.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer("Done!")


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_broadcast)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_cancel")],
    ])
    await callback.message.edit_text(
        "📢 <b>Broadcast Message</b>\n\nType the message to send to all users:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    broadcast_text = message.text
    await state.clear()
    user_ids = await admin_get_all_user_ids()
    sent = 0
    failed = 0
    status_msg = await message.answer(f"📤 Sending to {len(user_ids)} users...")
    for uid in user_ids:
        try:
            await bot.send_message(uid, broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"📢 <b>Broadcast complete</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 <b>Admin Panel</b>\n\nChoose an action:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 <b>Admin Panel</b>\n\nChoose an action:",
        reply_markup=admin_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Cancelled")
