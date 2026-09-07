"""
📚 AdaptAI - Rotas da Biblioteca de Estrategias de Adaptacao.

Base curada (transtorno -> diretrizes) que a equipe edita e os geradores
consultam. Escopo: estrategias base (escola_id NULL, so super_admin edita) +
estrategias da propria escola (admin/coordenador da escola editam).
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.estrategia_adaptacao import EstrategiaAdaptacao
from app.services import estrategias_service

router = APIRouter(prefix="/estrategias-adaptacao", tags=["📚 Estratégias de Adaptação"])


def _is_admin(u: User) -> bool:
    return u.role in (UserRole.ADMIN, UserRole.COORDINATOR, UserRole.SUPER_ADMIN)


def _is_super(u: User) -> bool:
    return u.role == UserRole.SUPER_ADMIN


def _serializar(e: EstrategiaAdaptacao) -> dict:
    return {
        "id": e.id,
        "escola_id": e.escola_id,
        "global": e.escola_id is None,
        "transtorno": e.transtorno,
        "cid": e.cid,
        "titulo": e.titulo,
        "diretrizes": e.diretrizes,
        "fonte": e.fonte,
        "ativo": bool(e.ativo),
        "ordem": e.ordem,
        "atualizado_em": str(e.atualizado_em) if e.atualizado_em else None,
    }


class EstrategiaIn(BaseModel):
    transtorno: str = Field(..., max_length=60)
    diretrizes: str
    titulo: Optional[str] = Field(None, max_length=200)
    cid: Optional[str] = Field(None, max_length=100)
    fonte: Optional[str] = Field(None, max_length=500)
    ativo: bool = True
    ordem: int = 100
    # super_admin pode marcar como base global (escola_id = NULL)
    is_global: bool = False


@router.get("")
def listar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Base global + estrategias da escola do usuario."""
    q = db.query(EstrategiaAdaptacao).filter(
        (EstrategiaAdaptacao.escola_id.is_(None))
        | (EstrategiaAdaptacao.escola_id == current_user.escola_id)
    )
    itens = q.order_by(EstrategiaAdaptacao.transtorno, EstrategiaAdaptacao.ordem).all()
    return {"total": len(itens), "estrategias": [_serializar(e) for e in itens]}


@router.post("/seed")
def semear(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Semeia as estrategias-base globais (idempotente). Somente super_admin."""
    if not _is_super(current_user):
        raise HTTPException(status_code=403, detail="Apenas super admin pode semear a base global.")
    n = estrategias_service.seed(db)
    return {"inseridas": n}


@router.post("", status_code=status.HTTP_201_CREATED)
def criar(body: EstrategiaIn, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para editar estrategias.")
    if body.is_global and not _is_super(current_user):
        raise HTTPException(status_code=403, detail="Apenas super admin cria estrategia base global.")
    escola_id = None if body.is_global else current_user.escola_id
    e = EstrategiaAdaptacao(
        escola_id=escola_id, transtorno=body.transtorno.strip().lower(),
        cid=body.cid, titulo=body.titulo, diretrizes=body.diretrizes,
        fonte=body.fonte, ativo=body.ativo, ordem=body.ordem,
        criado_por_id=current_user.id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _serializar(e)


def _pode_editar(e: EstrategiaAdaptacao, u: User) -> bool:
    if e.escola_id is None:
        return _is_super(u)              # base global: so super
    return _is_admin(u) and e.escola_id == u.escola_id


@router.put("/{estrategia_id}")
def atualizar(estrategia_id: int, body: EstrategiaIn, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    e = db.query(EstrategiaAdaptacao).filter(EstrategiaAdaptacao.id == estrategia_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Estrategia nao encontrada.")
    if not _pode_editar(e, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para editar esta estrategia.")
    e.transtorno = body.transtorno.strip().lower()
    e.cid = body.cid
    e.titulo = body.titulo
    e.diretrizes = body.diretrizes
    e.fonte = body.fonte
    e.ativo = body.ativo
    e.ordem = body.ordem
    db.commit()
    db.refresh(e)
    return _serializar(e)


@router.delete("/{estrategia_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(estrategia_id: int, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    e = db.query(EstrategiaAdaptacao).filter(EstrategiaAdaptacao.id == estrategia_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Estrategia nao encontrada.")
    if not _pode_editar(e, current_user):
        raise HTTPException(status_code=403, detail="Sem permissao para remover esta estrategia.")
    db.delete(e)
    db.commit()
    return None
