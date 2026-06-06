import aiosqlite
import httpx
from datetime import datetime, timezone
from loguru import logger

# Static fallbacks if API is offline
DEFAULT_RATES_TO_USD = {
    "USD": 1.0,
    "KZT": 450.0,
    "RUB": 90.0,
    "EUR": 0.92,
}

async def fetch_and_update_rates(db: aiosqlite.Connection) -> None:
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("rates", {})
                now_str = datetime.now(timezone.utc).isoformat()
                for curr, rate in rates.items():
                    # We store rate relative to USD: 1 USD = rate units
                    await db.execute(
                        "INSERT INTO exchange_rates(currency, rate_to_usd, updated_at) "
                        "VALUES(?, ?, ?) ON CONFLICT(currency) DO UPDATE SET rate_to_usd=excluded.rate_to_usd, updated_at=excluded.updated_at",
                        (curr, float(rate), now_str)
                    )
                await db.commit()
                logger.info("Successfully updated currency exchange rates from API")
                return
    except Exception as e:
        logger.error(f"Failed to fetch exchange rates: {e}. Using local fallback updates.")

    # Fallback updates
    now_str = datetime.now(timezone.utc).isoformat()
    for curr, rate in DEFAULT_RATES_TO_USD.items():
        await db.execute(
            "INSERT INTO exchange_rates(currency, rate_to_usd, updated_at) "
            "VALUES(?, ?, ?) ON CONFLICT(currency) DO UPDATE SET rate_to_usd=excluded.rate_to_usd, updated_at=excluded.updated_at",
            (curr, rate, now_str)
        )
    await db.commit()

async def get_exchange_rate(db: aiosqlite.Connection, from_curr: str, to_curr: str) -> float:
    """Returns the conversion multiplier: from_curr -> to_curr."""
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    if from_curr == to_curr:
        return 1.0

    # Ensure rates exist in DB
    cur = await db.execute("SELECT COUNT(*) FROM exchange_rates")
    (cnt,) = await cur.fetchone()
    if cnt == 0:
        await fetch_and_update_rates(db)

    # Get rate from_curr to USD
    cur = await db.execute("SELECT rate_to_usd FROM exchange_rates WHERE currency=?", (from_curr,))
    row_from = await cur.fetchone()
    rate_from = row_from[0] if row_from else DEFAULT_RATES_TO_USD.get(from_curr)

    # Get rate to_curr to USD
    cur = await db.execute("SELECT rate_to_usd FROM exchange_rates WHERE currency=?", (to_curr,))
    row_to = await cur.fetchone()
    rate_to = row_to[0] if row_to else DEFAULT_RATES_TO_USD.get(to_curr)

    if not rate_from or not rate_to:
        logger.warning(f"Rates not found for {from_curr} or {to_curr}. Using 1.0.")
        return 1.0

    # from_curr -> USD -> to_curr
    # rate_to_usd represents units per 1 USD (e.g. 1 USD = 450 KZT, so KZT rate_to_usd = 450)
    # USD amount = from_amount / rate_from
    # to_amount = USD_amount * rate_to
    return float(rate_to / rate_from)
