def block(*lines: str) -> str:
    return "\n".join([str(x) for x in lines if x is not None and str(x).strip() != ""])


def fmt_money(n: int) -> str:
    """
    Форматирует число: 15000 -> 15 000
    """
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)
