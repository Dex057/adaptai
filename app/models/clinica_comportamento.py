"""
🏥 AdaptAI - Model de registro de comportamento ABC (vertical CLINICA).

Espelha 017_clinica_comportamento.sql. Registro ABC + frequencia/duracao/
intensidade de comportamentos-alvo.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from datetime import datetime, timezone
import enum
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class Intensidade(str, enum.Enum):
    LEVE = "LEVE"
    MODERADA = "MODERADA"
    INTENSA = "INTENSA"


class RegistroComportamento(Base):
    __tablename__ = "registros_comportamento"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True)
    comportamento = Column(String(255), nullable=False)
    antecedente = Column(Text, nullable=True)
    consequencia = Column(Text, nullable=True)
    frequencia = Column(Integer, nullable=True)
    duracao_seg = Column(Integer, nullable=True)
    intensidade = Column(SQLEnum(Intensidade), nullable=True)
    data_hora = Column(DateTime, nullable=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
