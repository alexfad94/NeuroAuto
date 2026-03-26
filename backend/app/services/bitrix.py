from __future__ import annotations

from typing import Optional

import httpx

from ..config import settings


def _clean_base(url: str) -> str:
    return url.rstrip("/")


class BitrixClient:
    def __init__(self) -> None:
        self.base_url = _clean_base(settings.bitrix_webhook_url)
        self._lead_fields_cache: Optional[dict] = None
        self._department_cache: Optional[dict[str, dict]] = None

    async def _post(self, method: str, data: dict) -> dict:
        if not self.base_url:
            return {"result": None}

        url = f"{self.base_url}/{method}.json"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            return response.json()

    async def _get_lead_fields(self) -> dict:
        if self._lead_fields_cache is not None:
            return self._lead_fields_cache
        res = await self._post("crm.lead.fields", {})
        self._lead_fields_cache = res.get("result", {}) or {}
        return self._lead_fields_cache

    async def _enum_id(self, field_code: str, value: str) -> Optional[str]:
        fields = await self._get_lead_fields()
        meta = fields.get(field_code, {})
        for item in meta.get("items", []):
            if str(item.get("VALUE", "")).lower() == value.lower():
                return str(item.get("ID"))
        return None

    async def _get_departments(self) -> dict[str, dict]:
        if self._department_cache is not None:
            return self._department_cache
        res = await self._post("department.get", {})
        departments = res.get("result", []) or []
        self._department_cache = {str(d.get("NAME", "")).lower(): d for d in departments}
        return self._department_cache

    async def get_department_by_name(self, department_name: str) -> Optional[dict]:
        deps = await self._get_departments()
        return deps.get(department_name.lower())

    async def create_route_task(
        self,
        *,
        lead_id: int,
        department_name: str,
        route_queue: str,
        summary: str,
    ) -> Optional[int]:
        department = await self.get_department_by_name(department_name)
        responsible_id = str(settings.default_manager_id)
        department_id = None
        if department:
            department_id = str(department.get("ID"))
            if department.get("UF_HEAD"):
                responsible_id = str(department.get("UF_HEAD"))

        title = f"[{department_name}] Лид #{lead_id}: обработать маршрут"
        description = (
            f"Очередь: {route_queue}\n"
            f"Лид ID: {lead_id}\n"
            f"Описание: {summary}\n"
        )
        if department_id:
            description += f"ID отдела: {department_id}\n"

        res = await self._post(
            "tasks.task.add",
            {
                "fields[TITLE]": title,
                "fields[RESPONSIBLE_ID]": responsible_id,
                "fields[DESCRIPTION]": description,
            },
        )
        task = (res.get("result") or {}).get("task", {})
        task_id = task.get("id")
        return int(task_id) if task_id else None

    async def create_lead(
        self,
        *,
        title: str,
        name: str,
        phone: Optional[str],
        comments: str,
        session_id: str,
        trigger_code: Optional[str],
        car_model: Optional[str],
        budget: Optional[float],
        preferred_contact: str,
    ) -> Optional[int]:
        payload: dict[str, str] = {
            "fields[TITLE]": title,
            "fields[NAME]": name or "Клиент чата",
            "fields[SOURCE_ID]": "WEB",
            "fields[COMMENTS]": comments,
            "fields[ASSIGNED_BY_ID]": str(settings.default_manager_id),
            "fields[UF_CRM_CHAT_SESSION_ID]": session_id,
        }
        channel_id = await self._enum_id("UF_CRM_CHAT_CHANNEL", "webchat")
        if channel_id:
            payload["fields[UF_CRM_CHAT_CHANNEL]"] = channel_id
        contact_enum_id = await self._enum_id(
            "UF_CRM_PREFERRED_CONTACT", preferred_contact or "call"
        )
        if contact_enum_id:
            payload["fields[UF_CRM_PREFERRED_CONTACT]"] = contact_enum_id
        if phone:
            payload["fields[PHONE][0][VALUE]"] = phone
            payload["fields[PHONE][0][VALUE_TYPE]"] = "WORK"
        if trigger_code:
            payload["fields[UF_CRM_TRIGGER_CODE]"] = trigger_code
        if car_model:
            payload["fields[UF_CRM_CAR_MODEL]"] = car_model
        if budget:
            payload["fields[UF_CRM_BUDGET]"] = str(budget)

        res = await self._post("crm.lead.add", payload)
        lead_id = res.get("result")
        return int(lead_id) if lead_id else None

    async def add_timeline_comment(self, lead_id: int, comment: str) -> Optional[int]:
        payload = {
            "fields[ENTITY_TYPE]": "lead",
            "fields[ENTITY_ID]": str(lead_id),
            "fields[COMMENT]": comment,
        }
        res = await self._post("crm.timeline.comment.add", payload)
        item_id = res.get("result")
        return int(item_id) if item_id else None

    async def add_activity(
        self,
        lead_id: int,
        phone: Optional[str],
        description: str,
        subject: str = "Обработать заявку из чат-бота",
    ) -> Optional[int]:
        payload = {
            "fields[OWNER_TYPE_ID]": "1",
            "fields[OWNER_ID]": str(lead_id),
            "fields[TYPE_ID]": "2",
            "fields[SUBJECT]": subject,
            "fields[DESCRIPTION]": description,
            "fields[DESCRIPTION_TYPE]": "3",
            "fields[RESPONSIBLE_ID]": str(settings.default_manager_id),
            "fields[PRIORITY]": "2",
            "fields[COMPLETED]": "N",
            "fields[COMMUNICATIONS][0][TYPE]": "PHONE",
            "fields[COMMUNICATIONS][0][VALUE]": phone or "+70000000000",
            "fields[COMMUNICATIONS][0][ENTITY_TYPE_ID]": "1",
            "fields[COMMUNICATIONS][0][ENTITY_ID]": str(lead_id),
        }
        res = await self._post("crm.activity.add", payload)
        item_id = res.get("result")
        return int(item_id) if item_id else None

    async def update_status(self, lead_id: int, status_id: str) -> bool:
        payload = {"id": str(lead_id), "fields[STATUS_ID]": status_id}
        res = await self._post("crm.lead.update", payload)
        return bool(res.get("result"))

    async def update_route_fields(
        self,
        *,
        lead_id: int,
        route_department: str,
        route_status: str = "routed",
        route_queue: Optional[str] = None,
        route_department_real_id: Optional[str] = None,
        route_task_id: Optional[int] = None,
    ) -> bool:
        payload: dict[str, str] = {"id": str(lead_id)}
        department_id = await self._enum_id("UF_CRM_ROUTE_DEPARTMENT", route_department)
        status_id = await self._enum_id("UF_CRM_ROUTE_STATUS", route_status)

        if department_id:
            payload["fields[UF_CRM_ROUTE_DEPARTMENT]"] = department_id
        if status_id:
            payload["fields[UF_CRM_ROUTE_STATUS]"] = status_id
        if route_queue:
            payload["fields[UF_CRM_ROUTE_QUEUE]"] = route_queue
        if route_department_real_id:
            payload["fields[UF_CRM_ROUTE_DEPARTMENT_REAL_ID]"] = route_department_real_id
        if route_task_id:
            payload["fields[UF_CRM_ROUTE_TASK_ID]"] = str(route_task_id)

        if len(payload) == 1:
            return False

        res = await self._post("crm.lead.update", payload)
        return bool(res.get("result"))
