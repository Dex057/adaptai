"""
🏥 AdaptAI - Models do nucleo clinico (vertical CLINICA - Fase 0).

Espelha a migration 011_clinica_core.sql. Entidades-ancora do prontuario e a
ponte "equipe do caso x paciente", alem do entitlement por tenant e da trilha
de auditoria (LGPD - dado sensivel de saude).

REGRA DE BOUNDED CONTEXT: este modulo pertence ao vertical CLINICA. Ele pode
depender do KERNEL (users, escolas) mas NUNCA do vertical ESCOLA. O unico ponto
de contato e `VinculoAlunoPaciente` (ponte opcional), que so e usada quando os
dois modulos coexistem no mesmo tenant.

Enums: valor == NOME em MAIUSCULO, para casar com os literais ENUM das migrations
(o SQLAlchemy persiste o nome do membro).
"""
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey,
    Enum as SQLEnum, DECIMAL,
)
from datetime import datetime, timezone
import enum
from app.database import Base


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
class ModuloEscola(str, enum.Enum):
    """Modulos licenciaveis por tenant (espelha app/core/entitlements.Modulo)."""
    ESCOLA = "ESCOLA"
    CLINICA = "CLINICA"
    INTELIGENCIA = "INTELIGENCIA"


class Especialidade(str, enum.Enum):
    PSICOLOGIA_ABA = "PSICOLOGIA_ABA"
    FONOAUDIOLOGIA = "FONOAUDIOLOGIA"
    TERAPIA_OCUPACIONAL = "TERAPIA_OCUPACIONAL"
    PSICOPEDAGOGIA = "PSICOPEDAGOGIA"
    FISIOTERAPIA = "FISIOTERAPIA"
    MUSICOTERAPIA = "MUSICOTERAPIA"
    NUTRICAO = "NUTRICAO"
    NEUROPEDIATRIA = "NEUROPEDIATRIA"
    OUTRO = "OUTRO"


class Conselho(str, enum.Enum):
    CRP = "CRP"
    CFFA = "CFFA"
    CREFITO = "CREFITO"
    CRM = "CRM"
    CRN = "CRN"
    CREF = "CREF"
    OUTRO = "OUTRO"


class PapelProfissional(str, enum.Enum):
    ADMIN_CLINICA = "ADMIN_CLINICA"
    RESPONSAVEL_TECNICO = "RESPONSAVEL_TECNICO"
    COORDENADOR = "COORDENADOR"
    SUPERVISOR = "SUPERVISOR"
    APLICADOR = "APLICADOR"
    TERAPEUTA = "TERAPEUTA"


class PapelNoCaso(str, enum.Enum):
    RESPONSAVEL = "RESPONSAVEL"
    COTERAPEUTA = "COTERAPEUTA"
    SUPERVISOR = "SUPERVISOR"
    OBSERVADOR = "OBSERVADOR"


class StatusPaciente(str, enum.Enum):
    EM_AVALIACAO = "EM_AVALIACAO"
    ATIVO = "ATIVO"
    INATIVO = "INATIVO"
    ALTA = "ALTA"


class TipoConsentimento(str, enum.Enum):
    TRATAMENTO_DADOS = "TRATAMENTO_DADOS"
    USO_IMAGEM = "USO_IMAGEM"
    COMPARTILHA_ESCOLA = "COMPARTILHA_ESCOLA"
    COMPARTILHA_CONVENIO = "COMPARTILHA_CONVENIO"


class AcaoAuditoria(str, enum.Enum):
    VISUALIZAR = "VISUALIZAR"
    CRIAR = "CRIAR"
    EDITAR = "EDITAR"
    EXPORTAR = "EXPORTAR"
    IMPRIMIR = "IMPRIMIR"


def _agora():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Entitlement
# --------------------------------------------------------------------------
class EscolaModulo(Base):
    """Modulo que um tenant (escola) tem ativo. Base do "vender separado/junto"."""
    __tablename__ = "escola_modulos"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    modulo = Column(SQLEnum(ModuloEscola), nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)
    ativado_em = Column(DateTime, default=_agora)
    desativado_em = Column(DateTime, nullable=True)
    observacao = Column(String(500), nullable=True)


# --------------------------------------------------------------------------
# Profissional
# --------------------------------------------------------------------------
class Profissional(Base):
    """Terapeuta: liga um usuario ao tenant + especialidade e papel."""
    __tablename__ = "profissionais"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nome = Column(String(255), nullable=False)
    especialidade = Column(SQLEnum(Especialidade), nullable=False)
    conselho_tipo = Column(SQLEnum(Conselho), nullable=True)
    conselho_numero = Column(String(50), nullable=True)
    papel = Column(SQLEnum(PapelProfissional), nullable=False, default=PapelProfissional.TERAPEUTA)
    ativo = Column(Boolean, nullable=False, default=True)
    percentual_repasse = Column(DECIMAL(5, 2), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


# --------------------------------------------------------------------------
# Paciente
# --------------------------------------------------------------------------
class Paciente(Base):
    """Titular do prontuario. DADO SENSIVEL DE SAUDE (LGPD art. 11)."""
    __tablename__ = "pacientes"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False, index=True)
    nome = Column(String(255), nullable=False)
    data_nascimento = Column(Date, nullable=True)
    responsavel_nome = Column(String(255), nullable=True)
    responsavel_contato = Column(String(100), nullable=True)
    status = Column(SQLEnum(StatusPaciente), nullable=False, default=StatusPaciente.EM_AVALIACAO)
    # Token read-only para o Portal da Familia (espelha o studentToken).
    token_familia = Column(String(64), unique=True, nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)


# --------------------------------------------------------------------------
# Equipe do caso (ponte equipe x paciente)
# --------------------------------------------------------------------------
class EquipeCaso(Base):
    """Ponte equipe-do-caso x paciente. O guard de acesso clinico valida aqui."""
    __tablename__ = "equipe_caso"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False, index=True)
    papel_no_caso = Column(SQLEnum(PapelNoCaso), nullable=False, default=PapelNoCaso.COTERAPEUTA)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime, default=_agora)


# --------------------------------------------------------------------------
# Consentimento (LGPD)
# --------------------------------------------------------------------------
class Consentimento(Base):
    """Aceite do responsavel para tratar dado sensivel de saude (LGPD art. 11)."""
    __tablename__ = "consentimentos"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(SQLEnum(TipoConsentimento), nullable=False)
    versao_texto = Column(String(100), nullable=False)
    concedido_por = Column(String(255), nullable=False)
    concedido_em = Column(DateTime, default=_agora)
    revogado_em = Column(DateTime, nullable=True)  # NULL = vigente


# --------------------------------------------------------------------------
# Vinculo opcional Aluno x Paciente (ponte escola<->clinica)
# --------------------------------------------------------------------------
class VinculoAlunoPaciente(Base):
    """Vinculo LEVE aluno<->paciente. So usado quando ESCOLA e CLINICA coexistem."""
    __tablename__ = "vinculo_aluno_paciente"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    aluno_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    criado_em = Column(DateTime, default=_agora)


# --------------------------------------------------------------------------
# Auditoria de acesso (trilha de prontuario)
# --------------------------------------------------------------------------
class AuditoriaAcesso(Base):
    """Trilha de quem acessou qual prontuario e quando. usuario_id sem FK de
    proposito: a trilha deve sobreviver a remocao do usuario."""
    __tablename__ = "auditoria_acesso"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, nullable=False)
    usuario_id = Column(Integer, nullable=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    acao = Column(SQLEnum(AcaoAuditoria), nullable=False)
    recurso = Column(String(100), nullable=True)
    recurso_id = Column(Integer, nullable=True)
    ip = Column(String(45), nullable=True)
    criado_em = Column(DateTime, default=_agora)
