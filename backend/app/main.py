from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import ChatRequest, ChatResponse
from .services.bitrix import BitrixClient
from .services.faq import load_escalation_rules
from .services.gigachat import GigaChatClient
from .services.rag import FaqRagService
from .services.routing import (
    detect_trigger,
    is_negative_confirmation,
    is_positive_confirmation,
    should_escalate_immediately,
    should_route_to_manager,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="NeuroAuto MVP API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gigachat = GigaChatClient()
bitrix = BitrixClient()
rules = load_escalation_rules()
rag = FaqRagService()
pending_routes: dict[str, dict] = {}
PENDING_TTL_SECONDS = 20 * 60

TRIGGER_TO_ROUTE = {
    "HARD_ESCALATION": ("sales", "complaints-escalation"),
    "ROUTING_FINANCE": ("finance", "finance-dept"),
    "ROUTING_TRADE_IN": ("trade_in", "trade-in-dept"),
    "ROUTING_TEST_DRIVE": ("sales", "test-drive-coordinator"),
    "ROUTING_SERVICE_QUESTION": ("service", "service-dept"),
    "ROUTING_SERVICE_DIAGNOSTICS": ("service", "service-diagnostics"),
    "ROUTING_BODY_REPAIR": ("service", "body-repair-dept"),
    "ROUTING_PARTS_SALE": ("service", "parts-dept"),
    "ROUTING_SALES_UPSELL": ("sales", "sales-upsell"),
    "ROUTING_HR_DOCS": ("hr", "hr-onboarding"),
    "ROUTING_HR_TRAINING": ("hr", "hr-training"),
}
ROUTE_TO_DEPARTMENT_NAME = {
    "sales": "Sales",
    "finance": "Finance",
    "trade_in": "Trade-In",
    "service": "Service",
    "hr": "HR",
}
ROUTE_TO_LEAD_STATUS = {
    "hard_escalation": "ROUTE_ESCALATION",
    "sales": "ROUTE_SALES",
    "finance": "ROUTE_FINANCE",
    "trade_in": "ROUTE_TRADE_IN",
    "service": "ROUTE_SERVICE",
    "hr": "ROUTE_HR",
}
TRIGGER_TO_RAG_DEPARTMENT = {
    "ROUTING_FINANCE": "sales",
    "ROUTING_TRADE_IN": "sales",
    "ROUTING_TEST_DRIVE": "sales",
    "ROUTING_SERVICE_QUESTION": "service",
    "ROUTING_SERVICE_DIAGNOSTICS": "service",
    "ROUTING_BODY_REPAIR": "service",
    "ROUTING_PARTS_SALE": "service",
    "ROUTING_HR_DOCS": "hr",
    "ROUTING_HR_TRAINING": "hr",
}


def _cleanup_pending() -> None:
    now = time.time()
    expired = [sid for sid, state in pending_routes.items() if now - state.get("ts", now) > PENDING_TTL_SECONDS]
    for sid in expired:
        pending_routes.pop(sid, None)


def _suggest_handoff(trigger_code: str | None) -> str:
    if trigger_code == "ROUTING_TRADE_IN":
        return (
            "\n\nЕсли хотите, передам запрос менеджеру трейд-ин и он свяжется с вами "
            "для оценки. Напишите: \"да, передайте менеджеру\"."
        )
    if trigger_code == "ROUTING_FINANCE":
        return (
            "\n\nЕсли хотите, передам заявку финансовому менеджеру для расчета. "
            "Напишите: \"да, передайте менеджеру\"."
        )
    if trigger_code == "ROUTING_TEST_DRIVE":
        return (
            "\n\nЕсли хотите, могу прямо сейчас передать заявку на тест-драйв менеджеру. "
            "Напишите: \"да, передайте менеджеру\"."
        )
    if trigger_code == "ROUTING_SERVICE_QUESTION":
        return (
            "\n\nЕсли нужно, передам запрос сервисному менеджеру для точной консультации. "
            "Напишите: \"да, передайте менеджеру\"."
        )
    if trigger_code in {"ROUTING_HR_DOCS", "ROUTING_HR_TRAINING"}:
        return (
            "\n\nЕсли хотите, передам ваш запрос рекрутеру. "
            "Напишите: \"да, передайте рекрутеру\"."
        )
    return ""


def _route_info(trigger_code: str | None) -> tuple[str, str]:
    if trigger_code and trigger_code in TRIGGER_TO_ROUTE:
        return TRIGGER_TO_ROUTE[trigger_code]
    return ("sales", "general-sales")


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "env": settings.app_env}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    _cleanup_pending()
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    trigger_code = detect_trigger(message, rules)
    hard_escalation = should_escalate_immediately(message, rules)
    manager_route_requested = should_route_to_manager(message)
    pending = pending_routes.get(payload.session_id)

    confirm_pending_route = bool(
        pending and is_positive_confirmation(message) and not is_negative_confirmation(message)
    )
    escalated = bool(hard_escalation or (trigger_code and manager_route_requested) or confirm_pending_route)

    if escalated:
        route_trigger = trigger_code
        route_source_message = message
        if hard_escalation:
            route_trigger = "HARD_ESCALATION"
        if confirm_pending_route and pending:
            route_trigger = pending.get("trigger_code")
            route_source_message = pending.get("initial_message", message)
            pending_routes.pop(payload.session_id, None)

        title = f"MVP Chat Lead: {payload.car_model or 'Новый клиент'}"
        comments = (
            f"Источник: webchat\n"
            f"Текст запроса: {route_source_message}\n"
            f"Триггер: {route_trigger or 'HARD_ESCALATION'}\n"
            f"SLA: до {settings.manager_response_sla_minutes} минут."
        )
        lead_id = await bitrix.create_lead(
            title=title,
            name=payload.client_name or "Клиент чата",
            phone=payload.phone,
            comments=comments,
            session_id=payload.session_id,
            trigger_code=route_trigger or "HARD_ESCALATION",
            car_model=payload.car_model,
            budget=payload.budget,
            preferred_contact=payload.preferred_contact or "call",
        )
        if lead_id:
            route_department, route_queue = _route_info(route_trigger)
            real_department_name = ROUTE_TO_DEPARTMENT_NAME.get(route_department, "Sales")
            real_department = await bitrix.get_department_by_name(real_department_name)
            real_department_id = str(real_department.get("ID")) if real_department else None

            handoff = {
                "handoff_auto": {
                    "client_id": payload.session_id,
                    "from": "SalesBot",
                    "to": "manager",
                    "context": {
                        "request": route_source_message,
                        "vehicle": payload.car_model,
                        "budget": payload.budget,
                        "preferred_contact": payload.preferred_contact,
                    },
                    "priority": "high" if hard_escalation else "medium",
                    "deadline": f"{settings.manager_response_sla_minutes}m",
                    "chat_log_url": f"{settings.public_base_url}/chat/{payload.session_id}",
                    "tags": [route_trigger or "hard_escalation", "webchat", route_department, route_queue],
                }
            }
            await bitrix.add_timeline_comment(lead_id, json.dumps(handoff, ensure_ascii=False))
            route_task_id = await bitrix.create_route_task(
                lead_id=lead_id,
                department_name=real_department_name,
                route_queue=route_queue,
                summary=route_source_message,
            )
            await bitrix.update_route_fields(
                lead_id=lead_id,
                route_department=route_department,
                route_status="routed",
                route_queue=route_queue,
                route_department_real_id=real_department_id,
                route_task_id=route_task_id,
            )
            await bitrix.add_activity(
                lead_id=lead_id,
                phone=payload.phone,
                description=f"Маршрут: {route_department}/{route_queue}. Связаться с клиентом по заявке из сайта.",
                subject=f"Маршрут {route_department}: обработать заявку",
            )
            next_status = ROUTE_TO_LEAD_STATUS.get(route_department, "ROUTED_TO_MANAGER")
            if route_trigger == "HARD_ESCALATION":
                next_status = ROUTE_TO_LEAD_STATUS.get("hard_escalation", next_status)
            await bitrix.update_status(lead_id, next_status)

        return ChatResponse(
            answer=(
                "Спасибо! Передал ваш запрос менеджеру. "
                f"Мы на связи в рабочее время {settings.dealer_working_hours}, "
                f"обычно отвечаем до {settings.manager_response_sla_minutes} минут."
            ),
            escalated=True,
            trigger_code=route_trigger or "HARD_ESCALATION",
            lead_id=lead_id,
        )

    rag_department = TRIGGER_TO_RAG_DEPARTMENT.get(trigger_code)
    answer = await gigachat.ask(
        rag.build_system_prompt(message, preferred_department=rag_department),
        message,
    )
    if trigger_code:
        pending_routes[payload.session_id] = {
            "trigger_code": trigger_code,
            "initial_message": message,
            "ts": time.time(),
        }
        answer += _suggest_handoff(trigger_code)

    if is_negative_confirmation(message):
        pending_routes.pop(payload.session_id, None)

    return ChatResponse(answer=answer, escalated=False, trigger_code=trigger_code, lead_id=None)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    file_path = FRONTEND_DIR / "index.html"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Frontend is missing")
    return FileResponse(str(file_path))

