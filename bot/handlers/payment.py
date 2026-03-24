import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command

from bot.database.db import (
    set_subscription, create_payment_record, get_subscription_status, get_user_settings,
    save_crypto_invoice, get_crypto_invoice, mark_crypto_invoice_paid,
)
from bot.i18n import t
import time
from bot.services.cryptomus import (
    is_configured as crypto_configured,
    create_payment as cm_create_payment,
    get_payment_status as cm_get_status,
    PAID_STATUSES,
)

logger = logging.getLogger(__name__)
router = Router()

# ─── Telegram Stars plans ────────────────────────────────────────────────────

PLANS = {
    "1month":  {"months": 1,  "price": 250,  "currency": "XTR", "emoji": "🗓"},
    "3months": {"months": 3,  "price": 640,  "currency": "XTR", "emoji": "📅"},
    "12months":{"months": 12, "price": 2100, "currency": "XTR", "emoji": "🏆"},
}

STARS_SAVINGS = {"1month": "", "3months": " (−15%)", "12months": " (−30%)"}

# ─── Crypto plans (USD prices) ────────────────────────────────────────────────

CRYPTO_PLANS = {
    "1month":  {"months": 1,  "price_usd": 4.99,  "emoji": "🗓"},
    "3months": {"months": 3,  "price_usd": 12.99, "emoji": "📅"},
    "12months":{"months": 12, "price_usd": 39.99, "emoji": "🏆"},
}

CRYPTO_SAVINGS = {"1month": "", "3months": " (−15%)", "12months": " (−30%)"}

# Coins shown in the picker — short key → display label
COINS = {
    "btc":   "Bitcoin (BTC)",
    "eth":   "Ethereum (ETH)",
    "usdtt": "USDT (TRC20)",
    "usdti": "USDT (ERC20)",
    "ton":   "TON",
    "ltc":   "Litecoin (LTC)",
    "bnb":   "BNB (BSC)",
    "sol":   "Solana (SOL)",
    "trx":   "TRON (TRX)",
    "usdc":  "USDC",
}

# ─── Plan name / description display ─────────────────────────────────────────

PLAN_DISPLAY = {
    "ru": {"1month": "1 месяц",   "3months": "3 месяца",  "12months": "12 месяцев"},
    "en": {"1month": "1 month",   "3months": "3 months",  "12months": "12 months"},
    "uk": {"1month": "1 місяць",  "3months": "3 місяці",  "12months": "12 місяців"},
    "fr": {"1month": "1 mois",    "3months": "3 mois",    "12months": "12 mois"},
    "es": {"1month": "1 mes",     "3months": "3 meses",   "12months": "12 meses"},
}

PLAN_DESC = {
    "ru": {
        "1month":  "Полный доступ на 1 месяц",
        "3months": "Полный доступ на 3 месяца (−15%)",
        "12months":"Полный доступ на 12 месяцев (−30%)",
    },
    "en": {
        "1month":  "Full access for 1 month",
        "3months": "Full access for 3 months (−15%)",
        "12months":"Full access for 12 months (−30%)",
    },
    "uk": {
        "1month":  "Повний доступ на 1 місяць",
        "3months": "Повний доступ на 3 місяці (−15%)",
        "12months":"Повний доступ на 12 місяців (−30%)",
    },
    "fr": {
        "1month":  "Accès complet pendant 1 mois",
        "3months": "Accès complet pendant 3 mois (−15%)",
        "12months":"Accès complet pendant 12 mois (−30%)",
    },
    "es": {
        "1month":  "Acceso completo por 1 mes",
        "3months": "Acceso completo por 3 meses (−15%)",
        "12months":"Acceso completo por 12 meses (−30%)",
    },
}

# ─── i18n snippets ────────────────────────────────────────────────────────────

_L = lambda d, lang: d.get(lang, d.get("en", ""))

_CRYPTO_PLANS_TITLE = {
    "ru": "💎 <b>Оплата криптовалютой</b>\n\nЦены в USD — выберите тариф:",
    "en": "💎 <b>Pay with Crypto</b>\n\nPrices in USD — choose a plan:",
    "uk": "💎 <b>Оплата криптовалютою</b>\n\nЦіни в USD — оберіть тариф:",
    "fr": "💎 <b>Payer en crypto</b>\n\nPrix en USD — choisissez un plan :",
    "es": "💎 <b>Pagar con cripto</b>\n\nPrecios en USD — elige un plan:",
}

_COIN_TITLE = {
    "ru": "🪙 <b>Выберите монету</b>\n\nТариф: <b>{plan}</b> — <b>${price}</b>\n\nПользователь получит адрес кошелька и переведёт с любого кошелька:",
    "en": "🪙 <b>Choose a coin</b>\n\nPlan: <b>{plan}</b> — <b>${price}</b>\n\nYou'll receive a wallet address and can pay from any crypto wallet:",
    "uk": "🪙 <b>Оберіть монету</b>\n\nТариф: <b>{plan}</b> — <b>${price}</b>\n\nОтримаєте адресу гаманця і зможете оплатити з будь-якого гаманця:",
    "fr": "🪙 <b>Choisissez une monnaie</b>\n\nPlan : <b>{plan}</b> — <b>${price}</b>\n\nVous recevrez une adresse et pourrez payer depuis n'importe quel portefeuille :",
    "es": "🪙 <b>Elige una moneda</b>\n\nPlan: <b>{plan}</b> — <b>${price}</b>\n\nRecibirás una dirección de wallet y podrás pagar desde cualquier billetera:",
}

_INVOICE_MSG = {
    "ru": (
        "💎 <b>Счёт на оплату</b>\n\n"
        "📋 Тариф: <b>{plan}</b>\n"
        "💰 Сумма: <code>{amount} {coin}</code>\n"
        "📬 Адрес:\n<code>{address}</code>\n\n"
        "⚠️ Отправьте <b>ровно {amount} {coin}</b> на адрес выше с любого кошелька "
        "(MetaMask, Trust Wallet, Binance, аппаратный кошелёк — любой).\n\n"
        "После отправки нажмите <b>✅ Я оплатил</b>."
    ),
    "en": (
        "💎 <b>Payment Invoice</b>\n\n"
        "📋 Plan: <b>{plan}</b>\n"
        "💰 Amount: <code>{amount} {coin}</code>\n"
        "📬 Address:\n<code>{address}</code>\n\n"
        "⚠️ Send <b>exactly {amount} {coin}</b> to the address above from any wallet "
        "(MetaMask, Trust Wallet, Binance, hardware wallet — any).\n\n"
        "After sending, press <b>✅ I've paid</b>."
    ),
    "uk": (
        "💎 <b>Рахунок на оплату</b>\n\n"
        "📋 Тариф: <b>{plan}</b>\n"
        "💰 Сума: <code>{amount} {coin}</code>\n"
        "📬 Адреса:\n<code>{address}</code>\n\n"
        "⚠️ Надішліть <b>рівно {amount} {coin}</b> на вказану адресу з будь-якого гаманця "
        "(MetaMask, Trust Wallet, Binance, апаратний гаманець — будь-який).\n\n"
        "Після відправки натисніть <b>✅ Я оплатив</b>."
    ),
    "fr": (
        "💎 <b>Facture de paiement</b>\n\n"
        "📋 Plan : <b>{plan}</b>\n"
        "💰 Montant : <code>{amount} {coin}</code>\n"
        "📬 Adresse :\n<code>{address}</code>\n\n"
        "⚠️ Envoyez <b>exactement {amount} {coin}</b> à l'adresse ci-dessus depuis n'importe quel portefeuille "
        "(MetaMask, Trust Wallet, Binance, hardware wallet…)\n\n"
        "Après l'envoi, appuyez sur <b>✅ J'ai payé</b>."
    ),
    "es": (
        "💎 <b>Factura de pago</b>\n\n"
        "📋 Plan: <b>{plan}</b>\n"
        "💰 Monto: <code>{amount} {coin}</code>\n"
        "📬 Dirección:\n<code>{address}</code>\n\n"
        "⚠️ Envía <b>exactamente {amount} {coin}</b> a la dirección de arriba desde cualquier billetera "
        "(MetaMask, Trust Wallet, Binance, hardware wallet…)\n\n"
        "Después de enviar, presiona <b>✅ He pagado</b>."
    ),
}

_CHECK_BTN  = {"ru": "✅ Я оплатил",  "en": "✅ I've paid",  "uk": "✅ Я оплатив",  "fr": "✅ J'ai payé",  "es": "✅ He pagado"}
_BACK_BTN   = {"ru": "🔙 Назад",      "en": "🔙 Back",       "uk": "🔙 Назад",       "fr": "🔙 Retour",     "es": "🔙 Atrás"}

_PAID_OK = {
    "ru": "✅ <b>Оплата подтверждена!</b>\n\n🎉 Подписка активирована: <b>{plan}</b>\nВсе функции доступны!\n\nНажмите /start для перехода в меню.",
    "en": "✅ <b>Payment confirmed!</b>\n\n🎉 Subscription activated: <b>{plan}</b>\nAll features unlocked!\n\nPress /start to go to the menu.",
    "uk": "✅ <b>Оплату підтверджено!</b>\n\n🎉 Підписку активовано: <b>{plan}</b>\nУсі функції доступні!\n\nНатисніть /start для переходу в меню.",
    "fr": "✅ <b>Paiement confirmé!</b>\n\n🎉 Abonnement activé : <b>{plan}</b>\nToutes les fonctionnalités débloquées!\n\nAppuyez sur /start pour aller au menu.",
    "es": "✅ <b>¡Pago confirmado!</b>\n\n🎉 Suscripción activada: <b>{plan}</b>\n¡Todas las funciones desbloqueadas!\n\nPresiona /start para ir al menú.",
}

_NOT_PAID = {
    "ru": "⏳ Оплата ещё не подтверждена сетью.\n\nПодождите несколько минут после отправки и попробуйте снова.",
    "en": "⏳ Payment not confirmed by the network yet.\n\nWait a few minutes after sending and try again.",
    "uk": "⏳ Оплату ще не підтверджено мережею.\n\nЗачекайте кілька хвилин після відправки і спробуйте знову.",
    "fr": "⏳ Paiement pas encore confirmé par le réseau.\n\nAttendez quelques minutes après l'envoi et réessayez.",
    "es": "⏳ Pago aún no confirmado por la red.\n\nEspera unos minutos después de enviar e intenta de nuevo.",
}

_EXPIRED = {
    "ru": "❌ Счёт истёк или уже оплачен. Создайте новый через /buy.",
    "en": "❌ Invoice expired or already paid. Create a new one via /buy.",
    "uk": "❌ Рахунок закінчився або вже оплачений. Створіть новий через /buy.",
    "fr": "❌ Facture expirée ou déjà payée. Créez-en une nouvelle via /buy.",
    "es": "❌ Factura caducada o ya pagada. Crea una nueva con /buy.",
}

_INVOICE_ERROR = {
    "ru": "❌ Не удалось создать счёт. Проверьте настройки NOWPayments или попробуйте позже.",
    "en": "❌ Failed to create invoice. Check NOWPayments settings or try later.",
    "uk": "❌ Не вдалось створити рахунок. Перевірте налаштування NOWPayments або спробуйте пізніше.",
    "fr": "❌ Impossible de créer la facture. Vérifiez les paramètres NOWPayments ou réessayez plus tard.",
    "es": "❌ No se pudo crear la factura. Verifica la configuración de NOWPayments o inténtalo más tarde.",
}


# ─── Keyboards ────────────────────────────────────────────────────────────────

_STARS_BTN = {
    "ru": "⭐ Telegram Stars",
    "en": "⭐ Telegram Stars",
    "uk": "⭐ Telegram Stars",
    "fr": "⭐ Telegram Stars",
    "es": "⭐ Telegram Stars",
}
_CRYPTO_BTN = {
    "ru": "💎 Криптовалюта",
    "en": "💎 Cryptocurrency",
    "uk": "💎 Криптовалюта",
    "fr": "💎 Cryptomonnaie",
    "es": "💎 Criptomoneda",
}


def get_buy_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Main payment method picker."""
    buttons = [
        [InlineKeyboardButton(text=_L(_STARS_BTN, lang), callback_data="stars_menu")],
    ]
    buttons.append([InlineKeyboardButton(text=_L(_CRYPTO_BTN, lang), callback_data="crypto_menu")])
    buttons.append([InlineKeyboardButton(text=t("btn_back_main", lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_stars_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Stars plan selection."""
    display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
    buttons = []
    for plan_id, plan in PLANS.items():
        title = display.get(plan_id, plan_id)
        savings = STARS_SAVINGS.get(plan_id, "")
        buttons.append([InlineKeyboardButton(
            text=f"{plan['emoji']} {title} — ⭐ {plan['price']} Stars{savings}",
            callback_data=f"buy_{plan_id}",
        )])
    buttons.append([InlineKeyboardButton(text=_L(_BACK_BTN, lang), callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_crypto_plan_keyboard(lang: str) -> InlineKeyboardMarkup:
    display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
    buttons = []
    for plan_id, plan in CRYPTO_PLANS.items():
        title = display.get(plan_id, plan_id)
        savings = CRYPTO_SAVINGS.get(plan_id, "")
        buttons.append([InlineKeyboardButton(
            text=f"{plan['emoji']} {title} — ${plan['price_usd']}{savings}",
            callback_data=f"cplan_{plan_id}",
        )])
    buttons.append([InlineKeyboardButton(text=_L(_BACK_BTN, lang), callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_coin_keyboard(lang: str, plan_id: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for short, label in COINS.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"casset_{plan_id}_{short}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=_L(_BACK_BTN, lang), callback_data="crypto_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_invoice_keyboard(lang: str, invoice_id: int, pay_url: str = "") -> InlineKeyboardMarkup:
    buttons = []
    if pay_url:
        buttons.append([InlineKeyboardButton(text="🌐 Pay on Cryptomus", url=pay_url)])
    buttons.append([InlineKeyboardButton(text=_L(_CHECK_BTN, lang), callback_data=f"ccheck_{invoice_id}")])
    buttons.append([InlineKeyboardButton(text=_L(_BACK_BTN, lang),  callback_data="buy_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_paywall_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_buy_sub", lang), callback_data="buy_menu")],
    ])


async def send_paywall(message: Message, edit: bool = False):
    try:
        s = await get_user_settings(message.chat.id)
        lang = s.get("language", "ru")
    except Exception:
        lang = "ru"
    text = t("paywall_text", lang)
    if edit:
        await message.edit_text(text, reply_markup=get_paywall_keyboard(lang), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=get_paywall_keyboard(lang), parse_mode="HTML")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _buy_info(status: dict, lang: str) -> str:
    if status["type"] == "trial":
        return t("buy_info_trial", lang, days=status["days_left"])
    elif status["type"] == "subscription":
        return t("buy_info_active", lang, days=status["days_left"])
    return t("buy_info_none", lang)


_STARS_TITLE = {
    "ru": "⭐ <b>Оплата Telegram Stars</b>\n\nВыберите тариф:",
    "en": "⭐ <b>Pay with Telegram Stars</b>\n\nChoose a plan:",
    "uk": "⭐ <b>Оплата Telegram Stars</b>\n\nОберіть тариф:",
    "fr": "⭐ <b>Payer avec Telegram Stars</b>\n\nChoisissez un plan :",
    "es": "⭐ <b>Pagar con Telegram Stars</b>\n\nElige un plan:",
}

_METHOD_TITLE = {
    "ru": "💳 <b>Выберите способ оплаты</b>",
    "en": "💳 <b>Choose payment method</b>",
    "uk": "💳 <b>Оберіть спосіб оплати</b>",
    "fr": "💳 <b>Choisissez un mode de paiement</b>",
    "es": "💳 <b>Elige el método de pago</b>",
}


def _buy_text(lang: str, info: str) -> str:
    header = _L(_METHOD_TITLE, lang)
    return f"{header}\n\n{info}"


async def _get_lang(uid: int) -> str:
    try:
        return (await get_user_settings(uid)).get("language", "ru")
    except Exception:
        return "ru"


# ─── Stars handlers ───────────────────────────────────────────────────────────

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    s = await get_user_settings(message.from_user.id)
    lang = s["language"]
    status = await get_subscription_status(message.from_user.id)
    await message.answer(_buy_text(lang, _buy_info(status, lang)),
                         reply_markup=get_buy_keyboard(lang), parse_mode="HTML")


@router.callback_query(F.data == "buy_menu")
async def cb_buy_menu(callback: CallbackQuery):
    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    status = await get_subscription_status(callback.from_user.id)
    await callback.message.edit_text(_buy_text(lang, _buy_info(status, lang)),
                                     reply_markup=get_buy_keyboard(lang), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stars_menu")
async def cb_stars_menu(callback: CallbackQuery):
    lang = await _get_lang(callback.from_user.id)
    await callback.message.edit_text(
        _L(_STARS_TITLE, lang),
        reply_markup=get_stars_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_") & ~F.data.in_({"buy_menu"}))
async def cb_buy_plan(callback: CallbackQuery):
    plan_id = callback.data.replace("buy_", "")
    plan = PLANS.get(plan_id)
    if not plan:
        await callback.answer("Plan not found", show_alert=True)
        return

    s = await get_user_settings(callback.from_user.id)
    lang = s["language"]
    display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
    desc_map = PLAN_DESC.get(lang, PLAN_DESC["en"])

    await create_payment_record(callback.from_user.id, plan_id, plan["price"], "XTR")
    try:
        await callback.message.answer_invoice(
            title=f"FreelanceBot — {display.get(plan_id, plan_id)}",
            description=desc_map.get(plan_id, ""),
            payload=f"sub_{plan_id}_{callback.from_user.id}",
            currency="XTR",
            prices=[LabeledPrice(label=display.get(plan_id, plan_id), amount=plan["price"])],
            provider_token="",
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Stars invoice error: {e}")
        await callback.answer("Error creating invoice. Please try again.", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    logger.info(f"Stars payment from {message.from_user.id}: {payload}")

    parts = payload.split("_")
    plan_id = "_".join(parts[1:-1]) if len(parts) >= 3 else (parts[1] if len(parts) == 2 else None)
    plan = PLANS.get(plan_id)

    if plan:
        await set_subscription(message.from_user.id, plan["months"], payment.telegram_payment_charge_id)
        s = await get_user_settings(message.from_user.id)
        lang = s["language"]
        display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
        await message.answer(t("payment_success", lang, plan=display.get(plan_id, plan_id)),
                             parse_mode="HTML")
    else:
        await message.answer("✅ Payment received! Subscription activated.\nPress /start to continue.")


# ─── Crypto handlers ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "crypto_menu")
async def cb_crypto_menu(callback: CallbackQuery):
    lang = await _get_lang(callback.from_user.id)
    await callback.answer(t("crypto_coming_soon", lang), show_alert=True)


@router.callback_query(F.data.startswith("cplan_"))
async def cb_crypto_plan(callback: CallbackQuery):
    if not crypto_configured():
        await callback.answer("Crypto payments not configured.", show_alert=True)
        return
    plan_id = callback.data.replace("cplan_", "")
    plan = CRYPTO_PLANS.get(plan_id)
    if not plan:
        await callback.answer("Plan not found", show_alert=True)
        return

    lang = await _get_lang(callback.from_user.id)
    display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])

    text = _L(_COIN_TITLE, lang).format(
        plan=display.get(plan_id, plan_id),
        price=plan["price_usd"],
    )
    await callback.message.edit_text(text, reply_markup=get_coin_keyboard(lang, plan_id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("casset_"))
async def cb_crypto_asset(callback: CallbackQuery):
    if not crypto_configured():
        await callback.answer("Crypto payments not configured.", show_alert=True)
        return

    # callback_data: casset_<plan_id>_<coin_short>
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.answer("Invalid data", show_alert=True)
        return
    plan_id, coin_short = parts[1], parts[2]
    plan = CRYPTO_PLANS.get(plan_id)
    if not plan:
        await callback.answer("Plan not found", show_alert=True)
        return

    lang = await _get_lang(callback.from_user.id)
    display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
    plan_title = display.get(plan_id, plan_id)

    await callback.answer("⏳")

    # Generate a unique integer order_id (millisecond timestamp)
    order_id = int(time.time() * 1000) % 2147483647

    payment = await cm_create_payment(
        amount=plan["price_usd"],
        coin_short=coin_short,
        order_id=order_id,
        description=f"FreelanceBot — {plan_title}",
    )

    if not payment:
        await callback.message.answer(_L(_INVOICE_ERROR, lang), parse_mode="HTML")
        return

    pay_address = payment.get("address", "")
    pay_amount  = str(payment.get("payer_amount", payment.get("amount", "")))
    pay_currency= payment.get("payer_currency", payment.get("to_currency", coin_short)).upper()

    await save_crypto_invoice(
        invoice_id=order_id,
        user_id=callback.from_user.id,
        plan=plan_id,
        asset=coin_short,
        pay_address=pay_address,
        pay_amount=pay_amount,
    )

    text = _L(_INVOICE_MSG, lang).format(
        plan=plan_title,
        amount=pay_amount,
        coin=pay_currency,
        address=pay_address,
    )

    # Cryptomus also provides a hosted payment page URL
    pay_url = payment.get("url", "")
    kb = get_invoice_keyboard(lang, order_id, pay_url=pay_url)
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("ccheck_"))
async def cb_crypto_check(callback: CallbackQuery):
    try:
        payment_id = int(callback.data.replace("ccheck_", ""))
    except ValueError:
        await callback.answer("Invalid invoice", show_alert=True)
        return

    lang = await _get_lang(callback.from_user.id)
    record = await get_crypto_invoice(payment_id)

    if not record:
        await callback.answer(_L(_EXPIRED, lang), show_alert=True)
        return

    if record["status"] == "paid":
        await callback.answer(_L(_EXPIRED, lang), show_alert=True)
        return

    status = await cm_get_status(payment_id)

    if status in PAID_STATUSES:
        plan_id = record["plan"]
        plan = CRYPTO_PLANS.get(plan_id)
        if plan:
            await mark_crypto_invoice_paid(payment_id)
            await set_subscription(callback.from_user.id, plan["months"], f"crypto_{payment_id}")
            await create_payment_record(
                callback.from_user.id, plan_id,
                int(plan["price_usd"] * 100), record["asset"].upper()
            )
            display = PLAN_DISPLAY.get(lang, PLAN_DISPLAY["en"])
            text = _L(_PAID_OK, lang).format(plan=display.get(plan_id, plan_id))
            await callback.message.answer(text, parse_mode="HTML")
            await callback.answer("✅")
        else:
            await callback.answer("Plan error.", show_alert=True)
    elif status in ("wait", "confirm_check", "wrong_amount"):
        await callback.answer(_L(_NOT_PAID, lang), show_alert=True)
    else:
        await callback.answer(_L(_EXPIRED, lang), show_alert=True)
