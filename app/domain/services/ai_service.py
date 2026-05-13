def simple_feedback(amount: int, category_name: str | None) -> str:
    # no real AI, but deterministic feedback hook
    if amount >= 100000:
        return "Крупная сумма. Проверь, что категория выбрана правильно."
    if category_name and category_name.lower() in ("еда","транспорт") and amount >= 20000:
        return "Заметная трата для этой категории."
    return ""
