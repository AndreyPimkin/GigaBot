import asyncio
import time
import requests
import logging
import urllib3
from typing import Optional
from config import GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL, API_TIMEOUT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, credentials: str = GIGACHAT_CREDENTIALS):
        self.credentials = credentials
        self._semaphore = asyncio.Semaphore(1)
        self._token_cache = {"token": None, "expires": 0}

    async def _get_access_token(self) -> str:
        if self._token_cache["token"] and time.time() < self._token_cache["expires"]:
            return self._token_cache["token"]

        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {self.credentials}",
            "RqUID": "00000000-0000-0000-0000-000000000000"
        }
        data = {"scope": GIGACHAT_SCOPE}

        resp = requests.post(url, headers=headers, data=data, verify=False, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()

        self._token_cache["token"] = token_data["access_token"]
        self._token_cache["expires"] = time.time() + (token_data.get("expires_at", 1800) or 1800)
        return self._token_cache["token"]

    async def generate_response(self, user_message: str, history: Optional[list] = None) -> str:
        async with self._semaphore:
            for attempt in range(3):
                try:
                    token = await self._get_access_token()
                    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                    payload = {"model": GIGACHAT_MODEL, "messages": [], "stream": False}
                    if history:
                        for m in history[-10:]:
                            payload["messages"].append({"role": "user", "content": m["user_message"]})
                            payload["messages"].append({"role": "assistant", "content": m["bot_response"]})
                    payload["messages"].append({"role": "user", "content": user_message})

                    loop = asyncio.get_event_loop()

                    def _call_api():
                        r = requests.post(url, headers=headers, json=payload, verify=False, timeout=API_TIMEOUT)
                        r.raise_for_status()
                        return r.json()["choices"][0]["message"]["content"]

                    return (await loop.run_in_executor(None, _call_api)).strip()

                except Exception as e:
                    err_str = str(e).lower()
                    if attempt < 2 and any(x in err_str for x in ["429", "503", "timeout", "busy"]):
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise LLMError(f"Ошибка LLM: {e}")