"""Schemas da Comunicacao com a familia (IA)."""
from typing import Optional

from pydantic import BaseModel, Field


class MensagemFamiliaRequest(BaseModel):
    aluno_id: int
    tom: str = Field(default="Atualizacao do dia", description="Tom da mensagem")
    nota: Optional[str] = Field(default=None, description="Contexto curto do professor")


class MensagemFamiliaResponse(BaseModel):
    mensagem: str
