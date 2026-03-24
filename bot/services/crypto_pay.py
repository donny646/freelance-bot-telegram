import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

CRYPTO_PAY_API = "https://pay.crypt.bot/api"


def crypto_token() -> Optional[str]:
    return os.getenv("CRYPTO_BOT_TOKEN") or None


async def create_invoice(
    asset: str,
    amount: str,
    description: str,
    payload: str,
    bot_username: str = "freelanceplan_bot",
) -> Optional[dict]:
    token = crypto_token()
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTO_PAY_API}/createInvoice",
                headers={"Crypto-Pay-API-Token": token},
                json={
                    "asset": asset,
                    "amount": amount,
                    "description": description,
                    "payload": payload,
                    "paid_btn_name": "openBot",
                    "paid_btn_url": f"https://t.me/{bot_username}",
                },
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data["result"]
                logger.error(f"CryptoPay createInvoice error: {data}")
                return None
    except Exception as e:
        logger.error(f"CryptoPay request failed: {e}")
        return None


async def get_invoice_status(invoice_id: int) -> Optional[str]:
    """Returns 'active', 'paid', or 'expired', or None on error."""
    token = crypto_token()
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CRYPTO_PAY_API}/getInvoices",
                headers={"Crypto-Pay-API-Token": token},
                params={"invoice_ids": str(invoice_id)},
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    items = data["result"].get("items", [])
                    if items:
                        return items[0].get("status")
                logger.error(f"CryptoPay getInvoices error: {data}")
                return None
    except Exception as e:
        logger.error(f"CryptoPay status check failed: {e}")
        return None
