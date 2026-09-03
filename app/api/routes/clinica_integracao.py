"""
🏥 AdaptAI - Integração PEI↔PTI (vertical CLINICA).

A ponte escola<->clinica: vincula um Paciente (PTI) a um aluno/Student (PEI) e
deixa a equipe clinica ver os objetivos do PEI (o que a escola trabalha) ao lado
do plano terapeutico. Camada de integracao (toca os dois verticais de proposito).
Gate CLINICA; acesso ao paciente pelo guard clinico.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_core import VinculoAlunoPaciente, AcaoAuditoria
from app.models.student import Student
from app.models.pei import PEI, PEIObjetivo

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Integração PEI↔PTI)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _pei_resumo(db: Session, aluno_id: int):
    pei = (
        db.query(PEI)
        .filter(PEI.student_id == aluno_id)
        .order_by(PEI.created_at.desc())
        .first()
    )
    if not pei:
        return None
    objs = db.query(PEIObjetivo).filter(PEIObjetivo.pei_id == pei.id).order_by(PEIObjetivo.area).all()
    return {
        "id": pei.id,
        "ano_letivo": pei.ano_letivo,
        "status": pei.status,
        "objetivos": [{
            "id": o.id, "area": o.area, "titulo": o.titulo, "status": o.status,
            "valor_atual": _num(o.valor_atual), "valor_alvo": _num(o.valor_alvo),
        } for o in objs],
    }


def _aluno_dict(a: Student):
    return {"id": a.id, "nome": a.name, "serie": a.grade_level, "turma": a.turma}


@router.get("/pacientes/{paciente_id}/vinculo-escolar")
def obter_vinculo(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    v = db.query(VinculoAlunoPaciente).filter(VinculoAlunoPaciente.paciente_id == p.id).first()
    if not v:
        return {"vinculado": False, "aluno": None, "pei": None}
    aluno = db.query(Student).filter(Student.id == v.aluno_id).first()
    if not aluno:
        return {"vinculado": False, "aluno": None, "pei": None}
    return {"vinculado": True, "aluno": _aluno_dict(aluno), "pei": _pei_resumo(db, aluno.id)}


@router.get("/pacientes/{paciente_id}/alunos-sugeridos")
def alunos_sugeridos(
    paciente_id: int,
    q: str = Query("", description="busca por nome do aluno"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    ja = {aid for (aid,) in db.query(VinculoAlunoPaciente.aluno_id).filter(
        VinculoAlunoPaciente.escola_id == p.escola_id).all()}
    query = db.query(Student).filter(Student.escola_id == p.escola_id)
    termo = (q or "").strip()
    if termo:
        query = query.filter(Student.name.ilike(f"%{termo}%"))
    out = []
    for a in query.order_by(Student.name).limit(30).all():
        if a.id in ja:
            continue
        out.append(_aluno_dict(a))
        if len(out) >= 20:
            break
    return out


class VincularIn(BaseModel):
    aluno_id: int


@router.post("/pacientes/{paciente_id}/vinculo-escolar", status_code=status.HTTP_201_CREATED)
def vincular(
    paciente_id: int,
    body: VincularIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(
        db, paciente_id, current_user, AcaoAuditoria.EDITAR, "vinculo_escolar", None)
    aluno = db.query(Student).filter(Student.id == body.aluno_id, Student.escola_id == p.escola_id).first()
    if not aluno:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aluno nao encontrado nesta escola.")
    # 1:1 por paciente — troca o vinculo se ja existir
    db.query(VinculoAlunoPaciente).filter(VinculoAlunoPaciente.paciente_id == p.id).delete()
    db.add(VinculoAlunoPaciente(
        escola_id=p.escola_id, aluno_id=aluno.id, paciente_id=p.id,
        criado_em=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"vinculado": True, "aluno": _aluno_dict(aluno), "pei": _pei_resumo(db, aluno.id)}


@router.delete("/pacientes/{paciente_id}/vinculo-escolar")
def desvincular(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(
        db, paciente_id, current_user, AcaoAuditoria.EDITAR, "vinculo_escolar", None)
    db.query(VinculoAlunoPaciente).filter(VinculoAlunoPaciente.paciente_id == p.id).delete()
    db.commit()
    return {"vinculado": False}
