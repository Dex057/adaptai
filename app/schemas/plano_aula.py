"""Schemas do Plano de aula simples (IA) — superficie mobile."""
from typing import List, Optional

from pydantic import BaseModel, Field


class PlanoAulaRequest(BaseModel):
    componente: str
    tema: Optional[str] = None
    duracao: Optional[str] = Field(default="1 aula")
    serie: Optional[str] = None
    perfis: Optional[List[str]] = Field(default=None, description="Perfis de apoio na turma")


class PlanoAulaResponse(BaseModel):
    markdown: str
