import re

def parse_positive_int(text: str, max_value: int = 9_999_999) -> int | None:
    t = text.strip().replace(" ", "")
    if not t.isdigit():
        return None
    v = int(t)
    if v <= 0 or v > max_value:
        return None
    return v

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
