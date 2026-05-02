import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict
from config import DB_PATH


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._connection = await aiosqlite.connect(self.db_path)
        await self._init_tables()

    async def _init_tables(self) -> None:
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                username TEXT NOT NULL,
                user_message TEXT NOT NULL,
                bot_response TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
        """)
        await self._connection.commit()

    async def get_or_create_user(self, username: str) -> int:
        cursor = await self._connection.execute("SELECT id FROM users WHERE username = ?", (username,))
        result = await cursor.fetchone()
        if result:
            return result[0]
        cursor = await self._connection.execute("INSERT INTO users (username) VALUES (?)", (username,))
        await self._connection.commit()
        return cursor.lastrowid

    async def create_session(self, session_id: str, user_id: int) -> None:
        await self._connection.execute("INSERT INTO sessions (session_id, user_id) VALUES (?, ?)", (session_id, user_id))
        await self._connection.commit()

    async def validate_session(self, session_id: str) -> Optional[str]:
        cursor = await self._connection.execute("""
            SELECT u.username
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_id = ?
        """, (session_id,))
        result = await cursor.fetchone()
        if result:
            await self._connection.execute("UPDATE sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?", (session_id,))
            await self._connection.commit()
            return result[0]
        return None

    async def save_message(self, session_id: str, username: str, user_message: str, bot_response: str) -> None:
        await self._connection.execute("""
            INSERT INTO messages (session_id, username, user_message, bot_response, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, username, user_message, bot_response, datetime.now()))
        await self._connection.commit()

    async def get_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        cursor = await self._connection.execute("""
            SELECT user_message, bot_response, timestamp
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC LIMIT ?
        """, (session_id, limit))
        rows = await cursor.fetchall()
        return [{"user_message": r[0], "bot_response": r[1], "timestamp": r[2]} for r in rows]

    async def get_all_history(self, limit: int = 100) -> list:
        cursor = await self._connection.execute("""
            SELECT username, user_message, bot_response
            FROM messages
            ORDER BY id ASC LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [{"username": r[0], "user_message": r[1], "bot_response": r[2]} for r in rows]

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()