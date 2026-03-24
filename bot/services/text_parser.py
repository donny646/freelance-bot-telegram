import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Паттерны для парсинга суммы
AMOUNT_PATTERNS = [
    r"(\d[\d\s]*[\d])\s*(?:руб|р|₽|rub|usd|\$|€|eur)?",
    r"(\d+(?:[.,]\d+)?)\s*(?:тыс|тысяч|к|k|kk)?",
]

# Ключевые слова для разделения описания и суммы
SEPARATORS = [" за ", " - ", " — ", ": ", " = "]


def parse_income_message(text: str) -> Optional[Tuple[str, float]]:
    """
    Парсит текстовое сообщение и извлекает описание и сумму.

    Примеры:
        "логотип 15000" -> ("логотип", 15000.0)
        "сайт для Ивана 50000 руб" -> ("сайт для Ивана", 50000.0)
        "консультация за 5000" -> ("консультация", 5000.0)
        "дизайн 2.5к" -> ("дизайн", 2500.0)
        "баннер - 3000" -> ("баннер", 3000.0)
    """
    text = text.strip()

    # Ищем число в конце строки (самый распространённый формат)
    # Паттерн: описание [пробел/разделитель] число [опц. валюта/тысяч]
    pattern = r"^(.+?)\s+(\d[\d\s]*(?:[.,]\d+)?)\s*(?:тыс|тысяч|к|k|kk|руб|р|₽|rub|usd|\$|€|eur)?\.?\s*$"
    match = re.match(pattern, text, re.IGNORECASE)

    if match:
        description = match.group(1).strip()
        amount_str = match.group(2).replace(" ", "").replace(",", ".")

        # Удаляем разделители из конца описания
        for sep in [" за", " -", " —", ":", " ="]:
            if description.endswith(sep):
                description = description[: -len(sep)].strip()

        try:
            amount = float(amount_str)

            # Обработка сокращений "тыс", "к"
            lower_text = text.lower()
            suffix_match = re.search(
                r"\d\s*(тыс|тысяч|кк|к\b|kk|k\b)", lower_text, re.IGNORECASE
            )
            if suffix_match:
                suffix = suffix_match.group(1).lower()
                if suffix in ("тыс", "тысяч", "к", "k"):
                    amount *= 1000
                elif suffix in ("кк", "kk"):
                    amount *= 1000000

            if amount <= 0:
                return None

            logger.debug(f"Парсинг: '{text}' -> ('{description}', {amount})")
            return description, amount

        except ValueError:
            pass

    # Попытка найти число где-либо в строке
    numbers = re.findall(r"\d[\d\s]*(?:[.,]\d+)?", text)
    if numbers:
        amount_str = numbers[-1].replace(" ", "").replace(",", ".")
        try:
            amount = float(amount_str)
            # Описание — всё до найденного числа
            idx = text.rfind(numbers[-1])
            description = text[:idx].strip()

            # Очистка описания
            for sep in [" за", " -", " —", ":", " ="]:
                if description.endswith(sep):
                    description = description[: -len(sep)].strip()

            if description and amount > 0:
                return description, amount
        except ValueError:
            pass

    return None


def format_amount(amount: float) -> str:
    """Форматировать сумму для отображения"""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}М ₽"
    elif amount >= 1_000:
        return f"{amount:,.0f} ₽".replace(",", " ")
    else:
        return f"{amount:.0f} ₽"


def _extract_time(text: str):
    """Extract HH:MM from text. Returns (hour, minute) or (9, 0) as default."""
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
    return 9, 0


def parse_date(text: str, tz_offset_hours: int = 0) -> Optional[str]:
    """
    Parse a date+time from text. Supports multiple languages and formats.

    Date formats:
        DD.MM.YYYY, DD/MM/YYYY, DD.MM, YYYY-MM-DD
        tomorrow / завтра / demain / mañana
        in N days / через N дней / dans N jours / en N días

    Time (optional, appended to any date):
        14:30  →  uses that time; omit → defaults to 09:00

    Examples:
        "25.12 14:30"       → 25 Dec at 14:30
        "tomorrow 18:00"    → tomorrow at 18:00
        "через 3 дня 9:00"  → in 3 days at 09:00
        "25.12.2026"        → 25 Dec at 09:00
    """
    from datetime import datetime, timedelta

    text = text.strip().lower()
    # Work in user's local timezone, convert to UTC for storage
    utc_now = datetime.utcnow()
    local_now = utc_now + timedelta(hours=tz_offset_hours)
    hour, minute = _extract_time(text)

    def to_utc(local_dt: datetime) -> str:
        """Convert local datetime to UTC string for DB storage."""
        utc_dt = local_dt - timedelta(hours=tz_offset_hours)
        return utc_dt.strftime("%Y-%m-%d %H:%M")

    # "tomorrow" keywords (EN/RU/UK/FR/ES)
    tomorrow_words = ("tomorrow", "завтра", "demain", "mañana")
    if any(w in text for w in tomorrow_words):
        base = local_now + timedelta(days=1)
        return to_utc(base.replace(hour=hour, minute=minute, second=0, microsecond=0))

    # "in N days" / "через N дней" / "dans N jours" / "en N días"
    in_n_days_patterns = [
        r"in\s+(\d+)\s+days?",
        r"через\s+(\d+)\s+дн",
        r"через\s+(\d+)",
        r"dans\s+(\d+)\s+jours?",
        r"en\s+(\d+)\s+d[ií]as?",
    ]
    for pattern in in_n_days_patterns:
        m = re.search(pattern, text)
        if m:
            base = local_now + timedelta(days=int(m.group(1)))
            return to_utc(base.replace(hour=hour, minute=minute, second=0, microsecond=0))

    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), hour, minute)
            return to_utc(dt)
        except ValueError:
            pass

    # DD.MM.YYYY or DD/MM/YYYY
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), hour, minute)
            return to_utc(dt)
        except ValueError:
            pass

    # DD.MM or DD/MM (current year; roll to next year if already passed)
    m = re.search(r"(\d{1,2})[./](\d{1,2})", text)
    if m:
        try:
            day, month = int(m.group(1)), int(m.group(2))
            year = local_now.year
            dt = datetime(year, month, day, hour, minute)
            if dt < local_now:
                dt = datetime(year + 1, month, day, hour, minute)
            return to_utc(dt)
        except ValueError:
            pass

    # Time only (today at HH:MM, or tomorrow if already passed)
    m = re.search(r"^\s*(\d{1,2}):(\d{2})\s*$", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            dt = local_now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if dt < local_now:
                dt += timedelta(days=1)
            return to_utc(dt)

    return None
