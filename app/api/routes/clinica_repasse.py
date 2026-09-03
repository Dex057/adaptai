"""
🏥 AdaptAI - Rotas de repasse ao profissional (vertical CLINICA).

Fecha por competencia (mes) quanto cada profissional recebe: base = faturado das
sessoes dele no mes; repasse = base * percentual do contrato. Gate CLINICA;
escopo por escola do usuario.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.models.clinica_core import Profissional
from app.models.clinica_terapia import Sessao
from app.models.clinica_faturamento import Faturamento
from app.models.clinica_repasse import Repasse

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Repasse)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    return datetime.now(timezone.utc)


def _escola_id(current_user: User) -> int:
    if not current_user.escola_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuario sem escola vinculada.")
    return current_user.escola_id


def _percentual(prof: Profissional) -> float:
    p = getattr(prof, "percentual_repasse", None)
    return float(p) if p is not None else 0.0


def _base_por_profissional(db: Session, escola_id: int, competencia: str) -> dict:
    rows = (
        db.query(Sessao.profissional_id, func.coalesce(func.sum(Faturamento.valor), 0))
        .join(Faturamento, Faturamento.sessao_id == Sessao.id)
        .filter(Faturamento.escola_id == escola_id, Faturamento.competencia == competencia)
        .group_by(Sessao.profissional_id)
        .all()
    )
    return {pid: float(total) for pid, total in rows if pid is not None}


@router.get("/repasses/preview")
def preview_repasse(
    competencia: str = Query(..., description="mes de referencia 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eid = _escola_id(current_user)
    bases = _base_por_profissional(db, eid, competencia)
    profs = db.query(Profissional).filter(Profissional.escola_id == eid).all()
    ja = {r.profissional_id for r in db.query(Repasse).filter(
        Repasse.escola_id == eid, Repasse.competencia == competencia).all()}
    itens = []
    for pr in profs:
        base = bases.get(pr.id, 0.0)
        if base <= 0 and pr.id not in ja:
            continue
        perc = _percentual(pr)
        itens.append({
            "profissional_id": pr.id,
            "profissional_nome": pr.nome,
            "percentual": perc,
            "valor_base": round(base, 2),
            "valor_repasse": round(base * perc / 100.0, 2),
            "ja_gerado": pr.id in ja,
        })
    total_base = round(sum(i["valor_base"] for i in itens), 2)
    total_rep = round(sum(i["valor_repasse"] for i in itens), 2)
    return {"competencia": competencia, "itens": itens, "total_base": total_base, "total_repasse": total_rep}


@router.post("/repasses/gerar")
def gerar_repasse(
    competencia: str = Query(..., description="mes de referencia 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eid = _escola_id(current_user)
    bases = _base_por_profissional(db, eid, competencia)
    profs = {p.id: p for p in db.query(Profissional).filter(Profissional.escola_id == eid).all()}
    n = 0
    for pid, base in bases.items():
        if base <= 0:
            continue
        pr = profs.get(pid)
        if not pr:
            continue
        perc = _percentual(pr)
        valor = round(base * perc / 100.0, 2)
        r = db.query(Repasse).filter(
            Repasse.escola_id == eid, Repasse.profissional_id == pid, Repasse.competencia == competencia
        ).first()
        if r:
            if r.status != "PAGO":
                r.valor_base = base
                r.percentual = perc
                r.valor_repasse = valor
        else:
            db.add(Repasse(
                escola_id=eid, profissional_id=pid, competencia=competencia,
                valor_base=base, percentual=perc, valor_repasse=valor,
                status="PENDENTE", criado_em=_agora(),
            ))
        n += 1
    db.commit()
    return {"competencia": competencia, "gerados": n}


@router.get("/repasses")
def listar_repasses(
    competencia: str = Query(..., description="mes de referencia 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eid = _escola_id(current_user)
    rows = (
        db.query(Repasse, Profissional.nome)
        .join(Profissional, Profissional.id == Repasse.profissional_id)
        .filter(Repasse.escola_id == eid, Repasse.competencia == competencia)
        .order_by(Profissional.nome)
        .all()
    )
    return [{
        "id": r.id, "profissional_id": r.profissional_id, "profissional_nome": nome,
        "competencia": r.competencia, "valor_base": float(r.valor_base or 0),
        "percentual": float(r.percentual or 0), "valor_repasse": float(r.valor_repasse or 0),
        "status": r.status, "pago_em": r.pago_em.isoformat() if r.pago_em else None,
        "observacao": r.observacao,
    } for (r, nome) in rows]


class RepasseUpdate(BaseModel):
    status: Optional[str] = None
    observacao: Optional[str] = None


@router.patch("/repasses/{repasse_id}")
def atualizar_repasse(
    repasse_id: int,
    body: RepasseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eid = _escola_id(current_user)
    r = db.query(Repasse).filter(Repasse.id == repasse_id, Repasse.escola_id == eid).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repasse nao encontrado.")
    if body.status is not None:
        if body.status not in ("PENDENTE", "PAGO"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status invalido (PENDENTE/PAGO).")
        r.status = body.status
        r.pago_em = _agora() if body.status == "PAGO" else None
    if body.observacao is not None:
        r.observacao = body.observacao
    db.commit()
    db.refresh(r)
    return {"id": r.id, "status": r.status, "pago_em": r.pago_em.isoformat() if r.pago_em else None}


class PercentualIn(BaseModel):
    percentual: float


@router.patch("/profissionais/{profissional_id}/percentual")
def definir_percentual(
    profissional_id: int,
    body: PercentualIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    eid = _escola_id(current_user)
    pr = db.query(Profissional).filter(Profissional.id == profissional_id, Profissional.escola_id == eid).first()
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profissional nao encontrado.")
    if body.percentual < 0 or body.percentual > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "percentual deve estar entre 0 e 100.")
    pr.percentual_repasse = body.percentual
    db.commit()
    return {"id": pr.id, "percentual_repasse": float(pr.percentual_repasse)}
