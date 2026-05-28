from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from app.domain.money import parse_money

# Multilingual hints; bot supports ru/en/kk.
INCOME_HINTS = {
    "зп", "зарплата", "пришло", "приход", "доход", "прибыль", "поступило", "поступление",
    "пополнение", "получил", "получила", "пришли", "начислили", "начисление", "заработал", "заработала", "зачислили", "зачисление",
    "salary", "income", "got", "received", "earned", "wage", "bonus",
    "жалақы", "табыс", "кіріс",
}
EXPENSE_HINTS = {
    "купил", "купила", "потратил", "потратила", "расход", "трата",
    "оплатил", "оплатила", "заплатил", "заплатила",
    "списание", "потрачено", "ушло", "отдал", "отдала", "купить", "потратить", "оплата", "платеж", "выплатил", "выплатила", "заплатить", "заказал", "заказала",
    "spent", "paid", "bought", "expense", "cost",
    "төледім", "сатып", "шығыс", "жұмсадым",
}

# Matches one numeric value with optional sign and ` ` / NBSP thousands separators
# and an optional decimal part separated by `.` or `,`.
_amount_re = re.compile(
    r"(?P<sign>[+\-])?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?"
    r"|\d+(?:[.,]\d{1,4})?)"
)


@dataclass
class QuickParsed:
    raw: str
    amount: int              # minor units, always positive
    kind: Optional[str]      # "income" | "expense" | None
    note: str                # cleaned remaining text


def parse_quick(text: str, currency: str = "KZT", max_minor: int = 1_000_000_000) -> Optional[QuickParsed]:
    """Parse a free-form quick-add message.

    Strategy:
    - Find all amount-like tokens. If exactly one — that's the amount.
    - If multiple, take the LARGEST (typical user case: "Такси 500, чаевые 50"
      should record 500 with note "Такси чаевые 50"). This keeps the bot from
      silently giving up.
    - Sign / keyword hints determine income vs expense.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    matches = list(_amount_re.finditer(raw))
    if not matches:
        return None

    parsed_candidates: list[tuple[re.Match[str], int, str]] = []
    for m in matches:
        sign = m.group("sign") or ""
        num = m.group("num")
        token = f"{sign}{num}"
        value = parse_money(token, currency=currency, max_minor=max_minor)
        if value is None:
            continue
        parsed_candidates.append((m, value, sign))

    if not parsed_candidates:
        return None

    # Pick the largest amount; keep its match for note slicing.
    best_match, best_value, best_sign = max(parsed_candidates, key=lambda c: c[1])

    note = (raw[:best_match.start()] + raw[best_match.end():]).strip()
    note = re.sub(r"\s{2,}", " ", note)

    low = raw.lower()
    kind: Optional[str] = None

    if best_sign == "+":
        kind = "income"
    elif best_sign == "-":
        kind = "expense"
    else:
        if any(h in low for h in INCOME_HINTS):
            kind = "income"
        elif any(h in low for h in EXPENSE_HINTS):
            kind = "expense"

    return QuickParsed(raw=raw, amount=best_value, kind=kind, note=note)
