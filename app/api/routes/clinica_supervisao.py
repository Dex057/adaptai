"""
🏥 AdaptAI - Supervisao & qualidade ABA (vertical CLINICA).

- Aprovacao/assinatura do PTI (supervisor): sha256 do plano, mesmo padrao da
  assinatura de evolucao ("IA rascunha, humano assina; supervisor aprova").
- Fidelidade de aplicacao: checklist por sessao (% aplicado).
- IOA: concordancia entre observadores por sessao.
Gate CLINICA; acesso pelo guard clinico. Aprovar exige papel de supervisao.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User, UserRole
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_core import AcaoAuditoria, PapelProfissional
from app.models.clinica_terapia import PlanoTerapeutico, StatusPlanoTerapeutico, Sessao
from app.models.clinica_supervisao import FidelidadeAplicacao, IOARegistro

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Supervisão)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)

_PAPEIS_SUPERVISAO = {
    PapelProfissional.SUPERVISOR,
    PapelProfissional.RESPONSAVEL_TECNICO,
    PapelProfissional.COORDENADOR,
    PapelProfissional.ADMIN_CLINICA,
}


def _agora():
    return datetime.now(timezone.utc)


def _exigir_supervisor(db: Session, current_user: User, escola_id: int):
    if current_user.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.COORDINATOR):
        return
    prof = acesso_clinico.profissional_do_usuario(db, current_user, escola_id)
    if prof and prof.papel in _PAPEIS_SUPERVISAO:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas supervisor/coordenador pode aprovar o PTI.")


# ---------------------------------------------------------------- PTI: aprovar
def _hash_plano(pl: PlanoTerapeutico) -> str:
    base = "%s|%s|%s|%s" % (
        pl.id, pl.titulo or "", pl.aprovado_por_id or "",
        pl.aprovado_em.isoformat() if pl.aprovado_em else "",
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _aprovacao_dict(pl: PlanoTerapeutico, hash_valido=None) -> dict:
    v = pl.status.value if hasattr(pl.status, "value") else pl.status
    return {
        "plano_id": pl.id, "titulo": pl.titulo, "status": v,
        "aprovado": pl.aprovado_em is not None,
        "aprovado_por_id": pl.aprovado_por_id,
        "aprovado_em": str(pl.aprovado_em) if pl.aprovado_em else None,
        "assinatura_hash": pl.assinatura_hash,
        "revisao_nota": pl.revisao_nota,
        "hash_valido": hash_valido,
    }


def _get_plano(db, plano_id, current_user, escrever=False):
    pl = db.query(PlanoTerapeutico).filter(PlanoTerapeutico.id == plano_id).first()
    if not pl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PTI nao encontrado.")
    acao = AcaoAuditoria.EDITAR if escrever else None
    acesso_clinico.verificar_acesso_paciente(db, pl.paciente_id, current_user, acao, "plano", pl.id)
    return pl


@router.post("/planos/{plano_id}/aprovar")
def aprovar_plano(plano_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pl = _get_plano(db, plano_id, current_user, escrever=True)
    _exigir_supervisor(db, current_user, pl.escola_id)
    if pl.aprovado_em is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "PTI ja aprovado.")
    pl.aprovado_por_id = current_user.id
    pl.aprovado_em = _agora()
    pl.assinatura_hash = _hash_plano(pl)
    pl.revisao_nota = None
    pl.status = StatusPlanoTerapeutico.ATIVO
    db.commit()
    db.refresh(pl)
    return _aprovacao_dict(pl, True)


class RevisaoIn(BaseModel):
    nota: Optional[str] = None


@router.post("/planos/{plano_id}/solicitar-revisao")
def solicitar_revisao(plano_id: int, body: RevisaoIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pl = _get_plano(db, plano_id, current_user, escrever=True)
    _exigir_supervisor(db, current_user, pl.escola_id)
    pl.status = StatusPlanoTerapeutico.EM_REVISAO
    pl.revisao_nota = body.nota
    pl.aprovado_por_id = None
    pl.aprovado_em = None
    pl.assinatura_hash = None
    db.commit()
    db.refresh(pl)
    return _aprovacao_dict(pl)


@router.get("/planos/{plano_id}/aprovacao")
def status_aprovacao(plano_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pl = _get_plano(db, plano_id, current_user)
    valido = bool(pl.aprovado_em and pl.assinatura_hash and _hash_plano(pl) == pl.assinatura_hash)
    return _aprovacao_dict(pl, valido)


# ---------------------------------------------------------- fidelidade / sessao
def _get_sessao(db, sessao_id, current_user, acao=None):
    s = db.query(Sessao).filter(Sessao.id == sessao_id).first()
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessao nao encontrada.")
    acesso_clinico.verificar_acesso_paciente(db, s.paciente_id, current_user, acao, "sessao", s.id)
    return s


def _fid_dict(f: FidelidadeAplicacao) -> dict:
    try:
        itens = json.loads(f.itens) if f.itens else []
    except (ValueError, TypeError):
        itens = []
    return {
        "id": f.id, "sessao_id": f.sessao_id, "itens": itens,
        "total_itens": f.total_itens, "itens_ok": f.itens_ok,
        "percentual": float(f.percentual or 0), "observacao": f.observacao,
        "criado_em": f.criado_em.isoformat() if f.criado_em else None,
    }


class FidelidadeIn(BaseModel):
    itens: List[dict] = []
    observacao: Optional[str] = None


@router.post("/sessoes/{sessao_id}/fidelidade", status_code=status.HTTP_201_CREATED)
def registrar_fidelidade(sessao_id: int, body: FidelidadeIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = _get_sessao(db, sessao_id, current_user, AcaoAuditoria.CRIAR)
    itens = body.itens or []
    total = len(itens)
    ok = sum(1 for i in itens if i.get("ok"))
    pct = round(ok * 100.0 / total, 1) if total else 0.0
    f = FidelidadeAplicacao(
        escola_id=s.escola_id, sessao_id=s.id, observador_id=current_user.id,
        itens=json.dumps(itens, ensure_ascii=False), total_itens=total, itens_ok=ok,
        percentual=pct, observacao=body.observacao, criado_em=_agora(),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return _fid_dict(f)


@router.get("/sessoes/{sessao_id}/fidelidade")
def listar_fidelidade(sessao_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = _get_sessao(db, sessao_id, current_user)
    itens = db.query(FidelidadeAplicacao).filter(FidelidadeAplicacao.sessao_id == s.id).order_by(FidelidadeAplicacao.id.desc()).all()
    return [_fid_dict(f) for f in itens]


# ----------------------------------------------------------------------- IOA
def _ioa_dict(r: IOARegistro) -> dict:
    return {
        "id": r.id, "sessao_id": r.sessao_id, "objetivo_id": r.objetivo_id,
        "metodo": r.metodo, "observador2_nome": r.observador2_nome,
        "concordancias": r.concordancias, "total": r.total,
        "percentual": float(r.percentual or 0), "observacao": r.observacao,
        "criado_em": r.criado_em.isoformat() if r.criado_em else None,
    }


class IOAIn(BaseModel):
    concordancias: int
    total: int
    metodo: Optional[str] = None
    objetivo_id: Optional[int] = None
    observador2_nome: Optional[str] = None
    observacao: Optional[str] = None


@router.post("/sessoes/{sessao_id}/ioa", status_code=status.HTTP_201_CREATED)
def registrar_ioa(sessao_id: int, body: IOAIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = _get_sessao(db, sessao_id, current_user, AcaoAuditoria.CRIAR)
    total = max(0, int(body.total or 0))
    conc = max(0, min(int(body.concordancias or 0), total))
    pct = round(conc * 100.0 / total, 1) if total else 0.0
    r = IOARegistro(
        escola_id=s.escola_id, sessao_id=s.id, objetivo_id=body.objetivo_id,
        metodo=body.metodo, observador2_nome=body.observador2_nome,
        concordancias=conc, total=total, percentual=pct, observacao=body.observacao,
        registrado_por_id=current_user.id, criado_em=_agora(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _ioa_dict(r)


@router.get("/sessoes/{sessao_id}/ioa")
def listar_ioa(sessao_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = _get_sessao(db, sessao_id, current_user)
    itens = db.query(IOARegistro).filter(IOARegistro.sessao_id == s.id).order_by(IOARegistro.id.desc()).all()
    return [_ioa_dict(r) for r in itens]
