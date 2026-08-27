"""
🏥 AdaptAI - Rotas da agenda clinica (vertical CLINICA).

Agendamento de atendimentos + o pulo do gato: "realizar" um agendamento cria a
`Sessao` (migration 012) e devolve o id, emendando na coleta de dados/evolucao.
Gated pelo modulo CLINICA; acesso a paciente pelo guard acesso_clinico.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_core import Especialidade, Paciente, Profissional
from app.models.clinica_terapia import Sessao, Presenca
from app.models.clinica_agenda import Agendamento, StatusAgendamento

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Agenda)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    return datetime.now(timezone.utc)


def _v(e):
    return e.value if hasattr(e, "value") else e


def _dict(a: Agendamento, pac_nome=None, prof_nome=None) -> dict:
    return {
        "id": a.id, "paciente_id": a.paciente_id, "profissional_id": a.profissional_id,
        "paciente_nome": pac_nome, "profissional_nome": prof_nome,
        "especialidade": _v(a.especialidade),
        "inicio": a.inicio.isoformat() if a.inicio else None,
        "duracao_min": a.duracao_min, "status": _v(a.status),
        "local": a.local, "observacao": a.observacao, "sessao_id": a.sessao_id,
    }


def _agend_com_acesso(db, agendamento_id, current_user) -> Agendamento:
    a = db.query(Agendamento).filter(Agendamento.id == agendamento_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agendamento nao encontrado")
    acesso_clinico.verificar_acesso_paciente(db, a.paciente_id, current_user)
    return a


class AgendamentoCriar(BaseModel):
    paciente_id: int
    profissional_id: int
    especialidade: Especialidade
    inicio: datetime
    duracao_min: int = 50
    local: Optional[str] = None
    observacao: Optional[str] = None


class StatusUpdate(BaseModel):
    status: StatusAgendamento


@router.post("/agendamentos", status_code=status.HTTP_201_CREATED)
def criar_agendamento(
    body: AgendamentoCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, body.paciente_id, current_user)
    prof = db.query(Profissional).filter(
        Profissional.id == body.profissional_id, Profissional.escola_id == p.escola_id
    ).first()
    if not prof:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profissional nao encontrado")
    a = Agendamento(
        escola_id=p.escola_id, paciente_id=p.id, profissional_id=prof.id,
        especialidade=body.especialidade, inicio=body.inicio, duracao_min=body.duracao_min,
        status=StatusAgendamento.AGENDADO, local=body.local, observacao=body.observacao,
        criado_por_id=current_user.id, criado_em=_agora(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _dict(a, p.nome, prof.nome)


@router.get("/agendamentos")
def listar_agendamentos(
    de: Optional[datetime] = Query(None, description="inicio do intervalo (ISO)"),
    ate: Optional[datetime] = Query(None, description="fim do intervalo (ISO)"),
    profissional_id: Optional[int] = None,
    paciente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # intervalo padrao: hoje .. +7 dias
    if de is None:
        de = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if ate is None:
        ate = de + timedelta(days=7)

    q = (
        db.query(Agendamento, Paciente.nome, Profissional.nome)
        .join(Paciente, Paciente.id == Agendamento.paciente_id)
        .join(Profissional, Profissional.id == Agendamento.profissional_id)
        .filter(Agendamento.inicio >= de, Agendamento.inicio <= ate)
    )
    if current_user.role != UserRole.SUPER_ADMIN:
        q = q.filter(Agendamento.escola_id == current_user.escola_id)
    if profissional_id:
        q = q.filter(Agendamento.profissional_id == profissional_id)
    if paciente_id:
        q = q.filter(Agendamento.paciente_id == paciente_id)

    return [_dict(a, pn, prn) for (a, pn, prn) in q.order_by(Agendamento.inicio).all()]


@router.patch("/agendamentos/{agendamento_id}/status")
def atualizar_status(
    agendamento_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = _agend_com_acesso(db, agendamento_id, current_user)
    a.status = body.status
    a.atualizado_em = _agora()
    db.commit()
    db.refresh(a)
    return _dict(a)


@router.post("/agendamentos/{agendamento_id}/realizar", status_code=status.HTTP_201_CREATED)
def realizar_agendamento(
    agendamento_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca REALIZADO e cria a Sessao correspondente (emenda no fluxo clinico)."""
    a = _agend_com_acesso(db, agendamento_id, current_user)
    if a.sessao_id:
        return {"agendamento_id": a.id, "sessao_id": a.sessao_id,
                "paciente_id": a.paciente_id, "ja_realizado": True}
    sessao = Sessao(
        escola_id=a.escola_id, paciente_id=a.paciente_id, profissional_id=a.profissional_id,
        especialidade=a.especialidade, data_sessao=a.inicio, duracao_min=a.duracao_min,
        presenca=Presenca.PRESENTE, criado_em=_agora(),
    )
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    a.sessao_id = sessao.id
    a.status = StatusAgendamento.REALIZADO
    a.atualizado_em = _agora()
    db.commit()
    return {"agendamento_id": a.id, "sessao_id": sessao.id, "paciente_id": a.paciente_id}
