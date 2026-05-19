from __future__ import annotations
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os

load_dotenv()

class Settings(BaseModel):
    bot_token: str = Field(default_factory=lambda: os.getenv("BOT_TOKEN",""))
    timezone: str = Field(default_factory=lambda: os.getenv("TIMEZONE","Asia/Aqtobe"))
    db_path: str = Field(default_factory=lambda: os.getenv("DB_PATH","./data/bot.db"))
    admin_ids: list[int] = Field(default_factory=lambda: [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()])
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG","1").strip() in ("1","true","True","YES","yes"))
    full_access_stars_price: int = Field(default_factory=lambda: int(os.getenv("FULL_ACCESS_STARS_PRICE", "150")))
    full_access_days: int = Field(default_factory=lambda: int(os.getenv("FULL_ACCESS_DAYS", "90")))
    main_channel_id: int = Field(default_factory=lambda: int(os.getenv("MAIN_CHANNEL_ID", "0")))

settings = Settings()

if not settings.bot_token:
    raise RuntimeError("BOT_TOKEN is empty. Put it in .env")
