"""
🏥 AdaptAI - Model de mensagens equipe<->familia (vertical CLINICA).

Espelha 016_clinica_mensagens.sql. Canal simples de recados por paciente.
"""
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Enum as SQLEnum
from datetime import datetime, timezone
import enum
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class OrigemMensagem(str, enum.Enum):
    EQUIPE = "EQUIPE"
    FAMILIA = "FAMILIA"


class MensagemFamilia(Base):
    __tablename__ = "mensagens_familia"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    origem = Column(SQLEnum(OrigemMensagem), nullable=False)
    autor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    texto = Column(Text, nullable=False)
    criado_em = Column(DateTime, default=_agora)
