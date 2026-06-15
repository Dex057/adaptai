"""Schemas do feedback formativo de redacao (IA) — superficie mobile."""
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackRedacaoRequest(BaseModel):
    texto: str
    student_id: Optional[int] = Field(default=None, description="Opcional: ajusta o tom ao perfil")
    foco: Optional[str] = Field(default=None, description="Foco opcional do retorno")


class FeedbackRedacaoResponse(BaseModel):
    markdown: str
