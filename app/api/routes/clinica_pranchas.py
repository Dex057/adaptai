"""
🏥 AdaptAI - Rotas de CAA (pranchas de comunicação) - vertical CLINICA.

Monta pranchas/rotinas com pictogramas ARASAAC (reusa pictograma_service).
Gated pelo módulo CLINICA. Acesso por escopo de tenant (escola).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.core.entitlements import requer_modulo, Modulo
from app.services.pictograma_service import buscar_pictogramas, url_pictograma
from app.services import acesso_clinico
from app.services import historia_social_service
from app.models.clinica_caa import Prancha, PranchaItem, TipoPrancha

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (CAA)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _v(e):
    return e.value if hasattr(e, "value") else e


def _prancha_com_acesso(db, prancha_id, current_user) -> Prancha:
    pr = db.query(Prancha).filter(Prancha.id == prancha_id).first()
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prancha não encontrada")
    if current_user.role != UserRole.SUPER_ADMIN and pr.escola_id != current_user.escola_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prancha não encontrada")
    return pr


def _prancha_dict(pr: Prancha, itens=None) -> dict:
    d = {"id": pr.id, "titulo": pr.titulo, "tipo": _v(pr.tipo),
         "paciente_id": pr.paciente_id}
    if itens is not None:
        d["itens"] = [
            {"id": it.id, "ordem": it.ordem, "arasaac_id": it.arasaac_id,
             "imagem_url": it.imagem_url, "rotulo": it.rotulo}
            for it in itens
        ]
    return d


# ---------------------------------------------------------------------------
# Busca de pictogramas (proxy ARASAAC)
# ---------------------------------------------------------------------------
@router.get("/pictogramas")
def buscar(termo: str = Query(..., min_length=1), idioma: str = "pt"):
    resultados = buscar_pictogramas(termo, idioma=idioma)
    return {"termo": termo, "total": len(resultados), "pictogramas": resultados}


class HistoriaGerar(BaseModel):
    tema: str = Field(..., min_length=1)


@router.post("/historias-sociais/gerar")
def gerar_historia_social(body: HistoriaGerar):
    """IA escreve a história social (frases) e o backend resolve 1 pictograma
    ARASAAC por frase. NÃO persiste — o profissional revisa e cria a prancha."""
    dados = historia_social_service.gerar_historia(body.tema)
    frases = []
    for f in dados.get("frases", []):
        termo = f.get("termo") or ""
        arasaac_id, imagem_url = None, None
        if termo:
            achados = buscar_pictogramas(termo, limite=1)
            if achados:
                arasaac_id = achados[0].get("arasaac_id")
                imagem_url = achados[0].get("url") or (url_pictograma(arasaac_id) if arasaac_id else None)
        frases.append({"texto": f.get("texto"), "termo": termo,
                       "arasaac_id": arasaac_id, "imagem_url": imagem_url})
    return {"titulo": dados.get("titulo", ""), "frases": frases}


# ---------------------------------------------------------------------------
# Pranchas
# ---------------------------------------------------------------------------
class PranchaCriar(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    tipo: TipoPrancha = TipoPrancha.COMUNICACAO
    paciente_id: Optional[int] = None


@router.post("/pranchas", status_code=status.HTTP_201_CREATED)
def criar_prancha(
    body: PranchaCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.escola_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuário sem clínica vinculada.")
    if body.paciente_id:
        acesso_clinico.verificar_acesso_paciente(db, body.paciente_id, current_user)
    pr = Prancha(
        escola_id=current_user.escola_id,
        paciente_id=body.paciente_id,
        titulo=body.titulo,
        tipo=body.tipo,
        criado_por_id=current_user.id,
        criado_em=_agora(),
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return _prancha_dict(pr)


@router.get("/pranchas")
def listar_pranchas(
    paciente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Prancha)
    if current_user.role != UserRole.SUPER_ADMIN:
        q = q.filter(Prancha.escola_id == current_user.escola_id)
    if paciente_id is not None:
        q = q.filter(Prancha.paciente_id == paciente_id)
    return [_prancha_dict(pr) for pr in q.order_by(Prancha.id.desc()).all()]


@router.get("/pranchas/{prancha_id}")
def obter_prancha(
    prancha_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pr = _prancha_com_acesso(db, prancha_id, current_user)
    itens = db.query(PranchaItem).filter(
        PranchaItem.prancha_id == pr.id
    ).order_by(PranchaItem.ordem, PranchaItem.id).all()
    return _prancha_dict(pr, itens)


# ---------------------------------------------------------------------------
# Itens da prancha
# ---------------------------------------------------------------------------
class ItemCriar(BaseModel):
    rotulo: str = Field(..., min_length=1, max_length=255)
    arasaac_id: Optional[int] = None
    imagem_url: Optional[str] = None


@router.post("/pranchas/{prancha_id}/itens", status_code=status.HTTP_201_CREATED)
def adicionar_item(
    prancha_id: int,
    body: ItemCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pr = _prancha_com_acesso(db, prancha_id, current_user)
    # próxima ordem
    ultima = db.query(PranchaItem).filter(
        PranchaItem.prancha_id == pr.id
    ).order_by(PranchaItem.ordem.desc()).first()
    ordem = (ultima.ordem + 1) if ultima else 0
    url = body.imagem_url or (url_pictograma(body.arasaac_id) if body.arasaac_id else None)
    it = PranchaItem(
        prancha_id=pr.id, ordem=ordem, arasaac_id=body.arasaac_id,
        imagem_url=url, rotulo=body.rotulo, criado_em=_agora(),
    )
    db.add(it)
    db.commit()
    db.refresh(it)
    return {"id": it.id, "ordem": it.ordem, "arasaac_id": it.arasaac_id,
            "imagem_url": it.imagem_url, "rotulo": it.rotulo}


@router.delete("/pranchas/{prancha_id}/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_item(
    prancha_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pr = _prancha_com_acesso(db, prancha_id, current_user)
    it = db.query(PranchaItem).filter(
        PranchaItem.id == item_id, PranchaItem.prancha_id == pr.id
    ).first()
    if it:
        db.delete(it)
        db.commit()
    return None
