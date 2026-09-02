"""
🏥 AdaptAI - Models do Modulo 1 (PTI, sessao, evolucao) - vertical CLINICA.

Espelha a migration 012_clinica_pti_sessao.sql. Reaproveita o PADRAO do PEI
educacional (plano -> objetivo -> status), mas em tabelas proprias que penduram
em `pacientes` (nao em `students`), mantendo o vertical CLINICA isolado.

Regra "IA rascunha, humano assina": `Evolucao.rascunho_ia` marca texto gerado
por IA; a evolucao so vale apos `assinado_por_id`/`assinado_em`.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean, DECIMAL, ForeignKey,
    Enum as SQLEnum,
)
from datetime import datetime, timezone
import enum
from app.database import Base
from app.models.clinica_core import Especialidade  # mesmo vertical: reuso ok


def _agora():
    return datetime.now(timezone.utc)


class StatusPlanoTerapeutico(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    ATIVO = "ATIVO"
    EM_REVISAO = "EM_REVISAO"
    CONCLUIDO = "CONCLUIDO"
    ARQUIVADO = "ARQUIVADO"


class StatusObjetivoTerapeutico(str, enum.Enum):
    """Ciclo de vida clinico de uma meta (ABA e demais especialidades)."""
    BASELINE = "BASELINE"
    EM_AQUISICAO = "EM_AQUISICAO"
    MASTERY = "MASTERY"
    MANUTENCAO = "MANUTENCAO"
    GENERALIZACAO = "GENERALIZACAO"
    DESCONTINUADO = "DESCONTINUADO"


class Presenca(str, enum.Enum):
    PRESENTE = "PRESENTE"
    FALTA = "FALTA"
    REMARCADA = "REMARCADA"


class NivelAjuda(str, enum.Enum):
    """Nivel de ajuda (prompting) numa tentativa. Independente = melhor."""
    INDEPENDENTE = "INDEPENDENTE"
    AJUDA_VERBAL = "AJUDA_VERBAL"
    AJUDA_GESTUAL = "AJUDA_GESTUAL"
    AJUDA_FISICA_PARCIAL = "AJUDA_FISICA_PARCIAL"
    AJUDA_FISICA_TOTAL = "AJUDA_FISICA_TOTAL"


class PlanoTerapeutico(Base):
    """Plano Terapeutico Individual (PTI). Espelha `peis`, ancorado em paciente."""
    __tablename__ = "planos_terapeuticos"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String(255), nullable=False)
    periodo_inicio = Column(Date, nullable=True)
    periodo_fim = Column(Date, nullable=True)
    status = Column(SQLEnum(StatusPlanoTerapeutico), nullable=False, default=StatusPlanoTerapeutico.RASCUNHO)
    aprovado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    aprovado_em = Column(DateTime, nullable=True)
    assinatura_hash = Column(String(64), nullable=True)
    revisao_nota = Column(String(500), nullable=True)
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


class ObjetivoTerapeutico(Base):
    """Meta/programa dentro de um PTI. Espelha `pei_objetivos`, ciclo clinico."""
    __tablename__ = "objetivos_terapeuticos"

    id = Column(Integer, primary_key=True, index=True)
    plano_id = Column(Integer, ForeignKey("planos_terapeuticos.id", ondelete="CASCADE"), nullable=False, index=True)
    especialidade = Column(SQLEnum(Especialidade), nullable=False)
    descricao = Column(Text, nullable=False)
    criterio_mastery = Column(String(500), nullable=True)
    linha_base = Column(DECIMAL(5, 2), nullable=True)
    status = Column(SQLEnum(StatusObjetivoTerapeutico), nullable=False, default=StatusObjetivoTerapeutico.BASELINE)
    ordem = Column(Integer, default=0)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


class Sessao(Base):
    """Encontro terapeutico."""
    __tablename__ = "sessoes"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=False, index=True)
    especialidade = Column(SQLEnum(Especialidade), nullable=False)
    data_sessao = Column(DateTime, nullable=True)
    duracao_min = Column(Integer, nullable=True)
    presenca = Column(SQLEnum(Presenca), nullable=False, default=Presenca.PRESENTE)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=_agora)


class RegistroTentativa(Base):
    """Dado por meta por sessao (ABA/independencia). Alimenta a curva de evolucao."""
    __tablename__ = "registros_tentativa"

    id = Column(Integer, primary_key=True, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False, index=True)
    objetivo_id = Column(Integer, ForeignKey("objetivos_terapeuticos.id", ondelete="CASCADE"), nullable=False, index=True)
    tentativas = Column(Integer, nullable=False, default=0)
    acertos = Column(Integer, nullable=False, default=0)
    nivel_ajuda = Column(SQLEnum(NivelAjuda), nullable=True)
    percentual_independencia = Column(DECIMAL(5, 2), nullable=True)
    criado_em = Column(DateTime, default=_agora)


class Evolucao(Base):
    """Nota clinica da sessao. IA rascunha; profissional habilitado assina."""
    __tablename__ = "evolucoes"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="SET NULL"), nullable=True, index=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=True)
    especialidade = Column(SQLEnum(Especialidade), nullable=True)
    texto = Column(Text, nullable=False)
    rascunho_ia = Column(Boolean, nullable=False, default=False)
    assinado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assinado_em = Column(DateTime, nullable=True)  # NULL = nao assinada
    assinatura_hash = Column(String(64), nullable=True)  # SHA-256 no ato da assinatura
    criado_em = Column(DateTime, default=_agora)
