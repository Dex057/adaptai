"""
🏥 AdaptAI - Generalização nos 3 ambientes (clínica · casa · escola).

Agrega o desempenho do mesmo paciente na clínica (objetivos do PTI + último %),
em casa (programa de casa + adesão 7d) e na escola (PEI via o vínculo aluno↔
paciente), e oferece uma SÍNTESE por IA sobre a generalização. Diferencial do
ADAPT: os três ambientes no mesmo lugar. Gate CLINICA; acesso pelo guard clínico.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico, generalizacao_service
from app.models.clinica_core import VinculoAlunoPaciente
from app.models.clinica_terapia import (
    PlanoTerapeutico, ObjetivoTerapeutico, RegistroTentativa, Sessao,
)
from app.models.clinica_casa import TarefaCasa, TarefaCasaCheck
from app.models.student import Student
from app.models.pei import PEI, PEIObjetivo

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Generalização)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _v(e):
    return e.value if hasattr(e, "value") else e


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _coletar(db: Session, paciente):
    # --- clínica: objetivos + último % ---
    objs = (
        db.query(ObjetivoTerapeutico)
        .join(PlanoTerapeutico, PlanoTerapeutico.id == ObjetivoTerapeutico.plano_id)
        .filter(PlanoTerapeutico.paciente_id == paciente.id)
        .order_by(ObjetivoTerapeutico.ordem)
        .all()
    )
    obj_ids = [o.id for o in objs] or [0]
    regs = (
        db.query(RegistroTentativa, Sessao.data_sessao)
        .join(Sessao, Sessao.id == RegistroTentativa.sessao_id)
        .filter(RegistroTentativa.objetivo_id.in_(obj_ids))
        .order_by(Sessao.data_sessao)
        .all()
    )
    ult = {}
    for reg, _data in regs:
        pct = reg.percentual_independencia
        if pct is None and reg.tentativas:
            pct = round((reg.acertos or 0) * 100.0 / reg.tentativas, 2)
        ult[reg.objetivo_id] = float(pct) if pct is not None else None
    clinica = [{
        "objetivo_id": o.id, "descricao": o.descricao,
        "status": _v(o.status), "pct_ultimo": ult.get(o.id),
    } for o in objs]

    # --- casa: programa + adesão 7d ---
    tarefas = (
        db.query(TarefaCasa)
        .filter(TarefaCasa.paciente_id == paciente.id, TarefaCasa.ativo.is_(True))
        .order_by(TarefaCasa.id.desc()).all()
    )
    d7 = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    feitos = dict(
        db.query(TarefaCasaCheck.tarefa_id, func.count(TarefaCasaCheck.id))
        .filter(TarefaCasaCheck.data >= d7, TarefaCasaCheck.feito.is_(True),
                TarefaCasaCheck.tarefa_id.in_([t.id for t in tarefas] or [0]))
        .group_by(TarefaCasaCheck.tarefa_id).all()
    )
    casa = {
        "itens": [{"titulo": t.titulo, "feitos_7d": feitos.get(t.id, 0)} for t in tarefas],
        "total": len(tarefas),
    }

    # --- escola: PEI via vínculo ---
    escola = {"vinculado": False, "aluno": None, "objetivos": []}
    v = db.query(VinculoAlunoPaciente).filter(VinculoAlunoPaciente.paciente_id == paciente.id).first()
    if v:
        aluno = db.query(Student).filter(Student.id == v.aluno_id).first()
        if aluno:
            pei = db.query(PEI).filter(PEI.student_id == aluno.id).order_by(PEI.created_at.desc()).first()
            objetivos = []
            if pei:
                for o in db.query(PEIObjetivo).filter(PEIObjetivo.pei_id == pei.id).order_by(PEIObjetivo.area).all():
                    va, al = _num(o.valor_atual), _num(o.valor_alvo)
                    pct = round(va / al * 100) if (va is not None and al) else None
                    objetivos.append({"titulo": o.titulo or o.area, "area": o.area, "status": o.status, "pct": pct})
            escola = {"vinculado": True, "aluno": {"nome": aluno.name, "serie": aluno.grade_level}, "objetivos": objetivos}

    return clinica, casa, escola


@router.get("/pacientes/{paciente_id}/generalizacao")
def generalizacao(paciente_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    clinica, casa, escola = _coletar(db, p)
    return {"clinica": clinica, "casa": casa, "escola": escola}


@router.get("/pacientes/{paciente_id}/generalizacao/sintese")
def generalizacao_sintese(paciente_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    clinica, casa, escola = _coletar(db, p)
    tem = bool(clinica) or bool(casa.get("itens")) or bool(escola.get("objetivos"))
    if not tem:
        return {"sintese": "Ainda não há dados suficientes nos três ambientes para uma síntese.", "acoes": []}
    return generalizacao_service.sintetizar(clinica, casa, escola)
