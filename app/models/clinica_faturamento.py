"""
🏥 AdaptAI - Models de faturamento/convenios (vertical CLINICA).

Espelha 020_clinica_faturamento.sql. Enums com value == NAME (uppercase) para
casar com os literais das migrations MySQL.

`Convenio`    : fonte pagadora (particular/convenio/SUS).
`Faturamento` : item faturavel por competencia (mes 'YYYY-MM'), opcionalmente
                ligado a uma sessao e a um convenio, com valor e status.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, DECIMAL, ForeignKey,
    Enum as SQLEnum,
)
from datetime import datetime, timezone
import enum
from app.database import Base
from app.models.clinica_core import Especialidade


def _agora():
    return datetime.now(timezone.utc)


class TipoConvenio(str, enum.Enum):
    PARTICULAR = "PARTICULAR"
    CONVENIO = "CONVENIO"
    SUS = "SUS"


class StatusFaturamento(str, enum.Enum):
    A_FATURAR = "A_FATURAR"
    FATURADO = "FATURADO"
    PAGO = "PAGO"
    GLOSADO = "GLOSADO"


class Convenio(Base):
    """Fonte pagadora da clinica (por tenant)."""
    __tablename__ = "convenios"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    tipo = Column(SQLEnum(TipoConvenio), nullable=False, default=TipoConvenio.CONVENIO)
    registro_ans = Column(String(60), nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=_agora)


class Faturamento(Base):
    """Item faturavel. `competencia` = mes de referencia 'YYYY-MM'."""
    __tablename__ = "faturamentos"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True)
    convenio_id = Column(Integer, ForeignKey("convenios.id", ondelete="SET NULL"), nullable=True)
    competencia = Column(String(7), nullable=False)
    valor = Column(DECIMAL(10, 2), nullable=False, default=0)
    status = Column(SQLEnum(StatusFaturamento), nullable=False, default=StatusFaturamento.A_FATURAR)
    observacao = Column(String(255), nullable=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)


class PrecoEspecialidade(Base):
    """Preco padrao por especialidade (por tenant). Base do faturamento por sessao."""
    __tablename__ = "precos_especialidade"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    especialidade = Column(SQLEnum(Especialidade), nullable=False)
    valor = Column(DECIMAL(10, 2), nullable=False, default=0)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)
