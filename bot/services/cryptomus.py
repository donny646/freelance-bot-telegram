import os
import hashlib
import base64
import json
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

CRYPTOMUS_API = "https://api.cryptomus.com/v1"

PAID_STATUSES = {"paid", "paid_over", "confirm_check"}

# coin_short → (to_currency, network or None)
COIN_MAP = {
    "btc":   ("BTC",  None),
    "eth":   ("ETH",  "eth"),
    "usdtt": ("USDT", "tron"),
    "usdti": ("USDT", "eth"),
    "ton":   ("TON",  "ton"),
    "ltc":   ("LTC",  "ltc"),
    "bnb":   ("BNB",  "bsc"),
    "sol":   ("SOL",  "sol"),
    "trx":   ("TRX",  "tron"),
    "usdc":  ("USDC", "eth"),
}


def cm_merchant() -> Optional[str]:
    return os.getenv("CRYPTOMUS_MERCHANT_ID") or None


def cm_key() -> Optional[str]:
    return os.getenv("CRYPTOMUS_PAYMENT_KEY") or None


def is_configured() -> bool:
    return bool(cm_merchant() and cm_key())


def _sign(data: dict) -> str:
    body = json.dumps(data, separators=(",", ":"))
    b64 = base64.b64encode(body.encode()).decode()
    return hashlib.md5((b64 + (cm_key() or "")).encode()).hexdigest()


def _headers(data: dict) -> dict:
    return {
        "merchant": cm_merchant() or "",
        "sign": _sign(data),
        "Content-Type": "application/json",
    }


async def create_payment(
    amount: float,
    coin_short: str,
    order_id: int,
    description: str,
) -> Optional[dict]:
    if not is_configured():
        return None

    to_currency, network = COIN_MAP.get(coin_short, ("USDT", None))
    data: dict = {
        "amount": str(amount),
        "currency": "USD",
        "to_currency": to_currency,
        "order_id": str(order_id),
        "url_return": "https://t.me/freelanceplan_bot",
    }
    if network:
        data["network"] = network

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOMUS_API}/payment",
                headers=_headers(data),
                json=data,
            ) as resp:
                result = await resp.json()
                if result.get("state") == 0:
                    return result.get("result")
                logger.error(f"Cryptomus create_payment error: {result}")
                return None
    except Exception as e:
        logger.error(f"Cryptomus create_payment exception: {e}")
        return None


async def get_payment_status(order_id: int) -> Optional[str]:
    if not is_configured():
        return None

    data = {"order_id": str(order_id)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOMUS_API}/payment/info",
                headers=_headers(data),
                json=data,
            ) as resp:
                result = await resp.json()
                if result.get("state") == 0:
                    return result["result"].get("payment_status")
                logger.error(f"Cryptomus get_status error: {result}")
                return None
    except Exception as e:
        logger.error(f"Cryptomus get_status exception: {e}")
        return None
