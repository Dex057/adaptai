"""
🏥 AdaptAI - Models do programa de casa (vertical CLINICA).

Espelha 015_clinica_programa_casa.sql. Tarefas de generalizacao definidas pelo
terapeuta; a familia marca "fez/nao fez" por dia pelo portal.
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class TarefaCasa(Base):
    __tablename__ = "tarefas_casa"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


class TarefaCasaCheck(Base):
    __tablename__ = "tarefa_casa_check"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas_casa.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(Date, nullable=False)
    feito = Column(Boolean, nullable=False, default=False)
    observacao = Column(String(500), nullable=True)
    criado_em = Column(DateTime, default=_agora)
