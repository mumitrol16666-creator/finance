from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def _apply_sql_migration(db: aiosqlite.Connection, file: Path) -> None:
    sql = file.read_text(encoding="utf-8")
    await db.executescript(sql)


async def _apply_py_migration(db: aiosqlite.Connection, file: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"app.db.migrations.{file.stem}", file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load migration module: {file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    apply = getattr(module, "apply", None)
    if apply is None:
        raise RuntimeError(f"Python migration {file.name} must expose async apply(db)")

    await apply(db)


async def run_migrations(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    cur = await db.execute("SELECT id FROM migrations")
    applied = {row[0] for row in await cur.fetchall()}

    files = sorted([
        file for file in MIGRATIONS_DIR.iterdir()
        if file.is_file() and file.suffix in {".sql", ".py"}
    ])

    for file in files:
        migration_id = file.name

        if migration_id in applied:
            continue

        if file.suffix == ".sql":
            await _apply_sql_migration(db, file)
        elif file.suffix == ".py":
            await _apply_py_migration(db, file)
        else:
            continue

        await db.execute(
            "INSERT INTO migrations (id, applied_at) VALUES (?, ?)",
            (migration_id, datetime.now(timezone.utc).isoformat())
        )

        print(f"[MIGRATION] applied {migration_id}")

    await db.commit()
