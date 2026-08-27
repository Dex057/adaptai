"""
🏥 AdaptAI - Dashboard clinico (vertical CLINICA).

Visao de gestao da clinica: KPIs (pacientes, sessoes, faltas, mastery) e
ALERTAS acionaveis (meta estagnada, paciente sem sessao, consentimento ausente).
Gated pelo modulo CLINICA; escopo por tenant (escola).
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.core.entitlements import requer_modulo, Modulo
from app.models.clinica_core import (
    Paciente, StatusPaciente, Consentimento, TipoConsentimento,
)
from app.models.clinica_terapia import (
    Sessao, PlanoTerapeutico, ObjetivoTerapeutico, RegistroTentativa,
    StatusObjetivoTerapeutico,
)
from app.models.clinica_agenda import Agendamento, StatusAgendamento

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Dashboard)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)

LIMITE_ALERTAS = 25
DIAS_SEM_SESSAO = 14
DIAS_META_ESTAGNADA = 21


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    escola_id = current_user.escola_id
    is_super = current_user.role == UserRole.SUPER_ADMIN
    agora = datetime.now(timezone.utc)
    d7 = agora - timedelta(days=7)
    d30 = agora - timedelta(days=30)
    limite_sessao = agora - timedelta(days=DIAS_SEM_SESSAO)
    limite_meta = agora - timedelta(days=DIAS_META_ESTAGNADA)
    hoje_ini = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoje_fim = hoje_ini + timedelta(days=1)

    def escopo(q, coluna_escola):
        return q if is_super else q.filter(coluna_escola == escola_id)

    # --- KPIs ---
    pac_total = escopo(db.query(Paciente), Paciente.escola_id).count()
    pac_ativos = escopo(db.query(Paciente).filter(Paciente.status == StatusPaciente.ATIVO), Paciente.escola_id).count()
    sessoes_7d = escopo(db.query(Sessao).filter(Sessao.data_sessao >= d7), Sessao.escola_id).count()
    agenda_hoje = escopo(
        db.query(Agendamento).filter(
            Agendamento.inicio >= hoje_ini, Agendamento.inicio < hoje_fim,
            Agendamento.status.in_([StatusAgendamento.AGENDADO, StatusAgendamento.CONFIRMADO]),
        ), Agendamento.escola_id).count()

    faltas_30 = escopo(db.query(Agendamento).filter(Agendamento.inicio >= d30, Agendamento.status == StatusAgendamento.FALTA), Agendamento.escola_id).count()
    realiz_30 = escopo(db.query(Agendamento).filter(Agendamento.inicio >= d30, Agendamento.status == StatusAgendamento.REALIZADO), Agendamento.escola_id).count()
    taxa_falta = round(faltas_30 * 100.0 / (faltas_30 + realiz_30), 1) if (faltas_30 + realiz_30) else 0.0

    # objetivos por status
    q_obj = (db.query(ObjetivoTerapeutico.status, func.count(ObjetivoTerapeutico.id))
             .join(PlanoTerapeutico, PlanoTerapeutico.id == ObjetivoTerapeutico.plano_id))
    if not is_super:
        q_obj = q_obj.filter(PlanoTerapeutico.escola_id == escola_id)
    por_status = {s.value if hasattr(s, "value") else s: 0 for s in StatusObjetivoTerapeutico}
    for st, n in q_obj.group_by(ObjetivoTerapeutico.status).all():
        por_status[st.value if hasattr(st, "value") else st] = n

    # --- ALERTAS ---
    alertas = []

    # 1) pacientes ativos sem sessao ha DIAS_SEM_SESSAO
    ativos = escopo(
        db.query(Paciente.id, Paciente.nome).filter(Paciente.status == StatusPaciente.ATIVO),
        Paciente.escola_id).all()
    ult_sessao = dict(
        escopo(db.query(Sessao.paciente_id, func.max(Sessao.data_sessao)), Sessao.escola_id)
        .group_by(Sessao.paciente_id).all()
    )
    for pid, nome in ativos:
        ult = ult_sessao.get(pid)
        if ult is None or ult < limite_sessao:
            alertas.append({
                "tipo": "SEM_SESSAO", "paciente_id": pid, "paciente_nome": nome,
                "detalhe": "Sem sessão há mais de %d dias" % DIAS_SEM_SESSAO if ult else "Nenhuma sessão registrada",
            })
        if len(alertas) >= LIMITE_ALERTAS:
            break

    # 2) pacientes ativos sem consentimento de tratamento vigente
    com_consent = set(
        pid for (pid,) in escopo(
            db.query(Consentimento.paciente_id).filter(
                Consentimento.tipo == TipoConsentimento.TRATAMENTO_DADOS,
                Consentimento.revogado_em.is_(None),
            ), Consentimento.escola_id).all()
    )
    consent_alertas = 0
    for pid, nome in ativos:
        if pid not in com_consent:
            alertas.append({
                "tipo": "CONSENTIMENTO", "paciente_id": pid, "paciente_nome": nome,
                "detalhe": "Sem consentimento de tratamento vigente",
            })
            consent_alertas += 1
            if consent_alertas >= LIMITE_ALERTAS:
                break

    # 3) metas em aquisicao estagnadas (ultimo registro antigo ou inexistente)
    q_metas = (db.query(ObjetivoTerapeutico.id, ObjetivoTerapeutico.descricao, PlanoTerapeutico.paciente_id, Paciente.nome)
               .join(PlanoTerapeutico, PlanoTerapeutico.id == ObjetivoTerapeutico.plano_id)
               .join(Paciente, Paciente.id == PlanoTerapeutico.paciente_id)
               .filter(ObjetivoTerapeutico.status == StatusObjetivoTerapeutico.EM_AQUISICAO))
    if not is_super:
        q_metas = q_metas.filter(PlanoTerapeutico.escola_id == escola_id)
    metas = q_metas.limit(200).all()
    ult_reg = dict(
        db.query(RegistroTentativa.objetivo_id, func.max(Sessao.data_sessao))
        .join(Sessao, Sessao.id == RegistroTentativa.sessao_id)
        .group_by(RegistroTentativa.objetivo_id).all()
    )
    meta_alertas = 0
    for oid, desc, pid, nome in metas:
        ult = ult_reg.get(oid)
        if ult is None or ult < limite_meta:
            alertas.append({
                "tipo": "META_ESTAGNADA", "paciente_id": pid, "paciente_nome": nome,
                "detalhe": "Meta sem registro há %d+ dias: %s" % (DIAS_META_ESTAGNADA, (desc or "")[:80]),
            })
            meta_alertas += 1
            if meta_alertas >= LIMITE_ALERTAS:
                break

    return {
        "kpis": {
            "pacientes_total": pac_total,
            "pacientes_ativos": pac_ativos,
            "sessoes_7d": sessoes_7d,
            "agenda_hoje": agenda_hoje,
            "taxa_falta_30d": taxa_falta,
            "metas_mastery": por_status.get("MASTERY", 0),
        },
        "objetivos_por_status": por_status,
        "alertas": alertas,
    }
