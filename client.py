import asyncio
import json
import sys
from config import HOST, PORT


class ChatClient:
    def __init__(self, host: str = HOST, port: int = PORT):
        self.host, self.port = host, port
        self._reader = self._writer = None
        self._session_id = None

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        print(f"Подключено к {self.host}:{self.port}")

    async def authenticate(self, username: str) -> bool:
        auth_req = await self._read()
        if auth_req.get("type") != "auth_request":
            print(f"Ошибка: ожидается запрос авторизации")
            return False

        await self._send({"type": "login", "username": username})

        resp = await self._read()
        if resp.get("type") == "auth_success":
            self._session_id = resp.get("session_id")
            print(resp['message'])
            return True
        print(f"{resp.get('message', 'Ошибка входа')}")
        return False

    async def send_message(self, message: str):
        await self._send({"type": "message", "content": message})

    async def request_history(self):
        await self._send({"type": "history"})

    async def listen(self, callback):
        try:
            while True:
                resp = await self._read()
                await callback(resp)
        except asyncio.IncompleteReadError:
            print("Соединение разорвано")

    async def _read(self):
        length_bytes = await self._reader.readexactly(4)
        length = int.from_bytes(length_bytes, "big")
        return json.loads((await self._reader.readexactly(length)).decode())

    async def _send(self, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self._writer.write(len(raw).to_bytes(4, "big") + raw)
        await self._writer.drain()


async def handle_response(resp: dict):
    t = resp.get("type")
    if t == "message":
        print(f"\nБот: {resp['content']}\nВы: ", end="", flush=True)
    elif t == "typing":
        print(f"\nПечатает...\nВы: ", end="", flush=True)
    elif t == "history":
        msgs = resp.get("messages", [])
        print("История чата:")
        for m in msgs:
            print(f"  {m.get('username', '?')}: {m.get('user_message', '?')}")
            print(f"  Бот: {m.get('bot_response', '?')}")
        print("Вы: ", end="", flush=True)
    elif t == "error":
        print(f"\nОшибка: {resp['message']}\nВы: ", end="", flush=True)


async def input_loop(client: ChatClient):
    while True:
        msg = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        msg = msg.strip()
        if msg.lower() in ("/quit", "/exit"):
            break
        if msg == "/history":
            await client.request_history()
        elif msg:
            await client.send_message(msg)
        print("Вы: ", end="", flush=True)


async def main():
    client = ChatClient()
    await client.connect()
    username = input("Введите логин: ").strip()
    if not await client.authenticate(username):
        return
    print("\nВведите сообщение (/history, /quit):")
    print("Вы: ", end="", flush=True)
    listen_task = asyncio.create_task(client.listen(handle_response))
    await input_loop(client)
    listen_task.cancel()
    print("\nСессия завершена.")


if __name__ == "__main__":
    asyncio.run(main())