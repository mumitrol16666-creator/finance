import aiohttp
import time
from typing import Dict, Tuple

# In-memory cache structure: (from_currency, to_currency) -> (rate, timestamp)
_CACHE: Dict[Tuple[str, str], Tuple[float, float]] = {}
CACHE_TTL = 3600  # 1 hour in seconds

async def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Fetch the exchange rate from from_currency to to_currency.
    
    Uses an in-memory cache with a 1-hour expiration to prevent exceeding API limits.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    if from_currency == to_currency:
        return 1.0
        
    now = time.time()
    cache_key = (from_currency, to_currency)
    
    # Check cache validity
    if cache_key in _CACHE:
        rate, ts = _CACHE[cache_key]
        if now - ts < CACHE_TTL:
            return rate

    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch rates, status: {response.status}")
            data = await response.json()
            rates = data.get("rates", {})
            rate = rates.get(to_currency)
            if rate is None:
                raise Exception(f"Currency {to_currency} not found in rates")
                
            rate_val = float(rate)
            # Update cache for the pair
            _CACHE[cache_key] = (rate_val, now)
            # Update inverse cache to optimize subsequent reverse conversions
            if rate_val > 0:
                _CACHE[(to_currency, from_currency)] = (1.0 / rate_val, now)
                
            return rate_val
