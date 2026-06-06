from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import aiosqlite

from app.db.repositories.users_repo import (
    get_access_profile,
    set_progress_level,
)

UserMode = Literal["newbie", "full"]
MenuVariant = Literal["newbie", "full"]

FEATURE_EXPENSE = "expense"
FEATURE_INCOME = "income"
FEATURE_TRANSFER = "transfer"
FEATURE_HISTORY = "history"
FEATURE_SETTINGS = "settings"
FEATURE_ACCOUNTS = "accounts"
FEATURE_REPORTS = "reports"
FEATURE_PLANNED = "planned"
FEATURE_RECURRING = "recurring"
FEATURE_DEBTS = "debts"
FEATURE_AI = "ai"
FEATURE_UPGRADE = "upgrade"
FEATURE_BUDGETS = "budgets"

NEWBIE_LEVEL0_FEATURES = {
    FEATURE_EXPENSE,
    FEATURE_INCOME,
    FEATURE_HISTORY,
    FEATURE_SETTINGS,
    FEATURE_ACCOUNTS,
    FEATURE_UPGRADE,
    FEATURE_REPORTS,
    FEATURE_BUDGETS,
    FEATURE_AI,
}

NEWBIE_LEVEL2_EXTRA_FEATURES = {
    FEATURE_REPORTS,
    FEATURE_BUDGETS,
    FEATURE_ACCOUNTS,
}

FULL_FEATURES = {
    FEATURE_EXPENSE,
    FEATURE_INCOME,
    FEATURE_TRANSFER,
    FEATURE_HISTORY,
    FEATURE_SETTINGS,
    FEATURE_ACCOUNTS,
    FEATURE_REPORTS,
    FEATURE_PLANNED,
    FEATURE_RECURRING,
    FEATURE_DEBTS,
    FEATURE_AI,
    FEATURE_BUDGETS,
}


@dataclass(slots=True)
class UserAccessContext:
    user_id: int
    onboarding_completed: bool
    mode: UserMode
    progress_level: int
    full_access: bool
    current_streak: int
    max_streak: int
    last_activity_date: str | None
    expiration_date: str | None = None


async def get_user_context(db: aiosqlite.Connection, user_id: int) -> UserAccessContext:
    row = await get_access_profile(db, user_id)

    if row is None:
        return UserAccessContext(
            user_id=user_id,
            onboarding_completed=False,
            mode="newbie",
            progress_level=0,
            full_access=False,
            current_streak=0,
            max_streak=0,
            last_activity_date=None,
        )

    onboarded = int(row["onboarded"] or 0) == 1
    stored_mode = str(row["mode"] or "newbie").lower()
    stored_progress = int(row["progress_level"] or 0)
    full_access = int(row["full_access"] or 0) == 1
    full_access_until = str(row["full_access_until"]) if row["full_access_until"] else None
    current_streak = int(row["current_streak"] or 0)
    max_streak = int(row["max_streak"] or 0)
    last_activity_date = str(row["last_activity_date"]) if row["last_activity_date"] else None

    # Check if full access has expired
    if full_access and full_access_until:
        from datetime import date as _date
        try:
            until_date = _date.fromisoformat(full_access_until)
            if _date.today() > until_date:
                # Access expired — downgrade
                full_access = False
                stored_mode = "newbie"
                await db.execute(
                    "UPDATE users SET full_access=0, mode='newbie' WHERE id=?",
                    (user_id,),
                )
                await db.commit()
        except (ValueError, TypeError):
            pass

    auto_progress = 2 if max(current_streak, max_streak) >= 3 else 0
    effective_progress = max(stored_progress, auto_progress)

    if effective_progress != stored_progress:
        await set_progress_level(db, user_id, effective_progress)

    mode: UserMode = "full" if full_access or stored_mode == "full" else "newbie"

    return UserAccessContext(
        user_id=user_id,
        onboarding_completed=onboarded,
        mode=mode,
        progress_level=effective_progress,
        full_access=full_access,
        current_streak=current_streak,
        max_streak=max_streak,
        last_activity_date=last_activity_date,
        expiration_date=full_access_until,
    )


async def can_use_feature(db: aiosqlite.Connection, user_id: int, feature: str) -> bool:
    ctx = await get_user_context(db, user_id)
    return feature in get_available_features_from_context(ctx)


async def get_menu_variant(db: aiosqlite.Connection, user_id: int) -> MenuVariant:
    ctx = await get_user_context(db, user_id)
    return "full" if ctx.mode == "full" else "newbie"


async def get_available_features(db: aiosqlite.Connection, user_id: int) -> set[str]:
    ctx = await get_user_context(db, user_id)
    return get_available_features_from_context(ctx)


async def should_offer_upgrade(db: aiosqlite.Connection, user_id: int) -> bool:
    ctx = await get_user_context(db, user_id)
    return ctx.mode != "full"


async def get_menu_context(db: aiosqlite.Connection, user_id: int) -> tuple[MenuVariant, int, bool, str | None]:
    ctx = await get_user_context(db, user_id)
    return ("full" if ctx.mode == "full" else "newbie", ctx.progress_level, ctx.full_access, ctx.expiration_date)



def get_available_features_from_context(ctx: UserAccessContext) -> set[str]:
    if ctx.mode == "full":
        return set(FULL_FEATURES)

    features = set(NEWBIE_LEVEL0_FEATURES)
    if ctx.progress_level >= 2:
        features.update(NEWBIE_LEVEL2_EXTRA_FEATURES)
    return features
