"""
🏥 AdaptAI - Rotas de faturamento/convenios (vertical CLINICA).

Gated CLINICA. Convenios sao por tenant (escola). Itens de faturamento sao por
paciente (acesso via equipe do caso, anti-IDOR). Resumo agrega por competencia.

Escopo: MVP de gestao financeira — cadastro de fontes pagadoras, lancamento de
itens faturaveis por mes e acompanhamento do status (a faturar/faturado/pago/
glosado). Nao emite guia TISS nem integra com operadora nesta fase.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_faturamento import (
    Convenio, Faturamento, TipoConvenio, StatusFaturamento, PrecoEspecialidade,
)
from app.models.clinica_core import Especialidade, Paciente

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Faturamento)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    return datetime.now(timezone.utc)


def _num(v):
    return float(v) if v is not None else 0.0


def _escola_id(current_user: User) -> int:
    if not current_user.escola_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Usuario sem clinica vinculada.")
    return current_user.escola_id


def _escopo_conv(q, current_user: User):
    if current_user.role == UserRole.SUPER_ADMIN:
        return q
    return q.filter(Convenio.escola_id == current_user.escola_id)


# ============================================================================
# Convenios (fontes pagadoras) — por tenant
# ============================================================================
def _convenio_dict(c: Convenio) -> dict:
    return {
        "id": c.id, "nome": c.nome,
        "tipo": c.tipo.value if hasattr(c.tipo, "value") else c.tipo,
        "registro_ans": c.registro_ans, "ativo": bool(c.ativo),
    }


class ConvenioCriar(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    tipo: TipoConvenio = TipoConvenio.CONVENIO
    registro_ans: Optional[str] = Field(None, max_length=60)


class ConvenioEditar(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=200)
    ativo: Optional[bool] = None
    registro_ans: Optional[str] = Field(None, max_length=60)


@router.get("/convenios")
def listar_convenios(
    incluir_inativos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _escopo_conv(db.query(Convenio), current_user)
    if not incluir_inativos:
        q = q.filter(Convenio.ativo.is_(True))
    convs = q.order_by(Convenio.nome).all()
    return [_convenio_dict(c) for c in convs]


@router.post("/convenios", status_code=status.HTTP_201_CREATED)
def criar_convenio(
    body: ConvenioCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = Convenio(
        escola_id=_escola_id(current_user),
        nome=body.nome.strip(), tipo=body.tipo,
        registro_ans=body.registro_ans, ativo=True, criado_em=_agora(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _convenio_dict(c)


@router.patch("/convenios/{convenio_id}")
def editar_convenio(
    convenio_id: int,
    body: ConvenioEditar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = _escopo_conv(db.query(Convenio).filter(Convenio.id == convenio_id), current_user).first()
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convenio nao encontrado")
    if body.nome is not None:
        c.nome = body.nome.strip()
    if body.ativo is not None:
        c.ativo = body.ativo
    if body.registro_ans is not None:
        c.registro_ans = body.registro_ans
    db.commit()
    db.refresh(c)
    return _convenio_dict(c)


# ============================================================================
# Faturamento — itens por paciente
# ============================================================================
def _faturamento_dict(f: Faturamento) -> dict:
    return {
        "id": f.id, "paciente_id": f.paciente_id, "sessao_id": f.sessao_id,
        "convenio_id": f.convenio_id, "competencia": f.competencia,
        "valor": _num(f.valor),
        "status": f.status.value if hasattr(f.status, "value") else f.status,
        "observacao": f.observacao,
        "criado_em": str(f.criado_em) if f.criado_em else None,
    }


def _competencia_valida(v: str) -> bool:
    try:
        datetime.strptime(v, "%Y-%m")
        return True
    except (ValueError, TypeError):
        return False


class FaturamentoCriar(BaseModel):
    competencia: str = Field(..., description="mes de referencia 'YYYY-MM'")
    valor: float = Field(..., ge=0)
    convenio_id: Optional[int] = None
    sessao_id: Optional[int] = None
    observacao: Optional[str] = Field(None, max_length=255)


class FaturamentoStatus(BaseModel):
    status: StatusFaturamento


@router.get("/pacientes/{paciente_id}/faturamentos")
def listar_faturamentos_paciente(
    paciente_id: int,
    competencia: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    q = db.query(Faturamento).filter(Faturamento.paciente_id == p.id)
    if competencia:
        if not _competencia_valida(competencia):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "competencia deve ser 'YYYY-MM'")
        q = q.filter(Faturamento.competencia == competencia)
    itens = q.order_by(Faturamento.competencia.desc(), Faturamento.id.desc()).limit(300).all()
    return [_faturamento_dict(f) for f in itens]


@router.post("/pacientes/{paciente_id}/faturamentos", status_code=status.HTTP_201_CREATED)
def criar_faturamento(
    paciente_id: int,
    body: FaturamentoCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _competencia_valida(body.competencia):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "competencia deve ser 'YYYY-MM'")
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    # convenio (se informado) tem que ser do mesmo tenant
    if body.convenio_id is not None:
        conv = _escopo_conv(db.query(Convenio).filter(Convenio.id == body.convenio_id), current_user).first()
        if not conv:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Convenio nao encontrado")
    try:
        valor = Decimal(str(body.valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "valor invalido")
    f = Faturamento(
        escola_id=p.escola_id, paciente_id=p.id,
        sessao_id=body.sessao_id, convenio_id=body.convenio_id,
        competencia=body.competencia, valor=valor,
        status=StatusFaturamento.A_FATURAR, observacao=body.observacao,
        criado_por_id=current_user.id, criado_em=_agora(),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return _faturamento_dict(f)


@router.patch("/faturamentos/{faturamento_id}/status")
def mudar_status_faturamento(
    faturamento_id: int,
    body: FaturamentoStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f = db.query(Faturamento).filter(Faturamento.id == faturamento_id).first()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Faturamento nao encontrado")
    # acesso via paciente dono (anti-IDOR) + auditoria
    acesso_clinico.verificar_acesso_paciente(db, f.paciente_id, current_user)
    f.status = body.status
    db.commit()
    db.refresh(f)
    return _faturamento_dict(f)


# ============================================================================
# Resumo por competencia (agrega o tenant inteiro)
# ============================================================================
@router.get("/faturamento/itens")
def listar_itens_mes(
    competencia: str = Query(..., description="mes 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista os itens de faturamento do tenant na competencia (com nome do paciente)."""
    if not _competencia_valida(competencia):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "competencia deve ser 'YYYY-MM'")
    is_super = current_user.role == UserRole.SUPER_ADMIN
    escola_id = current_user.escola_id
    q = (db.query(Faturamento, Paciente.nome)
         .outerjoin(Paciente, Paciente.id == Faturamento.paciente_id)
         .filter(Faturamento.competencia == competencia))
    if not is_super:
        q = q.filter(Faturamento.escola_id == escola_id)
    itens = q.order_by(Faturamento.id.desc()).limit(500).all()
    return [{
        "id": f.id, "paciente_id": f.paciente_id, "paciente_nome": nome,
        "valor": _num(f.valor),
        "status": f.status.value if hasattr(f.status, "value") else f.status,
        "convenio_id": f.convenio_id, "observacao": f.observacao,
        "sessao_id": f.sessao_id, "competencia": f.competencia,
    } for f, nome in itens]


@router.get("/faturamento/resumo")
def resumo_faturamento(
    competencia: str = Query(..., description="mes 'YYYY-MM'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _competencia_valida(competencia):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "competencia deve ser 'YYYY-MM'")
    is_super = current_user.role == UserRole.SUPER_ADMIN
    escola_id = current_user.escola_id

    def escopo(q):
        return q if is_super else q.filter(Faturamento.escola_id == escola_id)

    base = escopo(db.query(Faturamento).filter(Faturamento.competencia == competencia))

    por_status = {s.value: {"quantidade": 0, "valor": 0.0} for s in StatusFaturamento}
    q_status = (escopo(db.query(
        Faturamento.status, func.count(Faturamento.id), func.coalesce(func.sum(Faturamento.valor), 0))
        .filter(Faturamento.competencia == competencia))
        .group_by(Faturamento.status))
    for st, qtd, val in q_status.all():
        key = st.value if hasattr(st, "value") else st
        por_status[key] = {"quantidade": int(qtd), "valor": _num(val)}

    total_valor = sum(v["valor"] for v in por_status.values())
    total_qtd = sum(v["quantidade"] for v in por_status.values())
    # o que ainda nao entrou (a faturar + faturado + glosado) x recebido (pago)
    recebido = por_status[StatusFaturamento.PAGO.value]["valor"]
    a_receber = total_valor - recebido

    return {
        "competencia": competencia,
        "total": {"quantidade": total_qtd, "valor": round(total_valor, 2)},
        "recebido": round(recebido, 2),
        "a_receber": round(a_receber, 2),
        "por_status": por_status,
    }


# ============================================================================
# Precos por especialidade (base do faturamento por sessao)
# ============================================================================
class PrecoSet(BaseModel):
    valor: float = Field(..., ge=0)


@router.get("/precos")
def listar_precos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista TODAS as especialidades com o valor configurado (0 se nao definido)."""
    escola_id = _escola_id(current_user)
    rows = {p.especialidade: p.valor for p in db.query(PrecoEspecialidade)
            .filter(PrecoEspecialidade.escola_id == escola_id).all()}
    return [
        {"especialidade": e.value, "valor": _num(rows.get(e, 0))}
        for e in Especialidade
    ]


@router.put("/precos/{especialidade}")
def definir_preco(
    especialidade: Especialidade,
    body: PrecoSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    escola_id = _escola_id(current_user)
    try:
        valor = Decimal(str(body.valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "valor invalido")
    row = (db.query(PrecoEspecialidade)
           .filter(PrecoEspecialidade.escola_id == escola_id,
                   PrecoEspecialidade.especialidade == especialidade).first())
    if row:
        row.valor = valor
    else:
        db.add(PrecoEspecialidade(escola_id=escola_id, especialidade=especialidade, valor=valor))
    db.commit()
    return {"especialidade": especialidade.value, "valor": float(valor)}
