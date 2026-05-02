import asyncio
import json
import logging
from typing import Optional, Dict

from auth import SessionManager
from database import Database
from llm_client import LLMClient, LLMError
from config import HOST, PORT, BUFFER_SIZE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ChatServer:
    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.db = Database()
        self.session_manager: Optional[SessionManager] = None
        self.llm_client: Optional[LLMClient] = None
        self._server: Optional[asyncio.Server] = None

    async def initialize(self) -> None:
        await self.db.connect()
        self.session_manager = SessionManager(self.db)
        self.llm_client = LLMClient()
        logger.info(f"Server initialized on {self.host}:{self.port}")

    async def _handle_auth(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Optional[str]:
        await self._send_json(writer, {"type": "auth_request", "message": "Введите ваш логин:"})

        data = await self._read_json(reader)
        if not data or "username" not in data:
            await self._send_json(writer, {"type": "error", "message": "Неверный формат логина"})
            return None

        username = data["username"].strip()
        if not username:
            await self._send_json(writer, {"type": "error", "message": "Логин не может быть пустым"})
            return None

        session_id = await self.session_manager.authenticate(username)
        if not session_id:
            await self._send_json(writer, {"type": "error", "message": "Пользователь с таким логином уже подключён"})
            return None

        await self._send_json(writer, {
            "type": "auth_success",
            "message": f"Добро пожаловать, {username}!",
            "session_id": session_id
        })
        logger.info(f"User '{username}' authenticated")
        return session_id

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client_addr = writer.get_extra_info('peername')
        session_id = None
        logger.info(f"New connection from {client_addr}")

        try:
            session_id = await self._handle_auth(reader, writer)
            if not session_id:
                return

            while True:
                data = await self._read_json(reader)
                if not data:
                    break

                msg_type = data.get("type")
                if msg_type == "message":
                    await self._handle_message(reader, writer, session_id, data)
                elif msg_type == "history":
                    await self._handle_history_request(reader, writer, session_id)
                elif msg_type == "disconnect":
                    break
                else:
                    await self._send_json(writer, {"type": "error", "message": f"Неизвестный тип сообщения: {msg_type}"})

        except (ConnectionResetError, asyncio.IncompleteReadError):
            logger.info(f"Client {client_addr} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}", exc_info=True)
        finally:
            if session_id:
                await self.session_manager.remove_session(session_id)

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Connection closed for {client_addr}")

    async def _handle_message(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str,
                              data: Dict) -> None:
        user_message = data.get("content", "").strip()
        if not user_message:
            await self._send_json(writer, {"type": "error", "message": "Пустое сообщение"})
            return

        username = await self.session_manager.validate_session(session_id)
        if not username:
            await self._send_json(writer, {"type": "error", "message": "Сессия истекла"})
            return

        await self._send_json(writer, {"type": "typing", "message": "Думаю..."})

        try:
            history = await self.db.get_history(session_id, limit=10)
            bot_response = await self.llm_client.generate_response(user_message, history)
            await self.db.save_message(session_id, username, user_message, bot_response)
            await self._send_json(writer, {"type": "message", "content": bot_response})
        except LLMError as e:
            logger.error(f"LLM error: {e}")
            await self._send_json(writer, {"type": "error", "message": str(e)})
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            await self._send_json(writer, {"type": "error", "message": "Внутренняя ошибка сервера"})

    async def _handle_history_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str) -> None:
        username = await self.session_manager.validate_session(session_id)
        if not username:
            await self._send_json(writer, {"type": "error", "message": "Сессия не валидна"})
            return

        history = await self.db.get_all_history()
        await self._send_json(writer, {"type": "history", "messages": history})

    async def _read_json(self, reader: asyncio.StreamReader) -> Optional[Dict]:
        try:
            length_bytes = await reader.readexactly(4)
            length = int.from_bytes(length_bytes, byteorder='big')
            data_bytes = await reader.readexactly(length)
            return json.loads(data_bytes.decode('utf-8'))
        except (asyncio.IncompleteReadError, json.JSONDecodeError):
            return None

    async def _send_json(self, writer: asyncio.StreamWriter, data: Dict) -> None:
        json_data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        length = len(json_data).to_bytes(4, byteorder='big')
        writer.write(length + json_data)
        await writer.drain()

    async def start(self) -> None:
        await self.initialize()
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info(f"Server started on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()

    async def shutdown(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self.db:
            await self.db.close()
        logger.info("Server shutdown complete")


async def main():
    server = ChatServer()
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())