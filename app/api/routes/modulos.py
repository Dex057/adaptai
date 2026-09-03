"""
🔎 AdaptAI - Rota de modulos do tenant (para o gate de navegacao do frontend).

NAO e protegida por requer_modulo: o frontend precisa saber QUAIS modulos o
tenant tem para montar a navegacao (um tenant sem CLINICA nem deve ver o menu).
Retorna apenas os nomes dos modulos ativos do tenant do usuario logado.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user, require_admin
from app.models.user import User
from app.core.entitlements import modulos_ativos
from app.models.clinica_core import EscolaModulo, ModuloEscola

router = APIRouter(prefix="/tenant", tags=["🔎 Módulos"])


@router.get("/modulos")
def meus_modulos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Módulos ativos do tenant do usuário logado (para o gate de navegação)."""
    mods = modulos_ativos(db, current_user.escola_id)
    return {"modulos": sorted(m.value for m in mods)}


# ---------------------------------------------------------------------------
# Administração de módulos por tenant (ADMIN / SUPER_ADMIN).
# É o "licenciamento" comercial: liga/desliga ESCOLA/CLINICA/INTELIGENCIA.
# ---------------------------------------------------------------------------
class SetModulo(BaseModel):
    ativo: bool


@router.get("/{escola_id}/modulos")
def modulos_do_tenant(
    escola_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.query(EscolaModulo).filter(EscolaModulo.escola_id == escola_id).all()
    ativos = {r.modulo for r in rows if r.ativo}
    return {
        "escola_id": escola_id,
        "modulos": [
            {"modulo": m.value, "ativo": m in ativos} for m in ModuloEscola
        ],
    }


@router.put("/{escola_id}/modulos/{modulo}")
def set_modulo_tenant(
    escola_id: int,
    modulo: str,
    body: SetModulo,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        m = ModuloEscola(modulo.upper())
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Módulo inválido")

    row = (
        db.query(EscolaModulo)
        .filter(EscolaModulo.escola_id == escola_id, EscolaModulo.modulo == m)
        .first()
    )
    agora = datetime.now(timezone.utc)
    if not row:
        row = EscolaModulo(escola_id=escola_id, modulo=m, ativo=body.ativo,
                           ativado_em=agora if body.ativo else None)
        db.add(row)
    else:
        row.ativo = body.ativo
        if body.ativo:
            row.ativado_em = row.ativado_em or agora
            row.desativado_em = None
        else:
            row.desativado_em = agora
    db.commit()
    return {"escola_id": escola_id, "modulo": m.value, "ativo": body.ativo}
