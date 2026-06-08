import re
from datetime import datetime

from app.domain.money import parse_money


DATE_OUT_FMT = "%Y-%m-%d"
_DATE_INPUT_FORMATS = ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d")


def parse_friendly_date(text: str | None) -> str | None:
    """Accept human dates in several common formats and return ISO ``YYYY-MM-DD``.

    Supported inputs: ``25.03.2026``, ``25-03-2026``, ``25/03/2026``,
    ``2026-03-25``, ``2026.03.25``, ``2026/03/25``. Returns ``None`` on
    anything we couldn't recognise — callers decide how to react.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    for fmt in _DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime(DATE_OUT_FMT)
        except Exception:
            pass
    return None


def parse_positive_int(text: str, max_value: int = 9_999_999) -> int | None:
    """Legacy entry point — delegates to ``parse_money``.

    Kept so existing handlers keep working unchanged; new handlers should call
    ``parse_money(text, currency=user_currency)`` directly so the selected
    currency rules are applied consistently.
    """
    return parse_money(text, currency="KZT", max_minor=max_value)

def parse_hhmm(text: str) -> str | None:
    t = text.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", t):
        return None
    hh, mm = int(t[:2]), int(t[3:])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return f"{hh:02d}:{mm:02d}"

def clean_name(text: str, min_len: int = 2, max_len: int = 24) -> str | None:
    t = " ".join(text.strip().split())
    if len(t) < min_len or len(t) > max_len:
        return None
    return t

def clean_note(text: str | None, max_len: int = 140) -> str | None:
    """Normalize note text. Returns None if empty. Truncates to max_len."""
    if text is None:
        return None
    t = " ".join(str(text).strip().split())
    if not t:
        return None
    if len(t) > max_len:
        t = t[:max_len]
    return t
