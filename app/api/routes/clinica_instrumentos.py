"""
🏥 AdaptAI - Rotas de aplicacao de instrumentos padronizados (vertical CLINICA).

Gated CLINICA; acesso por paciente (equipe do caso).
"""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_instrumentos import AplicacaoInstrumento

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Instrumentos)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _num(v):
    return float(v) if v is not None else None


def _dict(a: AplicacaoInstrumento) -> dict:
    return {
        "id": a.id, "instrumento": a.instrumento,
        "data": str(a.data) if a.data else None,
        "pontuacao": _num(a.pontuacao), "pontuacao_max": _num(a.pontuacao_max),
        "observacao": a.observacao,
    }


class InstrumentoCriar(BaseModel):
    instrumento: str = Field(..., min_length=1, max_length=120)
    data: Optional[date] = None
    pontuacao: Optional[float] = None
    pontuacao_max: Optional[float] = None
    observacao: Optional[str] = None


@router.post("/pacientes/{paciente_id}/instrumentos", status_code=status.HTTP_201_CREATED)
def criar_aplicacao(
    paciente_id: int,
    body: InstrumentoCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    a = AplicacaoInstrumento(
        escola_id=p.escola_id, paciente_id=p.id, instrumento=body.instrumento,
        data=body.data or datetime.now(timezone.utc).date(),
        pontuacao=body.pontuacao, pontuacao_max=body.pontuacao_max,
        observacao=body.observacao, criado_por_id=current_user.id,
        criado_em=datetime.now(timezone.utc),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _dict(a)


@router.get("/pacientes/{paciente_id}/instrumentos")
def listar_aplicacoes(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    regs = (db.query(AplicacaoInstrumento)
            .filter(AplicacaoInstrumento.paciente_id == p.id)
            .order_by(AplicacaoInstrumento.data.desc(), AplicacaoInstrumento.id.desc())
            .limit(200).all())
    return [_dict(a) for a in regs]
