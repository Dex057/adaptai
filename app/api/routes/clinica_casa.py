"""
🏥 AdaptAI - Rotas do programa de casa (lado terapeuta) - vertical CLINICA.

O terapeuta define tarefas de generalizacao para o paciente; a familia marca
pelo portal (ver familia.py). Gated CLINICA; acesso por paciente (equipe do caso).
"""
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_casa import TarefaCasa, TarefaCasaCheck

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Programa de casa)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    return datetime.now(timezone.utc)


def _tarefa_com_acesso(db, tarefa_id, current_user) -> TarefaCasa:
    t = db.query(TarefaCasa).filter(TarefaCasa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa nao encontrada")
    acesso_clinico.verificar_acesso_paciente(db, t.paciente_id, current_user)
    return t


class TarefaCriar(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    descricao: Optional[str] = None


class TarefaEditar(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None


@router.post("/pacientes/{paciente_id}/tarefas-casa", status_code=status.HTTP_201_CREATED)
def criar_tarefa(
    paciente_id: int,
    body: TarefaCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    t = TarefaCasa(
        escola_id=p.escola_id, paciente_id=p.id, titulo=body.titulo,
        descricao=body.descricao, ativo=True, criado_por_id=current_user.id,
        criado_em=_agora(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "titulo": t.titulo, "descricao": t.descricao, "ativo": t.ativo}


@router.get("/pacientes/{paciente_id}/tarefas-casa")
def listar_tarefas(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    tarefas = db.query(TarefaCasa).filter(TarefaCasa.paciente_id == p.id).order_by(TarefaCasa.id.desc()).all()
    # feitos nos ultimos 7 dias, por tarefa
    d7 = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    feitos = dict(
        db.query(TarefaCasaCheck.tarefa_id, func.count(TarefaCasaCheck.id))
        .filter(TarefaCasaCheck.data >= d7, TarefaCasaCheck.feito.is_(True),
                TarefaCasaCheck.tarefa_id.in_([t.id for t in tarefas] or [0]))
        .group_by(TarefaCasaCheck.tarefa_id).all()
    )
    return [{
        "id": t.id, "titulo": t.titulo, "descricao": t.descricao, "ativo": t.ativo,
        "feitos_7d": feitos.get(t.id, 0),
    } for t in tarefas]


@router.patch("/tarefas-casa/{tarefa_id}")
def editar_tarefa(
    tarefa_id: int,
    body: TarefaEditar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = _tarefa_com_acesso(db, tarefa_id, current_user)
    if body.titulo is not None:
        t.titulo = body.titulo
    if body.descricao is not None:
        t.descricao = body.descricao
    if body.ativo is not None:
        t.ativo = body.ativo
    t.atualizado_em = _agora()
    db.commit()
    return {"id": t.id, "titulo": t.titulo, "descricao": t.descricao, "ativo": t.ativo}


@router.delete("/tarefas-casa/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = _tarefa_com_acesso(db, tarefa_id, current_user)
    db.delete(t)
    db.commit()
    return None
