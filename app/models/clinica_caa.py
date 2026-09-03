"""
🏥 AdaptAI - Models de CAA (pranchas de comunicação) - vertical CLINICA.

Espelha a migration 013_clinica_caa.sql. Pranchas de comunicação, rotinas
visuais e histórias sociais montadas com pictogramas ARASAAC (reusa o
pictograma_service). Item guarda arasaac_id + URL do CDN + rótulo.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum,
)
from datetime import datetime, timezone
import enum
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class TipoPrancha(str, enum.Enum):
    COMUNICACAO = "COMUNICACAO"
    ROTINA = "ROTINA"
    HISTORIA_SOCIAL = "HISTORIA_SOCIAL"


class Prancha(Base):
    __tablename__ = "pranchas"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="SET NULL"), nullable=True, index=True)
    titulo = Column(String(255), nullable=False)
    tipo = Column(SQLEnum(TipoPrancha), nullable=False, default=TipoPrancha.COMUNICACAO)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


class PranchaItem(Base):
    __tablename__ = "prancha_itens"

    id = Column(Integer, primary_key=True, index=True)
    prancha_id = Column(Integer, ForeignKey("pranchas.id", ondelete="CASCADE"), nullable=False, index=True)
    ordem = Column(Integer, nullable=False, default=0)
    arasaac_id = Column(Integer, nullable=True)
    imagem_url = Column(String(1000), nullable=True)
    rotulo = Column(String(255), nullable=False)
    criado_em = Column(DateTime, default=_agora)
