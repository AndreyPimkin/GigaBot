import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from database import Database
from config import SESSION_TIMEOUT_SECONDS


class SessionManager:
    def __init__(self, database: Database):
        self.db = database
        self._active_sessions: Dict[str, dict] = {}

    def _generate_session_id(self, username: str) -> str:
        data = f"{username}:{datetime.now().isoformat()}:{uuid.uuid4().hex}"
        return hashlib.sha256(data.encode()).hexdigest()

    async def authenticate(self, username: str) -> Optional[str]:
        for session_data in self._active_sessions.values():
            if session_data["username"] == username and session_data["expires_at"] > datetime.now():
                return None
        user_id = await self.db.get_or_create_user(username)
        session_id = self._generate_session_id(username)
        await self.db.create_session(session_id, user_id)
        self._active_sessions[session_id] = {
            "username": username,
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(seconds=SESSION_TIMEOUT_SECONDS)
        }
        return session_id

    async def validate_session(self, session_id: str) -> Optional[str]:
        if session_id in self._active_sessions:
            if datetime.now() < self._active_sessions[session_id]["expires_at"]:
                self._active_sessions[session_id]["expires_at"] = datetime.now() + timedelta(
                    seconds=SESSION_TIMEOUT_SECONDS)
                return self._active_sessions[session_id]["username"]
            else:
                del self._active_sessions[session_id]

        username = await self.db.validate_session(session_id)
        if username:
            self._active_sessions[session_id] = {
                "username": username,
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(seconds=SESSION_TIMEOUT_SECONDS)
            }
            return username
        return None

    async def remove_session(self, session_id: str) -> None:
        self._active_sessions.pop(session_id, None)