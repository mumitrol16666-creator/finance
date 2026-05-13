from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

INCOME_HINTS = {"зп","зарплата","пришло","приход","доход","прибыль","поступило","поступление"}
EXPENSE_HINTS = {"купил","купила","потратил","потратила","расход","трата","оплатил","оплатила","заплатил","заплатила"}

_amount_re = re.compile(r'([+-]?)\s*(\d[\d\s]{0,14}\d|\d)')

@dataclass
class QuickParsed:
    raw: str
    amount: int              # positive number
    kind: Optional[str]      # "income" | "expense" | None
    note: str                # cleaned remaining text

def parse_quick(text: str, max_value: int = 99_999_999) -> Optional[QuickParsed]:
    """
    Strict parser:
    - exactly one numeric amount (allows spaces: 12 000)
    - optional leading sign +/-
    - kind inferred only from sign or keywords; otherwise None
    """
    raw = (text or "").strip()
    if not raw:
        return None

    matches = list(_amount_re.finditer(raw))
    if not matches:
        return None
    # only one amount allowed
    if len(matches) != 1:
        return None

    m = matches[0]
    sign = m.group(1) or ""
    num = (m.group(2) or "").replace(" ", "")
    if not num.isdigit():
        return None
    value = int(num)
    if value < 0 or value > max_value:
        return None

    # remove the matched amount portion from note
    note = (raw[:m.start()] + raw[m.end():]).strip()
    # normalize spaces
    note = re.sub(r"\s{2,}", " ", note)

    low = raw.lower()
    kind: Optional[str] = None

    if sign == "+":
        kind = "income"
    elif sign == "-":
        kind = "expense"
    else:
        # keyword inference (lightweight)
        if any(h in low for h in INCOME_HINTS):
            kind = "income"
        elif any(h in low for h in EXPENSE_HINTS):
            kind = "expense"

    return QuickParsed(raw=raw, amount=value, kind=kind, note=note)
