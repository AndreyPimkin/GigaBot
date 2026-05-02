import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("SERVER_HOST", "127.0.0.1")
PORT = int(os.getenv("SERVER_PORT", 8888))
BUFFER_SIZE = 1024
DB_PATH = os.getenv("DB_PATH", "chat_history.db")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", 30))
SESSION_TIMEOUT_SECONDS = 3600