from bot.i18n.translations import TRANSLATIONS, CURRENCY_SYMBOLS, CURRENCY_NAMES


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """Get translated string by key and language"""
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["ru"])
    text = lang_dict.get(key, TRANSLATIONS["ru"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def format_amount(amount: float, currency: str = "USD") -> str:
    """Format amount with proper currency symbol"""
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    position = "before" if currency in ("USD", "GBP", "EUR") else "after"

    if amount >= 1_000_000:
        formatted = f"{amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        formatted = f"{amount:,.0f}".replace(",", " ")
    else:
        formatted = f"{amount:.0f}"

    if position == "before":
        return f"{symbol}{formatted}"
    else:
        return f"{formatted} {symbol}"
