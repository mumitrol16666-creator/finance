"""Money parsing and formatting — single source of truth.

Amounts are stored in the ledger as whole currency units. This matches the
mobile app's integer amount model and keeps bot/app balances identical.

The parser accepts the formats real users type:
- "500", "1000"
- "1 000", "1\u00a0000"  (thin / non-breaking spaces)
- "1000.50", "1000,50"   (decimal . or ,)
- "1,000.50", "1 000,50" (thousands + decimal)
- "+1200", "-2500"       (sign — accepted; caller decides expense vs income)

It rejects:
- Empty / whitespace-only strings
- Anything with non-digit/non-separator characters (rejects unicode digits to
  prevent surprises like \u0660\u0661\u0662 silently parsing as 012)
- Zero or negative results
- Values exceeding ``max_value`` (default ~10^9 minor units)
"""
from __future__ import annotations

import re
from typing import Any, Optional

import aiosqlite

CURRENCY_SCALE: dict[str, int] = {
    "KZT": 1,
    "RUB": 1,
    "UZS": 1,
    "KGS": 1,
    "USD": 1,
    "EUR": 1,
    "GBP": 1,
}

CURRENCY_SYMBOL: dict[str, str] = {
    "KZT": "₸",
    "RUB": "₽",
    "UZS": "сум",
    "KGS": "сом",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

DEFAULT_CURRENCY = "KZT"

# Order matters here: ``-`` must be last in the char class to avoid being read as a range.
_ALLOWED_CHARS = re.compile(r"^[0-9\s\u00a0\u202f.,+\-]+$")


def get_scale(currency: str | None) -> int:
    """Return how many minor units make one major unit of ``currency``."""
    return CURRENCY_SCALE.get((currency or DEFAULT_CURRENCY).upper(), 1)


def get_symbol(currency: str | None) -> str:
    code = (currency or DEFAULT_CURRENCY).upper()
    return CURRENCY_SYMBOL.get(code, code)


def parse_money(
    text: str | None,
    currency: str | None = DEFAULT_CURRENCY,
    *,
    max_minor: int = 1_000_000_000,
) -> Optional[int]:
    """Parse user-typed amount into INTEGER minor units.

    Returns ``None`` when the input is invalid. ``None`` is the caller's signal to
    show a friendly "type the amount as digits, e.g. 500" error.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    if not _ALLOWED_CHARS.match(raw):
        return None

    # Strip all spaces (incl. NBSP, thin NBSP) used as thousand separators.
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")

    sign = 1
    if cleaned.startswith(("+", "-")):
        if cleaned[0] == "-":
            sign = -1
        cleaned = cleaned[1:]

    if not cleaned:
        return None

    # Disambiguate "." vs "," as decimal separator. Strategy:
    # - if both appear → the LAST one is the decimal separator, the other is the
    #   thousands separator: "1,000.50" → 1000.50; "1.000,50" → 1000.50
    # - if only one appears AND there are exactly 3 digits after it → thousands
    #   separator: "1,000" → 1000; "1.000" → 1000
    # - otherwise → decimal separator: "1000,50" → 1000.50
    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")

    if last_dot >= 0 and last_comma >= 0:
        if last_dot > last_comma:
            decimal_sep, thousand_sep = ".", ","
        else:
            decimal_sep, thousand_sep = ",", "."
    elif last_dot >= 0:
        after = cleaned[last_dot + 1:]
        if len(after) == 3 and after.isdigit() and cleaned[:last_dot].replace(".", "").isdigit():
            decimal_sep, thousand_sep = None, "."
        else:
            decimal_sep, thousand_sep = ".", None
    elif last_comma >= 0:
        after = cleaned[last_comma + 1:]
        if len(after) == 3 and after.isdigit() and cleaned[:last_comma].replace(",", "").isdigit():
            decimal_sep, thousand_sep = None, ","
        else:
            decimal_sep, thousand_sep = ",", None
    else:
        decimal_sep, thousand_sep = None, None

    if thousand_sep is not None:
        cleaned = cleaned.replace(thousand_sep, "")
    if decimal_sep is not None:
        cleaned = cleaned.replace(decimal_sep, ".")

    if cleaned in ("", "."):
        return None

    try:
        major = float(cleaned)
    except ValueError:
        return None

    scale = get_scale(currency)
    minor = int(round(major * scale)) * sign

    if minor <= 0:
        return None
    if minor > max_minor:
        return None
    return minor


def fmt_money(amount: int | None, currency: str | None = DEFAULT_CURRENCY, *, with_sign: bool = False) -> str:
    """Format integer minor units as a human-readable string with currency symbol.

    Uses a regular space as the thousands separator (locale-neutral, looks
    consistent in Telegram on every platform).
    """
    try:
        n = int(amount or 0)
    except Exception:
        return str(amount)

    scale = get_scale(currency)
    abs_n = abs(n)
    if scale == 1:
        major_part = f"{abs_n:,}".replace(",", " ")
    else:
        major, minor = divmod(abs_n, scale)
        minor_digits = len(str(scale)) - 1
        major_part = f"{major:,}".replace(",", " ") + f".{minor:0{minor_digits}d}"

    sign_part = ""
    if n < 0:
        sign_part = "-"
    elif with_sign and n > 0:
        sign_part = "+"

    symbol = get_symbol(currency)
    return f"{sign_part}{major_part} {symbol}"


def fmt_money_compact(amount: int | None, currency: str | None = DEFAULT_CURRENCY) -> str:
    """Compact form for inline buttons / balances where space is precious."""
    return fmt_money(amount, currency)


def fmt_exchange_rate(from_currency: str, to_currency: str, rate: float) -> str:
    """Format a direct rate in the readable direction, avoiding tiny decimals."""
    from_code = (from_currency or DEFAULT_CURRENCY).upper()
    to_code = (to_currency or DEFAULT_CURRENCY).upper()
    if rate <= 0:
        return "—"
    if rate < 1:
        from_code, to_code, rate = to_code, from_code, 1 / rate
    rate_text = f"{rate:.2f}".rstrip("0").rstrip(".")
    return f"1 {from_code} = {rate_text} {to_code}"


async def get_user_currency(db: aiosqlite.Connection, user_id: int) -> str:
    """Return ISO currency code (KZT default) from settings.

    Used by handlers so amount input is parsed with the right minor-unit scale.
    """
    try:
        cur = await db.execute("SELECT currency FROM settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    except Exception:
        return DEFAULT_CURRENCY
    if not row:
        return DEFAULT_CURRENCY
    return str(row[0] or DEFAULT_CURRENCY).upper()


async def parse_money_for_user(
    db: aiosqlite.Connection,
    user_id: int,
    text: str | None,
    *,
    max_minor: int = 1_000_000_000,
) -> Optional[int]:
    """Parse text using the user's currency scale.

    Thin convenience wrapper so handlers don't have to fetch settings + import
    ``parse_money`` separately on every amount step.
    """
    currency = await get_user_currency(db, user_id)
    return parse_money(text, currency=currency, max_minor=max_minor)
