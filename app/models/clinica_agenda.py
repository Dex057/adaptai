"""
🏥 AdaptAI - Model da agenda clinica (vertical CLINICA).

Espelha a migration 014_clinica_agenda.sql. Agendamento de atendimento ligado a
paciente + profissional + especialidade. Ao ser REALIZADO, o app cria uma
`Sessao` e guarda o vinculo em `sessao_id`.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from datetime import datetime, timezone
import enum
from app.database import Base
from app.models.clinica_core import Especialidade  # mesmo vertical: reuso ok


def _agora():
    return datetime.now(timezone.utc)


class StatusAgendamento(str, enum.Enum):
    AGENDADO = "AGENDADO"
    CONFIRMADO = "CONFIRMADO"
    REALIZADO = "REALIZADO"
    FALTA = "FALTA"
    CANCELADO = "CANCELADO"
    REMARCADO = "REMARCADO"


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=False, index=True)
    especialidade = Column(SQLEnum(Especialidade), nullable=False)
    inicio = Column(DateTime, nullable=False)
    duracao_min = Column(Integer, default=50)
    status = Column(SQLEnum(StatusAgendamento), nullable=False, default=StatusAgendamento.AGENDADO)
    local = Column(String(255), nullable=True)
    observacao = Column(Text, nullable=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)
