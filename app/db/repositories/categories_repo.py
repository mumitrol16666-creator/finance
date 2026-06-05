from __future__ import annotations
import aiosqlite

DEFAULT_EXPENSE = [
    ("Еда","🍔"),("Транспорт","🚕"),("Дом","🏠"),("Подписки","🧾"),("Развлечения","🎮"),
    ("Здоровье","🏥"),("Одежда","👕"),("Обучение","📚"),("Прочее","📦")
]
DEFAULT_INCOME = [
    ("Зарплата","💼"),("Бизнес","📈"),("Подарок","🎁"),("Возврат","💳"),("Прочее","📦")
]

async def count_categories(db: aiosqlite.Connection, user_id: int, kind: str) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM categories WHERE user_id=? AND kind=? AND is_archived=0", (user_id, kind))
    (cnt,) = await cur.fetchone()
    return int(cnt)

async def ensure_default_categories(db: aiosqlite.Connection, user_id: int, ts: str):
    # expense
    if await count_categories(db, user_id, "expense") == 0:
        await db.executemany(
            "INSERT OR IGNORE INTO categories(user_id,name,emoji,kind,is_archived,created_at,updated_at) VALUES(?,?,?,?,0,?,?)",
            [(user_id, n, e, "expense", ts, ts) for n,e in DEFAULT_EXPENSE]
        )
    # income
    if await count_categories(db, user_id, "income") == 0:
        await db.executemany(
            "INSERT OR IGNORE INTO categories(user_id,name,emoji,kind,is_archived,created_at,updated_at) VALUES(?,?,?,?,0,?,?)",
            [(user_id, n, e, "income", ts, ts) for n,e in DEFAULT_INCOME]
        )

async def list_categories(db: aiosqlite.Connection, user_id: int, kind: str):
    """Return categories ordered by recent usage (last 30 days) DESC, then id ASC.

    "Popular first" is a much friendlier default than creation order, especially
    once users have 15+ categories. The window is intentionally short (30 days)
    so the keyboard reflects *current* habits, not ancient history.
    """
    from datetime import datetime, timedelta, timezone
    window_start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cur = await db.execute(
        """
        SELECT id, name, emoji, default_account_id, exclude_from_analytics, warn_threshold
        FROM (
            SELECT c.id, c.name, c.emoji, c.default_account_id, c.exclude_from_analytics, c.warn_threshold,
                   COALESCE(SUM(CASE WHEN t.ts >= ? AND t.deleted_at IS NULL THEN 1 ELSE 0 END), 0) AS uses
            FROM categories c
            LEFT JOIN transactions t
              ON t.category_id = c.id
             AND t.user_id = c.user_id
             AND t.type = c.kind
            WHERE c.user_id=? AND c.kind=? AND c.is_archived=0
            GROUP BY c.id, c.name, c.emoji, c.default_account_id, c.exclude_from_analytics, c.warn_threshold
        )
        ORDER BY uses DESC, id ASC
        """,
        (window_start, user_id, kind),
    )
    return await cur.fetchall()


async def get_category(db: aiosqlite.Connection, user_id: int, category_id: int):
    cur = await db.execute(
        "SELECT id, name, emoji, kind, is_archived FROM categories WHERE user_id=? AND id=?",
        (user_id, category_id),
    )
    return await cur.fetchone()

REVERSE_CATEGORY_LOOKUP = {
    # ── Еда ──
    "food": "еда", "тамақ": "еда",
    "продукты": "еда", "супермаркет": "еда", "магазин": "еда",
    "ресторан": "еда", "кафе": "еда", "доставка": "еда",
    "обед": "еда", "ужин": "еда", "завтрак": "еда",
    "донер": "еда", "пицца": "еда", "кофе": "еда",
    "фастфуд": "еда", "столовая": "еда", "перекус": "еда",
    "grocery": "еда", "restaurant": "еда", "lunch": "еда",
    "dinner": "еда", "breakfast": "еда", "cafe": "еда",
    "snack": "еда", "delivery": "еда", "coffee": "еда",
    # ── Транспорт ──
    "transport": "транспорт", "көлік": "транспорт",
    "такси": "транспорт", "автобус": "транспорт", "метро": "транспорт",
    "бензин": "транспорт", "заправка": "транспорт", "самокат": "транспорт",
    "поезд": "транспорт", "дорога": "транспорт", "парковка": "транспорт",
    "uber": "транспорт", "яндекс такси": "транспорт", "bolt": "транспорт",
    "taxi": "транспорт", "bus": "транспорт", "gas": "транспорт",
    "fuel": "транспорт", "parking": "транспорт",
    # ── Дом ──
    "home": "дом", "үй": "дом",
    "аренда": "дом", "квартира": "дом", "ремонт": "дом",
    "коммуналка": "дом", "кпу": "дом", "электричество": "дом",
    "свет": "дом", "вода": "дом", "газ": "дом",
    "мебель": "дом", "уборка": "дом", "ипотека": "дом",
    "rent": "дом", "utilities": "дом", "furniture": "дом",
    "mortgage": "дом", "cleaning": "дом",
    # ── Подписки ──
    "subscriptions": "подписки", "жазылымдар": "подписки",
    "подписка": "подписки", "netflix": "подписки", "youtube": "подписки",
    "spotify": "подписки", "icloud": "подписки", "apple": "подписки",
    "интернет": "подписки", "связь": "подписки", "телефон": "подписки",
    "мобильный": "подписки", "subscription": "подписки",
    # ── Развлечения ──
    "entertainment": "развлечения", "ойын-сауық": "развлечения",
    "кино": "развлечения", "игры": "развлечения", "бар": "развлечения",
    "клуб": "развлечения", "тусовка": "развлечения", "концерт": "развлечения",
    "театр": "развлечения", "караоке": "развлечения", "боулинг": "развлечения",
    "кальян": "развлечения", "пиво": "развлечения", "алкоголь": "развлечения",
    "cinema": "развлечения", "games": "развлечения", "party": "развлечения",
    # ── Здоровье ──
    "health": "здоровье", "денсаулық": "здоровье",
    "аптека": "здоровье", "лекарства": "здоровье", "врач": "здоровье",
    "больница": "здоровье", "клиника": "здоровье", "стоматолог": "здоровье",
    "анализы": "здоровье", "спортзал": "здоровье", "фитнес": "здоровье",
    "витамины": "здоровье", "зубной": "здоровье",
    "pharmacy": "здоровье", "doctor": "здоровье", "gym": "здоровье",
    "fitness": "здоровье", "medicine": "здоровье", "hospital": "здоровье",
    # ── Одежда ──
    "clothing": "одежда", "киім": "одежда",
    "обувь": "одежда", "шмотки": "одежда", "кроссовки": "одежда",
    "куртка": "одежда", "джинсы": "одежда", "футболка": "одежда",
    "платье": "одежда", "костюм": "одежда", "аксессуары": "одежда",
    "shoes": "одежда", "clothes": "одежда", "fashion": "одежда",
    # ── Обучение ──
    "education": "обучение", "оқу": "обучение",
    "курсы": "обучение", "книги": "обучение", "книга": "обучение",
    "репетитор": "обучение", "школа": "обучение", "университет": "обучение",
    "учёба": "обучение", "тренинг": "обучение", "вебинар": "обучение",
    "courses": "обучение", "books": "обучение", "tutor": "обучение",
    "school": "обучение", "university": "обучение",
    # ── Прочее ──
    "other": "прочее", "басқа": "прочее",
    # ── Зарплата ──
    "salary": "зарплата", "жалақы": "зарплата",
    "зп": "зарплата", "оклад": "зарплата", "аванс": "зарплата",
    "получка": "зарплата", "wage": "зарплата", "paycheck": "зарплата",
    # ── Бизнес ──
    "business": "бизнес",
    "фриланс": "бизнес", "freelance": "бизнес", "проект": "бизнес",
    "заказ": "бизнес", "клиент": "бизнес", "контракт": "бизнес",
    # ── Подарок ──
    "gift": "подарок", "сыйлық": "подарок",
    "подарки": "подарок", "сюрприз": "подарок", "презент": "подарок",
    # ── Возврат ──
    "refunds": "возврат", "қайтару": "возврат",
    "возвраты": "возврат", "кэшбэк": "возврат", "cashback": "возврат",
    "refund": "возврат", "компенсация": "возврат",
}

async def find_category_by_name_ci(
    db: aiosqlite.Connection,
    user_id: int,
    kind: str,
    name: str,
):
    """
    Exact category match by name, case-insensitive.
    Returns (id, name, emoji) or None.
    """
    n = (name or "").strip().lower()
    if not n:
        return None

    # Reverse lookup for localized names
    n = REVERSE_CATEGORY_LOOKUP.get(n, n)

    cur = await db.execute(
        """
        SELECT id, name, emoji
        FROM categories
        WHERE user_id=?
          AND kind=?
          AND is_archived=0
          AND lower(name)=?
        LIMIT 1
        """,
        (user_id, kind, n),
    )
    return await cur.fetchone()

async def name_exists_any_kind(db: aiosqlite.Connection, user_id: int, name: str) -> bool:
    n = (name or "").strip().lower()
    cur = await db.execute(
        "SELECT 1 FROM categories WHERE user_id=? AND lower(name)=? LIMIT 1",
        (user_id, n),
    )
    return (await cur.fetchone()) is not None

async def create_category(db: aiosqlite.Connection, user_id: int, name: str, emoji: str | None, kind: str, ts: str):
    cur = await db.execute(
        "INSERT INTO categories(user_id,name,emoji,kind,is_archived,created_at,updated_at) VALUES(?,?,?,?,0,?,?)",
        (user_id, name.strip(), (emoji or None), kind, ts, ts),
    )
    return int(cur.lastrowid)

async def rename_category(db: aiosqlite.Connection, user_id: int, category_id: int, new_name: str, ts: str):
    await db.execute(
        "UPDATE categories SET name=?, updated_at=? WHERE user_id=? AND id=?",
        (new_name.strip(), ts, user_id, category_id),
    )

async def set_category_emoji(db: aiosqlite.Connection, user_id: int, category_id: int, emoji: str | None, ts: str):
    await db.execute(
        "UPDATE categories SET emoji=?, updated_at=? WHERE user_id=? AND id=?",
        ((emoji or None), ts, user_id, category_id),
    )

async def archive_category(db: aiosqlite.Connection, user_id: int, category_id: int, ts: str):
    await db.execute(
        "UPDATE categories SET is_archived=1, updated_at=? WHERE user_id=? AND id=?",
        (ts, user_id, category_id),
    )

async def find_category_by_note_hint(db: aiosqlite.Connection, user_id: int, kind: str, note: str):
    """
    Very conservative: tries to match category name as substring in note (case-insensitive).
    Returns (id, name, emoji) or None.
    """
    if not note:
        return None
    low = note.lower()

    from app.db.repositories.settings_repo import get_lang
    try:
        lang = await get_lang(db, user_id)
    except Exception:
        lang = "ru"

    from app.ui.i18n import t_category
    cats = await list_categories(db, user_id, kind)
    for cid, name, emoji in cats:
        name_lower = name.lower() if name else ""
        translated_name = t_category(name, lang).lower() if name else ""
        if name_lower and (name_lower in low or translated_name in low):
            return cid, name, emoji
    return None

async def get_category_budget(
    db: aiosqlite.Connection,
    user_id: int,
    category_id: int,
    month: str,
):
    cur = await db.execute(
        """
        SELECT limit_amount
        FROM budgets
        WHERE user_id=? AND category_id=? AND month=?
        LIMIT 1
        """,
        (user_id, category_id, month),
    )
    row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None

async def get_category_spent_month(
    db: aiosqlite.Connection,
    user_id: int,
    category_id: int,
    month: str,
):
    cur = await db.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id=?
          AND category_id=?
          AND type='expense'
          AND deleted_at IS NULL
          AND strftime('%Y-%m', created_at)=?
        """,
        (user_id, category_id, month),
    )
    row = await cur.fetchone()
    return int(row[0]) if row and row[0] else 0