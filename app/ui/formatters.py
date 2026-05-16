from app.domain.money import fmt_money as _fmt_money_domain


def block(*lines: str) -> str:
    return "\n".join([str(x) for x in lines if x is not None and str(x).strip() != ""])


def fmt_money(n: int, currency: str | None = None, *, with_sign: bool = False) -> str:
    """Format an integer minor-unit amount.

    Back-compat: legacy callers pass only ``n`` and expect digits-with-spaces
    (no currency symbol). New callers should pass ``currency`` to get a fully
    formatted string with the proper symbol.
    """
    if currency is None:
        try:
            n_int = int(n or 0)
        except Exception:
            return str(n)
        abs_part = f"{abs(n_int):,}".replace(",", " ")
        if n_int < 0:
            return f"-{abs_part}"
        if with_sign and n_int > 0:
            return f"+{abs_part}"
        return abs_part
    
    return _fmt_money_domain(n, currency, with_sign=with_sign)
def make_progress_bar(spent: int, limit: int, width: int = 10) -> str:
    """Generate a text-based progress bar.
    Example: [████░░░░░░] 40%
    """
    if limit <= 0:
        return "░" * width
    percent = min(max(spent / limit, 0), 1)
    filled = int(round(percent * width))
    empty = width - filled
    return "█" * filled + "░" * empty
