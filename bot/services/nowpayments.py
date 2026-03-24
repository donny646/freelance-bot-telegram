import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

NOWPAYMENTS_API = "https://api.nowpayments.io/v1"

# Human-readable label → NOWPayments currency code
COIN_CODES = {
    "BTC":         "btc",
    "ETH":         "eth",
    "USDT(TRC20)": "usdttrc20",
    "USDT(ERC20)": "usdterc20",
    "TON":         "ton",
    "LTC":         "ltc",
    "BNB":         "bnbbsc",
    "SOL":         "sol",
    "TRX":         "trx",
    "USDC":        "usdc",
}

# Short key used in callback_data → NOWPayments code
COIN_SHORT = {
    "btc":   "btc",
    "eth":   "eth",
    "usdtt": "usdttrc20",
    "usdti": "usdterc20",
    "ton":   "ton",
    "ltc":   "ltc",
    "bnb":   "bnbbsc",
    "sol":   "sol",
    "trx":   "trx",
    "usdc":  "usdc",
}

# Reverse map: short key → display label
SHORT_DISPLAY = {v: k for k, v in {
    "btc":   "BTC",
    "eth":   "ETH",
    "usdtt": "USDT (TRC20)",
    "usdti": "USDT (ERC20)",
    "ton":   "TON",
    "ltc":   "LTC",
    "bnb":   "BNB (BSC)",
    "sol":   "SOL",
    "trx":   "TRX",
    "usdc":  "USDC",
}.items()}

# Paid statuses
PAID_STATUSES = {"finished", "confirmed", "sending"}


def np_token() -> Optional[str]:
    return os.getenv("NOWPAYMENTS_API_KEY") or None


async def create_payment(
    price_amount: float,
    pay_currency_short: str,
    order_id: str,
    order_description: str,
) -> Optional[dict]:
    """Create a NOWPayments invoice. Returns the full payment object or None."""
    token = np_token()
    if not token:
        return None
    np_code = COIN_SHORT.get(pay_currency_short, pay_currency_short)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{NOWPAYMENTS_API}/payment",
                headers={"x-api-key": token, "Content-Type": "application/json"},
                json={
                    "price_amount": price_amount,
                    "price_currency": "usd",
                    "pay_currency": np_code,
                    "order_id": order_id,
                    "order_description": order_description,
                },
            ) as resp:
                data = await resp.json()
                if "payment_id" in data:
                    return data
                logger.error(f"NOWPayments create_payment error: {data}")
                return None
    except Exception as e:
        logger.error(f"NOWPayments create_payment exception: {e}")
        return None


async def get_payment_status(payment_id: int) -> Optional[str]:
    """Returns the payment status string or None on error."""
    token = np_token()
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{NOWPAYMENTS_API}/payment/{payment_id}",
                headers={"x-api-key": token},
            ) as resp:
                data = await resp.json()
                return data.get("payment_status")
    except Exception as e:
        logger.error(f"NOWPayments get_payment_status exception: {e}")
        return None
