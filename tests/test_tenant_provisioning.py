"""
Teste da ativacao manual de conta (app/services/tenant_provisioning.py),
usada tanto pelo checkout publico quanto pelo POST /planos/admin/ativar-conta
(fluxo: lead fala no WhatsApp, time ativa com o valor negociado).

Trava:
  - email/CNPJ duplicado bloqueia com TenantProvisioningError, sem sujar o banco;
  - status "ativa" cobra no ciclo atual (sem trial); "trial" nao cobra por 14 dias;
  - valor_mensal informado (negociado) sobrepoe o valor de tabela do plano;
  - sem senha informada, gera senha provisoria + link de definir senha.

Estrategia: sqlite em memoria + create_all, sem tocar Asaas (criar_cobranca_asaas=False).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401 - registra todos os models no metadata
from app.models.plano import Plano
from app.models.assinatura import StatusAssinatura
from app.services.tenant_provisioning import criar_escola_com_admin, TenantProvisioningError


@pytest.fixture(scope="module")
def TestSession():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield sessionmaker(autocommit=False, autoflush=False, bind=eng)
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db(TestSession):
    session = TestSession()
    yield session
    session.close()


@pytest.fixture(scope="module")
def plano(TestSession):
    session = TestSession()
    p = Plano(nome="Profissional", slug="profissional", valor=699.0, limite_alunos=100,
               limite_professores=10, limite_provas_mes=200, limite_materiais_mes=200,
               limite_peis_mes=100, limite_relatorios_mes=100, ativo=True)
    session.add(p)
    session.commit()
    session.refresh(p)
    session.close()
    return p


def _ativar(db, plano, **overrides):
    kwargs = dict(
        escola_nome="Escola Teste", escola_cnpj=None, escola_tipo="ESCOLA",
        admin_nome="Responsavel", admin_email="responsavel@escola-teste.com",
        admin_senha=None, plano=plano, valor_mensal=450.0,
        status_inicial=StatusAssinatura.TRIAL.value, criar_cobranca_asaas=False,
    )
    kwargs.update(overrides)
    return criar_escola_com_admin(db, **kwargs)


def test_ativa_conta_com_valor_negociado_e_gera_link_de_senha(db, plano):
    escola, usuario, assinatura, senha, link, _pag = _ativar(db, plano)

    assert escola.id and usuario.id and assinatura.id
    assert assinatura.valor_mensal == 450.0  # valor negociado, nao os 699 de tabela
    assert assinatura.status == StatusAssinatura.TRIAL.value
    assert assinatura.data_fim is not None  # trial tem prazo
    assert senha and link and "/redefinir-senha?token=" in link


def test_status_ativa_nao_tem_trial_e_ja_agenda_cobranca(db, plano):
    _e, _u, assinatura, _s, _l, _p = _ativar(
        db, plano, admin_email="outra@escola-teste.com", status_inicial=StatusAssinatura.ATIVA.value
    )
    assert assinatura.status == StatusAssinatura.ATIVA.value
    assert assinatura.data_fim is None
    assert assinatura.data_proxima_cobranca is not None


def test_email_duplicado_bloqueia(db, plano):
    _ativar(db, plano, admin_email="dup@escola-teste.com")
    with pytest.raises(TenantProvisioningError):
        _ativar(db, plano, admin_email="dup@escola-teste.com", escola_nome="Outra Escola")


def test_cnpj_duplicado_bloqueia(db, plano):
    _ativar(db, plano, admin_email="cnpj1@escola-teste.com", escola_cnpj="00.000.000/0001-00")
    with pytest.raises(TenantProvisioningError):
        _ativar(db, plano, admin_email="cnpj2@escola-teste.com", escola_cnpj="00.000.000/0001-00")
