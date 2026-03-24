import aiosqlite
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "bot/freelancer_bot.db"


async def init_db():
    """Инициализация базы данных и создание всех таблиц"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                is_active INTEGER DEFAULT 1,
                subscription_until TEXT,
                trial_started TEXT,
                language TEXT DEFAULT 'ru',
                currency TEXT DEFAULT 'USD',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Migrate existing tables — add new columns if missing
        for col, definition in [
            ("language", "TEXT DEFAULT 'ru'"),
            ("currency", "TEXT DEFAULT 'USD'"),
            ("timezone", "TEXT DEFAULT 'UTC'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass  # Column already exists

        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                contact TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                client_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'in_progress',
                deadline TEXT,
                amount REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS incomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER,
                text TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                is_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'XTR',
                telegram_payment_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS crypto_invoices (
                invoice_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                asset TEXT NOT NULL,
                pay_address TEXT,
                pay_amount TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        for col, definition in [
            ("pay_address", "TEXT"),
            ("pay_amount",  "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE crypto_invoices ADD COLUMN {col} {definition}")
            except Exception:
                pass

        await db.commit()
    logger.info("База данных инициализирована")


async def get_user(user_id: int) -> Optional[dict]:
    """Получить пользователя по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_or_update_user(user_id: int, username: str, full_name: str):
    """Создать или обновить пользователя, начать trial если новый"""
    existing = await get_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if not existing:
            trial_started = datetime.now().isoformat()
            await db.execute(
                """INSERT INTO users (user_id, username, full_name, trial_started)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, full_name, trial_started),
            )
            logger.info(f"Новый пользователь: {user_id} ({full_name})")
        else:
            await db.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username, full_name, user_id),
            )
        await db.commit()


async def get_user_settings(user_id: int) -> dict:
    """Get user language, currency and timezone settings"""
    user = await get_user(user_id)
    if not user:
        return {"language": "ru", "currency": "USD", "timezone": "UTC"}
    return {
        "language": user.get("language") or "ru",
        "currency": user.get("currency") or "USD",
        "timezone": user.get("timezone") or "UTC",
    }


async def set_user_language(user_id: int, language: str):
    """Set user interface language"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET language=? WHERE user_id=?", (language, user_id)
        )
        await db.commit()


async def set_user_currency(user_id: int, currency: str):
    """Set user currency preference"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET currency=? WHERE user_id=?", (currency, user_id)
        )
        await db.commit()


async def set_user_timezone(user_id: int, timezone: str):
    """Set user timezone preference"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET timezone=? WHERE user_id=?", (timezone, user_id)
        )
        await db.commit()


async def check_subscription(user_id: int) -> bool:
    """Проверить, есть ли у пользователя активная подписка или trial"""
    user = await get_user(user_id)
    if not user:
        return False

    now = datetime.now()

    if user["subscription_until"]:
        sub_until = datetime.fromisoformat(user["subscription_until"])
        if sub_until > now:
            return True

    if user["trial_started"]:
        trial_start = datetime.fromisoformat(user["trial_started"])
        trial_end = trial_start + timedelta(days=7)
        if trial_end > now:
            return True

    return False


async def get_subscription_status(user_id: int) -> dict:
    """Получить детальный статус подписки"""
    user = await get_user(user_id)
    if not user:
        return {"active": False, "type": "none", "days_left": 0}

    now = datetime.now()

    if user["subscription_until"]:
        sub_until = datetime.fromisoformat(user["subscription_until"])
        if sub_until > now:
            days_left = (sub_until - now).days
            return {"active": True, "type": "subscription", "days_left": days_left, "until": user["subscription_until"]}

    if user["trial_started"]:
        trial_start = datetime.fromisoformat(user["trial_started"])
        trial_end = trial_start + timedelta(days=7)
        if trial_end > now:
            days_left = (trial_end - now).days
            return {"active": True, "type": "trial", "days_left": days_left}

    return {"active": False, "type": "expired", "days_left": 0}


async def set_subscription(user_id: int, months: int, payment_id: str = None):
    """Установить подписку пользователю"""
    user = await get_user(user_id)
    now = datetime.now()

    if user and user["subscription_until"]:
        current_end = datetime.fromisoformat(user["subscription_until"])
        if current_end > now:
            new_end = current_end + timedelta(days=30 * months)
        else:
            new_end = now + timedelta(days=30 * months)
    else:
        new_end = now + timedelta(days=30 * months)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET subscription_until=? WHERE user_id=?",
            (new_end.isoformat(), user_id),
        )
        if payment_id:
            await db.execute(
                "UPDATE payments SET status='completed', telegram_payment_id=? WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
                (payment_id, user_id),
            )
        await db.commit()
    logger.info(f"Подписка установлена для {user_id} до {new_end}")


async def create_payment_record(user_id: int, plan: str, amount: int, currency: str = "XTR"):
    """Создать запись об оплате"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, plan, amount, currency) VALUES (?, ?, ?, ?)",
            (user_id, plan, amount, currency),
        )
        await db.commit()


# ===== ДОХОДЫ =====

async def add_income(user_id: int, description: str, amount: float, project_id: int = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO incomes (user_id, project_id, description, amount) VALUES (?, ?, ?, ?)",
            (user_id, project_id, description, amount),
        )
        await db.commit()
        return cursor.lastrowid


async def get_incomes(user_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM incomes WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_monthly_incomes(user_id: int, year: int, month: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM incomes WHERE user_id=?
               AND strftime('%Y', created_at)=? AND strftime('%m', created_at)=?
               ORDER BY created_at DESC""",
            (user_id, str(year), f"{month:02d}"),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ===== КЛИЕНТЫ =====

async def add_client(user_id: int, name: str, contact: str = None, notes: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO clients (user_id, name, contact, notes) VALUES (?, ?, ?, ?)",
            (user_id, name, contact, notes),
        )
        await db.commit()
        return cursor.lastrowid


async def get_clients(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM clients WHERE user_id=? ORDER BY name",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_client(client_id: int, user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM clients WHERE id=? AND user_id=?", (client_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ===== ПРОЕКТЫ =====

async def add_project(user_id: int, title: str, client_id: int = None,
                      description: str = None, deadline: str = None, amount: float = 0) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO projects (user_id, client_id, title, description, deadline, amount)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, client_id, title, description, deadline, amount),
        )
        await db.commit()
        return cursor.lastrowid


async def get_projects(user_id: int, status: str = None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                """SELECT p.*, c.name as client_name FROM projects p
                   LEFT JOIN clients c ON p.client_id = c.id
                   WHERE p.user_id=? AND p.status=? ORDER BY p.created_at DESC""",
                (user_id, status),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT p.*, c.name as client_name FROM projects p
                   LEFT JOIN clients c ON p.client_id = c.id
                   WHERE p.user_id=? ORDER BY p.created_at DESC""",
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_project(project_id: int, user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT p.*, c.name as client_name FROM projects p
               LEFT JOIN clients c ON p.client_id = c.id
               WHERE p.id=? AND p.user_id=?""",
            (project_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_project_status(project_id: int, user_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET status=? WHERE id=? AND user_id=?",
            (status, project_id, user_id),
        )
        await db.commit()


# ===== НАПОМИНАНИЯ =====

async def add_reminder(user_id: int, text: str, remind_at: str, project_id: int = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO reminders (user_id, project_id, text, remind_at) VALUES (?, ?, ?, ?)",
            (user_id, project_id, text, remind_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_reminders() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        async with db.execute(
            "SELECT * FROM reminders WHERE is_sent=0 AND remind_at <= ?", (now,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def mark_reminder_sent(reminder_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reminders SET is_sent=1 WHERE id=?", (reminder_id,)
        )
        await db.commit()


async def get_user_reminders(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE user_id=? AND is_sent=0 ORDER BY remind_at",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ===== АНАЛИТИКА =====

async def get_analytics(user_id: int) -> dict:
    now = datetime.now()
    year = str(now.year)
    month = f"{now.month:02d}"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT COALESCE(SUM(amount), 0) as total FROM incomes
               WHERE user_id=? AND strftime('%Y', created_at)=? AND strftime('%m', created_at)=?""",
            (user_id, year, month),
        ) as cursor:
            row = await cursor.fetchone()
            monthly_income = row["total"]

        async with db.execute(
            """SELECT COUNT(*) as cnt FROM incomes
               WHERE user_id=? AND strftime('%Y', created_at)=? AND strftime('%m', created_at)=?""",
            (user_id, year, month),
        ) as cursor:
            row = await cursor.fetchone()
            monthly_count = row["cnt"]

        avg_check = monthly_income / monthly_count if monthly_count > 0 else 0

        async with db.execute(
            "SELECT status, COUNT(*) as cnt FROM projects WHERE user_id=? GROUP BY status",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            project_stats = {r["status"]: r["cnt"] for r in rows}

        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM incomes WHERE user_id=?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            total_income = row["total"]

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM clients WHERE user_id=?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO crypto_invoices
               (invoice_id, user_id, plan, asset, pay_address, pay_amount, status)
               VALUES (?, ?, ?, ?, ?, ?, 'active')""",
            (invoice_id, user_id, plan, asset, pay_address, pay_amount),
        )
        await db.commit()


async def get_crypto_invoice(invoice_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM crypto_invoices WHERE invoice_id=?", (invoice_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def mark_crypto_invoice_paid(invoice_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE crypto_invoices SET status='paid' WHERE invoice_id=?", (invoice_id,)
        )
        await db.commit()
