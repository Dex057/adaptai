"""
🏥 AdaptAI - Model de aplicacao de instrumentos padronizados (vertical CLINICA).

Espelha 018_clinica_instrumentos.sql. Registro generico de aplicacao de
instrumento/escala com pontuacao, para acompanhar evolucao no tempo.
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, DECIMAL, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class AplicacaoInstrumento(Base):
    __tablename__ = "aplicacoes_instrumento"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    instrumento = Column(String(120), nullable=False)
    data = Column(Date, nullable=True)
    pontuacao = Column(DECIMAL(7, 2), nullable=True)
    pontuacao_max = Column(DECIMAL(7, 2), nullable=True)
    observacao = Column(Text, nullable=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
