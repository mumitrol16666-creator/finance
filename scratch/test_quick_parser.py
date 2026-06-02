from app.domain.services.quick_parser import parse_quick

tests = [
    ("купил кофе на 2000", "expense", 2000),
    ("пополнение баланса 5000", "income", 5000),
    ("получил зарплату 300000", "income", 300000),
    ("ушло на продукты 1500", "expense", 1500),
    ("списание за подписку 450", "expense", 450),
    ("пришли деньги 10000", "income", 10000),
]

for text, expected_kind, expected_amount in tests:
    res = parse_quick(text)
    if not res:
        print(f"FAIL: {text} -> None")
        continue
    # Amount is parsed into minor units. If KZT, it maps to 100x or is it 1:1?
    # Let's check how parse_money / parse_quick parses it.
    print(f"Parsed: '{text}' -> amount={res.amount}, kind={res.kind}, note='{res.note}'")
