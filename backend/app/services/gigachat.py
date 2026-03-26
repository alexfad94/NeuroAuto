from __future__ import annotations

import uuid
from typing import Optional

import httpx

from ..config import settings


class GigaChatClient:
    def __init__(self) -> None:
        self._access_token: Optional[str] = None

    async def _get_access_token(self) -> Optional[str]:
        if not settings.gigachat_auth_key:
            return None

        headers = {
            "Authorization": f"Basic {settings.gigachat_auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"scope": settings.gigachat_scope}

        async with httpx.AsyncClient(verify=settings.gigachat_verify_ssl, timeout=30) as client:
            response = await client.post(settings.gigachat_token_url, headers=headers, data=data)
            response.raise_for_status()
            payload = response.json()
            self._access_token = payload.get("access_token")
            return self._access_token

    async def ask(self, system_prompt: str, user_message: str) -> str:
        token = self._access_token or await self._get_access_token()
        if not token:
            return (
                "GigaChat ключ пока не настроен в .env. "
                "Я передал ваш запрос менеджеру, ответим в ближайшее время."
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.gigachat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": 700,
        }

        async with httpx.AsyncClient(verify=settings.gigachat_verify_ssl, timeout=60) as client:
            response = await client.post(settings.gigachat_chat_url, headers=headers, json=payload)
            if response.status_code == 401:
                # Refresh token once if it expired.
                token = await self._get_access_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    response = await client.post(settings.gigachat_chat_url, headers=headers, json=payload)

            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

