import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.db import get_analytics, get_monthly_incomes, get_user_settings
from bot.i18n import t, format_amount

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "menu_analytics")
async def cb_analytics(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]
    data = await get_analytics(callback.from_user.id)

    project_stats = data["project_stats"]
    in_progress = project_stats.get("in_progress", 0)
    completed = project_stats.get("completed", 0)
    paid = project_stats.get("paid", 0)
    total_projects = in_progress + completed + paid
    avg_str = format_amount(data["avg_check"], currency) if data["avg_check"] > 0 else "—"

    text = t(
        "analytics_title", lang,
        month=data["month"],
        monthly=format_amount(data["monthly_income"], currency),
        count=data["monthly_count"],
        avg=avg_str,
        in_progress=in_progress,
        completed=completed,
        paid=paid,
        total_projects=total_projects,
        clients=data["client_count"],
        total_income=format_amount(data["total_income"], currency),
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_analytics_monthly", lang), callback_data="analytics_monthly")],
        [InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "analytics_monthly")
async def cb_analytics_monthly(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang, currency = s["language"], s["currency"]

    now = datetime.now()
    incomes = await get_monthly_incomes(callback.from_user.id, now.year, now.month)

    if not incomes:
        text = f"📅 <b>{now.strftime('%B %Y')}</b>\n\n{t('analytics_no_income', lang)}"
    else:
        total = sum(i["amount"] for i in incomes)
        lines = [f"📅 <b>{now.strftime('%B %Y')}</b> — {format_amount(total, currency)}\n"]
        for inc in incomes:
            dt = datetime.fromisoformat(inc["created_at"]).strftime("%d.%m")
            lines.append(f"• {dt} {inc['description']}: <b>{format_amount(inc['amount'], currency)}</b>")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_analytics_back", lang), callback_data="menu_analytics")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()
