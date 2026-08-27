"""
app/core/entitlements.py — Licenciamento por modulo (entitlements) do ADAPT AI.

E a peca que permite vender "so Clinica", "so Escola" ou as duas juntas, sem
"ifs" espalhados pelo codigo. Cada tenant (uma `escola`) tem um conjunto de
modulos ativos na tabela `escola_modulos` (migration 011).

Tres camadas, do grosso ao fino — NAO confundir:
  1. ENTITLEMENT (aqui)         -> o tenant TEM DIREITO ao modulo. Comercial.
  2. PLANO/ASSINATURA (tenant.py) -> limites de uso e capacidades do plano.
  3. FEATURE FLAG (core/features.py) -> nome canonico de feature de custo de IA,
     DENTRO de um modulo.

Uso tipico — proteger um vertical inteiro:

    # app/api/routes/clinica.py  (ou o futuro app/clinica/api/__init__.py)
    from fastapi import APIRouter, Depends
    from app.core.entitlements import requer_modulo, Modulo

    router = APIRouter(
        dependencies=[Depends(requer_modulo(Modulo.CLINICA))],  # 403 se nao licenciado
    )

Integra-se ao multi-tenant existente: usa `get_tenant_context` para descobrir o
`escola_id` da requisicao — a mesma dependency que as rotas ja usam.
"""

from __future__ import annotations

from enum import Enum

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.tenant import get_tenant_context, TenantContext


class Modulo(str, Enum):
    ESCOLA = "ESCOLA"
    CLINICA = "CLINICA"
    INTELIGENCIA = "INTELIGENCIA"


def modulos_ativos(db: Session, escola_id: int | None) -> set[Modulo]:
    """Modulos que o tenant tem ativos agora. Query barata e indexada."""
    if not escola_id:
        return set()
    rows = db.execute(
        text(
            "SELECT modulo FROM escola_modulos "
            "WHERE escola_id = :eid AND ativo = 1"
        ),
        {"eid": escola_id},
    ).all()
    return {Modulo(r[0]) for r in rows}


def escola_tem_modulo(db: Session, escola_id: int | None, modulo: Modulo) -> bool:
    return modulo in modulos_ativos(db, escola_id)


def requer_modulo(modulo: Modulo):
    """
    Dependency de rota: barra com 403 se o tenant nao tiver o modulo licenciado.
    Coloque em `dependencies=[...]` do APIRouter do vertical.
    """

    def _guard(
        db: Session = Depends(get_db),
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> None:
        if not escola_tem_modulo(db, tenant.escola_id, modulo):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Modulo {modulo.value} nao licenciado para este tenant.",
            )

    return _guard


# Conveniencia p/ o frontend: um endpoint pode expor os modulos do tenant atual
# para o gate de navegacao (ver shared/useModulos.js). Ex. de uso numa rota:
#
#   @router.get("/tenant/modulos")
#   def listar_modulos(db=Depends(get_db), tenant=Depends(get_tenant_context)):
#       return {"modulos": sorted(m.value for m in modulos_ativos(db, tenant.escola_id))}
