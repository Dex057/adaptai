"""
🏥 AdaptAI - Model de repasse ao profissional (vertical CLINICA).

Espelha 024_clinica_repasse.sql. Um repasse por profissional por competencia
(mes): base faturada -> percentual do contrato -> valor a repassar. PENDENTE/PAGO.
"""
from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class Repasse(Base):
    __tablename__ = "repasses"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True)
    competencia = Column(String(7), nullable=False)
    valor_base = Column(DECIMAL(10, 2), nullable=False, default=0)
    percentual = Column(DECIMAL(5, 2), nullable=False, default=0)
    valor_repasse = Column(DECIMAL(10, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="PENDENTE")
    observacao = Column(String(255), nullable=True)
    pago_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=_agora)
