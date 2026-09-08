"""
Provisionamento de tenant (Escola + admin + assinatura).

Usado por dois fluxos que criam a mesma coisa com dados vindos de lugares
diferentes:
- autocadastro publico (POST /checkout/iniciar) - decadente, mantido no ar
  como porta dos fundos, mas sem link visivel no front.
- ativacao manual (POST /planos/admin/ativar-conta) - o fluxo atual: lead
  fala no WhatsApp, time comercial negocia o valor e ativa a conta.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.anthropic_client import get_fast_model
from app.core.config import settings
from app.core.security import (
    create_password_reset_token,
    get_password_hash,
    password_reset_fingerprint,
)
from app.models.assinatura import Assinatura
from app.models.assinatura import StatusAssinatura as StatusAssinaturaDB
from app.models.escola import ConfiguracaoEscola, Escola
from app.models.plano import Plano
from app.models.user import User, UserRole
from app.services.asaas_service import AsaasError, asaas_service


class TenantProvisioningError(Exception):
    """Erro de validacao (email/cnpj ja cadastrado)."""


def criar_escola_com_admin(
    db: Session,
    *,
    escola_nome: str,
    escola_cnpj: Optional[str],
    escola_tipo: str,
    escola_telefone: Optional[str] = None,
    admin_nome: str,
    admin_email: str,
    admin_senha: Optional[str],  # None = gera senha provisoria (fluxo manual)
    plano: Plano,
    valor_mensal: Optional[float] = None,  # None = usa o valor de tabela do plano
    status_inicial: str = StatusAssinaturaDB.TRIAL.value,
    trial_dias: int = 14,
    cep: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
    criar_cobranca_asaas: bool = True,
):
    """
    Cria Escola + User admin + Assinatura + (best-effort) cliente/assinatura no Asaas.

    Retorna (escola, usuario, assinatura, senha_gerada_ou_None, link_definir_senha_ou_None,
    link_pagamento_ou_None). `link_definir_senha` so existe quando `admin_senha` nao foi
    informada (fluxo manual) - mesmo padrao de convite ja usado para professores
    (app/api/routes/professores.py::_enviar_convite): token de 30min, o cliente define
    a propria senha, nunca trafega em texto puro.
    """
    if db.query(User).filter(User.email == admin_email).first():
        raise TenantProvisioningError("Este email ja esta cadastrado. Faca login ou use outro email.")
    if escola_cnpj and db.query(Escola).filter(Escola.cnpj == escola_cnpj).first():
        raise TenantProvisioningError("Ja existe uma escola cadastrada com este CNPJ.")

    escola = Escola(
        nome=escola_nome,
        cnpj=escola_cnpj,
        tipo=escola_tipo,
        telefone=escola_telefone,
        email=admin_email,
        cep=cep,
        cidade=cidade,
        estado=estado,
        ativa=True,
        cor_primaria="#8B5CF6",
        cor_secundaria="#EC4899",
    )
    db.add(escola)
    db.flush()  # para obter o ID

    senha_gerada = None
    if not admin_senha:
        senha_gerada = secrets.token_urlsafe(9)
        admin_senha = senha_gerada

    usuario = User(
        name=admin_nome,
        email=admin_email,
        hashed_password=get_password_hash(admin_senha),
        role=UserRole.ADMIN,
        escola_id=escola.id,
        is_active=True,
    )
    db.add(usuario)
    db.flush()  # garante hashed_password gravado, para o fingerprint do token

    valor = valor_mensal if valor_mensal is not None else plano.valor
    em_trial = status_inicial == StatusAssinaturaDB.TRIAL.value
    data_fim_trial = datetime.now() + timedelta(days=trial_dias) if em_trial else None

    assinatura = Assinatura(
        escola_id=escola.id,
        plano_id=plano.id,
        status=status_inicial,
        data_inicio=datetime.now(),
        data_fim=data_fim_trial,
        valor_mensal=valor,
        dia_vencimento=10,
        alunos_ativos=0,
        professores_ativos=1,  # o admin conta como professor
        provas_mes_atual=0,
        materiais_mes_atual=0,
        peis_mes_atual=0,
        relatorios_mes_atual=0,
        data_proxima_cobranca=None if em_trial else datetime.now() + timedelta(days=30),
    )
    db.add(assinatura)

    configuracao = ConfiguracaoEscola(
        escola_id=escola.id,
        modelo_ia_preferido=get_fast_model(),
        quantidade_questoes_padrao=5,
        dificuldade_padrao="medio",
        notificacoes_email=True,
        pei_automatico_ativo=True,
        materiais_adaptativos_ativo=True,
        relatorios_avancados_ativo=plano.relatorios_avancados,
        lgpd_ativo=True,
    )
    db.add(configuracao)

    db.commit()

    # Integracao Asaas (best-effort: NAO bloqueia a criacao da conta)
    link_pagamento = None
    if criar_cobranca_asaas and asaas_service.esta_configurado():
        try:
            cliente = asaas_service.criar_cliente(
                nome=admin_nome,
                email=admin_email,
                cpf_cnpj=escola_cnpj or None,
                external_reference=str(escola.id),
            )
            customer_id = cliente.get("id")

            next_due = (data_fim_trial or datetime.now()).strftime("%Y-%m-%d")
            assinatura_asaas = asaas_service.criar_assinatura(
                customer_id=customer_id,
                valor=valor,
                descricao=f"AdaptAI - Plano {plano.nome}",
                next_due_date=next_due,
                billing_type="UNDEFINED",  # cliente escolhe PIX/boleto/cartao
                cycle="MONTHLY",
                external_reference=str(escola.id),
            )
            subscription_id = assinatura_asaas.get("id")

            assinatura.asaas_customer_id = customer_id
            assinatura.asaas_subscription_id = subscription_id
            db.commit()

            if subscription_id:
                link_pagamento = asaas_service.obter_link_pagamento_assinatura(subscription_id)
        except AsaasError as e:
            # Conta ja foi criada; integracao pode ser refeita depois. Apenas registra.
            print(f"[PROVISIONING/ASAAS] Integracao falhou (conta criada mesmo assim): {e}")
        except Exception as e:
            print(f"[PROVISIONING/ASAAS] Erro inesperado na integracao: {type(e).__name__}")

    link_definir_senha = None
    if senha_gerada:
        fp = password_reset_fingerprint(usuario.hashed_password)
        token = create_password_reset_token(usuario.email, fp)
        link_definir_senha = f"{settings.FRONTEND_URL.rstrip('/')}/redefinir-senha?token={token}"

    return escola, usuario, assinatura, senha_gerada, link_definir_senha, link_pagamento
