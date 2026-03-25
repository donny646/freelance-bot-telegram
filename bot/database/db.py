import asyncpg
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        _pool = await asyncpg.create_pool(database_url)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                is_active INTEGER DEFAULT 1,
                subscription_until TEXT,
                trial_started TEXT,
                language TEXT DEFAULT 'ru',
                currency TEXT DEFAULT 'USD',
                timezone TEXT DEFAULT 'UTC',
                created_at TEXT DEFAULT ''
            )
        """)

        for col, definition in [
            ("language", "TEXT DEFAULT 'ru'"),
            ("currency", "TEXT DEFAULT 'USD'"),
            ("timezone", "TEXT DEFAULT 'UTC'"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                contact TEXT,
                notes TEXT,
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                client_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'in_progress',
                deadline TEXT,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS incomes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                project_id INTEGER,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                project_id INTEGER,
                text TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                is_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                plan TEXT NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'XTR',
                telegram_payment_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crypto_invoices (
                invoice_id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                plan TEXT NOT NULL,
                asset TEXT NOT NULL,
                pay_address TEXT,
                pay_amount TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        for col, definition in [
            ("pay_address", "TEXT"),
            ("pay_amount", "TEXT"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE crypto_invoices ADD COLUMN {col} {definition}")
            except Exception:
                pass

    logger.info("База данных инициализирована")


async def get_user(user_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def create_or_update_user(user_id: int, username: str, full_name: str):
    existing = await get_user(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not existing:
            trial_started = datetime.now().isoformat()
            await conn.execute(
                """INSERT INTO users (user_id, username, full_name, trial_started, created_at)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, username, full_name, trial_started, datetime.now().isoformat(),
            )
            logger.info(f"Новый пользователь: {user_id} ({full_name})")
        else:
            await conn.execute(
                "UPDATE users SET username=$1, full_name=$2 WHERE user_id=$3",
                username, full_name, user_id,
            )


async def get_user_settings(user_id: int) -> dict:
    user = await get_user(user_id)
    if not user:
        return {"language": "ru", "currency": "USD", "timezone": "UTC"}
    return {
        "language": user.get("language") or "ru",
        "currency": user.get("currency") or "USD",
        "timezone": user.get("timezone") or "UTC",
    }


async def set_user_language(user_id: int, language: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language=$1 WHERE user_id=$2", language, user_id)


async def set_user_currency(user_id: int, currency: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET currency=$1 WHERE user_id=$2", currency, user_id)


async def set_user_timezone(user_id: int, timezone: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET timezone=$1 WHERE user_id=$2", timezone, user_id)


async def check_subscription(user_id: int) -> bool:
    user = await get_user(user_id)
    if not user:
        return False
    now = datetime.now()
    if user["subscription_until"]:
        if datetime.fromisoformat(user["subscription_until"]) > now:
            return True
    if user["trial_started"]:
        if datetime.fromisoformat(user["trial_started"]) + timedelta(days=7) > now:
            return True
    return False


async def get_subscription_status(user_id: int) -> dict:
    user = await get_user(user_id)
    if not user:
        return {"active": False, "type": "none", "days_left": 0}
    now = datetime.now()
    if user["subscription_until"]:
        sub_until = datetime.fromisoformat(user["subscription_until"])
        if sub_until > now:
            return {"active": True, "type": "subscription", "days_left": (sub_until - now).days, "until": user["subscription_until"]}
    if user["trial_started"]:
        trial_end = datetime.fromisoformat(user["trial_started"]) + timedelta(days=7)
        if trial_end > now:
            return {"active": True, "type": "trial", "days_left": (trial_end - now).days}
    return {"active": False, "type": "expired", "days_left": 0}


async def set_subscription(user_id: int, months: int, payment_id: str = None):
    user = await get_user(user_id)
    now = datetime.now()
    if user and user["subscription_until"]:
        current_end = datetime.fromisoformat(user["subscription_until"])
        new_end = (current_end if current_end > now else now) + timedelta(days=30 * months)
    else:
        new_end = now + timedelta(days=30 * months)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET subscription_until=$1 WHERE user_id=$2",
            new_end.isoformat(), user_id,
        )
        if payment_id:
            await conn.execute(
                """UPDATE payments SET status='completed', telegram_payment_id=$1
                   WHERE user_id=$2 AND status='pending'""",
                payment_id, user_id,
            )
    logger.info(f"Подписка установлена для {user_id} до {new_end}")


async def create_payment_record(user_id: int, plan: str, amount: int, currency: str = "XTR"):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO payments (user_id, plan, amount, currency, created_at) VALUES ($1, $2, $3, $4, $5)",
            user_id, plan, amount, currency, datetime.now().isoformat(),
        )


# ===== ДОХОДЫ =====

async def add_income(user_id: int, description: str, amount: float, project_id: int = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO incomes (user_id, project_id, description, amount, created_at) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            user_id, project_id, description, amount, datetime.now().isoformat(),
        )
        return row["id"]


async def get_incomes(user_id: int, limit: int = 10) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incomes WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )
        return [dict(r) for r in rows]


async def get_monthly_incomes(user_id: int, year: int, month: int) -> list:
    prefix = f"{year}-{month:02d}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incomes WHERE user_id=$1 AND LEFT(created_at, 7)=$2 ORDER BY created_at DESC",
            user_id, prefix,
        )
        return [dict(r) for r in rows]


# ===== КЛИЕНТЫ =====

async def add_client(user_id: int, name: str, contact: str = None, notes: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO clients (user_id, name, contact, notes, created_at) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            user_id, name, contact, notes, datetime.now().isoformat(),
        )
        return row["id"]


async def get_clients(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM clients WHERE user_id=$1 ORDER BY name", user_id)
        return [dict(r) for r in rows]


async def get_client(client_id: int, user_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM clients WHERE id=$1 AND user_id=$2", client_id, user_id
        )
        return dict(row) if row else None


# ===== ПРОЕКТЫ =====

async def add_project(user_id: int, title: str, client_id: int = None,
                      description: str = None, deadline: str = None, amount: float = 0) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO projects (user_id, client_id, title, description, deadline, amount, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            user_id, client_id, title, description, deadline, amount, datetime.now().isoformat(),
        )
        return row["id"]


async def get_projects(user_id: int, status: str = None) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """SELECT p.*, c.name as client_name FROM projects p
                   LEFT JOIN clients c ON p.client_id = c.id
                   WHERE p.user_id=$1 AND p.status=$2 ORDER BY p.created_at DESC""",
                user_id, status,
            )
        else:
            rows = await conn.fetch(
                """SELECT p.*, c.name as client_name FROM projects p
                   LEFT JOIN clients c ON p.client_id = c.id
                   WHERE p.user_id=$1 ORDER BY p.created_at DESC""",
                user_id,
            )
        return [dict(r) for r in rows]


async def get_project(project_id: int, user_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT p.*, c.name as client_name FROM projects p
               LEFT JOIN clients c ON p.client_id = c.id
               WHERE p.id=$1 AND p.user_id=$2""",
            project_id, user_id,
        )
        return dict(row) if row else None


async def update_project_status(project_id: int, user_id: int, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET status=$1 WHERE id=$2 AND user_id=$3",
            status, project_id, user_id,
        )


# ===== НАПОМИНАНИЯ =====

async def add_reminder(user_id: int, text: str, remind_at: str, project_id: int = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO reminders (user_id, project_id, text, remind_at, created_at) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            user_id, project_id, text, remind_at, datetime.now().isoformat(),
        )
        return row["id"]


async def get_pending_reminders() -> list:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= $1", now
        )
        return [dict(r) for r in rows]


async def mark_reminder_sent(reminder_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE reminders SET is_sent=1 WHERE id=$1", reminder_id)


async def get_user_reminders(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM reminders WHERE user_id=$1 AND is_sent=0 ORDER BY remind_at",
            user_id,
        )
        return [dict(r) for r in rows]


# ===== АНАЛИТИКА =====

async def get_analytics(user_id: int) -> dict:
    now = datetime.now()
    prefix = f"{now.year}-{now.month:02d}"
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount), 0) as total FROM incomes WHERE user_id=$1 AND LEFT(created_at, 7)=$2",
            user_id, prefix,
        )
        monthly_income = row["total"]

        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM incomes WHERE user_id=$1 AND LEFT(created_at, 7)=$2",
            user_id, prefix,
        )
        monthly_count = row["cnt"]

        avg_check = monthly_income / monthly_count if monthly_count > 0 else 0

        rows = await conn.fetch(
            "SELECT status, COUNT(*) as cnt FROM projects WHERE user_id=$1 GROUP BY status",
            user_id,
        )
        project_stats = {r["status"]: r["cnt"] for r in rows}

        row = await conn.fetchrow(
            "SELECT COALESCE(SUM(amount), 0) as total FROM incomes WHERE user_id=$1", user_id
        )
        total_income = row["total"]

        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM clients WHERE user_id=$1", user_id
        )
        client_count = row["cnt"]

    return {
        "monthly_income": monthly_income,
        "monthly_count": monthly_count,
        "avg_check": avg_check,
        "project_stats": project_stats,
        "total_income": total_income,
        "client_count": client_count,
        "month": now.strftime("%B %Y"),
    }


async def save_crypto_invoice(
    invoice_id: int, user_id: int, plan: str, asset: str,
    pay_address: str = "", pay_amount: str = "",
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO crypto_invoices (invoice_id, user_id, plan, asset, pay_address, pay_amount, status, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
               ON CONFLICT (invoice_id) DO UPDATE SET
                   pay_address=EXCLUDED.pay_address,
                   pay_amount=EXCLUDED.pay_amount,
                   status='active'""",
            invoice_id, user_id, plan, asset, pay_address, pay_amount, datetime.now().isoformat(),
        )


async def get_crypto_invoice(invoice_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM crypto_invoices WHERE invoice_id=$1", invoice_id
        )
        return dict(row) if row else None


async def mark_crypto_invoice_paid(invoice_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE crypto_invoices SET status='paid' WHERE invoice_id=$1", invoice_id
        )


# ===== ADMIN =====

async def admin_get_stats() -> dict:
    now = datetime.now().isoformat()
    trial_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
        total_users = row["cnt"]

        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM users WHERE subscription_until > $1", now
        )
        active_subs = row["cnt"]

        row = await conn.fetchrow(
            """SELECT COUNT(*) as cnt FROM users
               WHERE (subscription_until IS NULL OR subscription_until <= $1)
               AND trial_started >= $2""",
            now, trial_cutoff,
        )
        on_trial = row["cnt"]

        expired = total_users - active_subs - on_trial

        row = await conn.fetchrow("SELECT COALESCE(SUM(amount), 0) as total FROM incomes")
        total_income = row["total"]

        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM projects")
        total_projects = row["cnt"]

        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM clients")
        total_clients = row["cnt"]

    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "on_trial": on_trial,
        "expired": max(0, expired),
        "total_income": total_income,
        "total_projects": total_projects,
        "total_clients": total_clients,
    }


async def admin_get_recent_users(limit: int = 15) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, username, full_name, subscription_until, trial_started FROM users ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]


async def admin_grant_subscription(user_id: int, months: int):
    await set_subscription(user_id, months)


async def admin_get_all_user_ids() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_active = 1")
        return [r["user_id"] for r in rows]
