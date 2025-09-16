import aiosqlite
import datetime


class Database:
    def __init__(self, db_path="trackers.db"):
        self.db_path = db_path

    async def connect(self):
        self.db = await aiosqlite.connect(self.db_path)
        # чтобы возвращать словари, а не кортежи
        self.db.row_factory = aiosqlite.Row

    async def close(self):
        await self.db.close()

    async def init_db(self):
        await self.connect()
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                created_at TEXT
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS flight_trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                origin TEXT,
                destination TEXT,
                date TEXT,
                price_limit INTEGER,
                active INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        try:
            async with self.db.execute("PRAGMA table_info('flight_trackers')") as cursor:
                cols = [row[1] async for row in cursor]
            if "last_sent_price" not in cols:
                await self.db.execute("ALTER TABLE flight_trackers ADD COLUMN last_sent_price INTEGER")
        except Exception:
            pass
        await self.db.commit()

    async def add_user(self, telegram_id: int, username: str = None):
        async with self.db.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
        if user:
            return user["id"]
        created_at = datetime.datetime.utcnow().isoformat()
        cursor = await self.db.execute(
            "INSERT INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, created_at)
        )
        await self.db.commit()
        return cursor.lastrowid

    async def add_flight_tracker(self, user_id: int, origin: str, destination: str, date: str, price_limit: int) -> int:
        cursor = await self.db.execute("""
            INSERT INTO flight_trackers (user_id, origin, destination, date, price_limit, active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (user_id, origin, destination, date, price_limit))
        await self.db.commit()
        return cursor.lastrowid

    async def get_active_trackers(self):
        trackers = []
        async with self.db.execute("""
            SELECT ft.id, u.telegram_id, ft.origin, ft.destination, ft.date, ft.price_limit
            FROM flight_trackers ft
            JOIN users u ON ft.user_id = u.id
            WHERE ft.active = 1
        """) as cursor:
            async for row in cursor:
                trackers.append({
                    "tracker_id": row["id"],
                    "telegram_id": row["telegram_id"],
                    "origin": row["origin"],
                    "destination": row["destination"],
                    "date": row["date"],
                    "price_limit": row["price_limit"]
                })
        return trackers

    async def get_user_trackers(self, user_id: int):
        trackers = []
        async with self.db.execute("""
            SELECT id, origin, destination, date, price_limit
            FROM flight_trackers
            WHERE user_id = ? AND active = 1
        """, (user_id,)) as cursor:
            async for row in cursor:
                trackers.append({
                    "tracker_id": row["id"],
                    "origin": row["origin"],
                    "destination": row["destination"],
                    "date": [row["date"]],
                    "price_limit": row["price_limit"]
                })
        return trackers

    async def count_active_trackers(self, user_id: int) -> int:
        async with self.db.execute(
                "SELECT COUNT(*) FROM flight_trackers WHERE user_id = ? AND active = 1",
                (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def tracker_exists(self, user_id: int, origin: str, destination: str, date: str) -> bool:
        async with self.db.execute(
                "SELECT 1 FROM flight_trackers WHERE user_id = ? AND origin = ? AND destination = ? AND date = ? AND active = 1",
                (user_id, origin, destination, date)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def deactivate_tracker(self, tracker_id: int):
        await self.db.execute("UPDATE flight_trackers SET active = 0 WHERE id = ?", (tracker_id,))
        await self.db.commit()

    async def deactivate_all_user_trackers(self, user_id: int):
        await self.db.execute("UPDATE flight_trackers SET active = 0 WHERE user_id = ?", (user_id,))
        await self.db.commit()

    async def get_last_sent_price(self, tracker_id: int):
        async with self.db.execute(
            "SELECT last_sent_price FROM flight_trackers WHERE id = ?",
            (tracker_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return row[0]

    async def update_last_sent_price(self, tracker_id: int, price: int):
        await self.db.execute(
            "UPDATE flight_trackers SET last_sent_price = ? WHERE id = ?",
            (int(price), tracker_id)
        )
        await self.db.commit()


db = Database()
