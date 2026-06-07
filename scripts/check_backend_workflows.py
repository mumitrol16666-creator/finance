import asyncio
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

logger.remove()

from app.api.api_server import (
    DebtPayRequest,
    SettingsUpdateRequest,
    execute_planned_endpoint,
    get_debt_payments_endpoint,
    get_user_settings,
    pay_debt_endpoint,
    update_settings,
)
from app.config.settings import settings
from app.db.connection import open_db
from app.db.migrate import run_migrations
from app.db.repositories.settings_repo import list_notify_targets
from app.domain.auth import hash_password
from app.scheduler.notify_scheduler import _is_in_quiet_hours


async def check() -> None:
    fd, path_str = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    path = Path(path_str)
    settings.db_path = str(path)
    now = "2026-06-07T00:00:00+00:00"

    db = await open_db(str(path))
    try:
        with redirect_stdout(io.StringIO()):
            await run_migrations(db)
        await db.execute(
            "INSERT INTO users(id,telegram_id,username,password_hash,display_name,onboarding_state,"
            "created_at,onboarded,mode,full_access) VALUES(1,1,'testuser',?,'Test','completed',?,1,'full',1)",
            (hash_password("password"), now),
        )
        await db.execute(
            "INSERT INTO settings(user_id,currency,timezone,lang,created_at,updated_at) "
            "VALUES(1,'KZT','Asia/Qyzylorda','ru',?,?)",
            (now, now),
        )
        account = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(1,'Main',100000,100000,'KZT',0,?,?)",
            (now, now),
        )
        category = await db.execute(
            "INSERT INTO categories(user_id,name,emoji,kind,is_archived,created_at,updated_at) "
            "VALUES(1,'Test','T','expense',0,?,?)",
            (now, now),
        )
        debt = await db.execute(
            "INSERT INTO debts(user_id,direction,dtype,title,total_amount,remaining_amount,payment_amount,"
            "next_payment_date,status,is_active,created_at,updated_at) "
            "VALUES(1,'out','private','Debt',5000,5000,1000,'2026-06-10','active',1,?,?)",
            (now, now),
        )
        planned = await db.execute(
            "INSERT INTO planned_transactions(user_id,kind,title,amount,category_id,account_id,planned_date,"
            "comment,is_required,is_archived,created_at,updated_at) "
            "VALUES(1,'expense','Planned',700,?,?,'2026-06-07',NULL,1,0,?,?)",
            (category.lastrowid, account.lastrowid, now, now),
        )
        await db.commit()
        account_id = int(account.lastrowid)
        debt_id = int(debt.lastrowid)
        planned_id = int(planned.lastrowid)
    finally:
        await db.close()

    await update_settings(
        SettingsUpdateRequest(
            quiet_hours_start="23:00",
            quiet_hours_end="07:30",
            telegram_notifications_enabled=True,
        ),
        1,
    )
    assert (await get_user_settings(1))["quiet_hours_start"] == "23:00"
    assert _is_in_quiet_hours(__import__("datetime").datetime(2026, 6, 7, 23, 30), 1, "23:00", "07:30")

    await pay_debt_endpoint(debt_id, DebtPayRequest(payment_amount=1000, account_id=account_id), 1)
    history = await get_debt_payments_endpoint(debt_id, 1)
    assert len(history) == 1 and history[0]["amount"] == 1000 and history[0]["transactionId"] is not None

    await execute_planned_endpoint(planned_id, 1)
    db = await open_db(str(path))
    try:
        planned_row = await (await db.execute(
            "SELECT is_archived FROM planned_transactions WHERE id=?",
            (planned_id,),
        )).fetchone()
        transaction_count = await (await db.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id=1"
        )).fetchone()
        targets = await list_notify_targets(db)
        assert planned_row[0] == 1
        assert transaction_count[0] == 2
        assert [row[0] for row in targets] == [1]
    finally:
        await db.close()

    await asyncio.sleep(0.5)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(check())
    print("Backend workflow checks OK")
