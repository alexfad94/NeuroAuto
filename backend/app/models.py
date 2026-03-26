from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=3, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)
    client_name: Optional[str] = Field(default="Клиент чата", max_length=120)
    phone: Optional[str] = Field(default=None, max_length=32)
    preferred_contact: Optional[str] = Field(default="call", max_length=32)
    car_model: Optional[str] = Field(default=None, max_length=120)
    budget: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    escalated: bool = False
    trigger_code: Optional[str] = None
    lead_id: Optional[int] = None
