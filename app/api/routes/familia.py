"""
🏥 AdaptAI - Portal da Família (read-only) do vertical CLINICA.

Acesso pelo `token_familia` opaco do paciente (gerado em
POST /clinica/pacientes/{id}/token-familia). NÃO usa login: o próprio token na
URL é a credencial (como um link de compartilhamento). Só expõe o essencial e
apenas o que já foi validado por um profissional:
  - primeiro nome do paciente e status;
  - objetivos ativos (descrição/especialidade/status);
  - evoluções ASSINADAS (rascunhos de IA não assinados nunca aparecem).

Rascunhos não assinados e dados sensíveis (responsável, contato) ficam de fora.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.clinica_core import Paciente, Consentimento, TipoConsentimento
from app.models.clinica_terapia import (
    PlanoTerapeutico, ObjetivoTerapeutico, Evolucao, StatusObjetivoTerapeutico,
)
from app.models.clinica_casa import TarefaCasa, TarefaCasaCheck
from app.models.clinica_mensagens import MensagemFamilia, OrigemMensagem

router = APIRouter(prefix="/familia", tags=["🏥 Portal da Família"])


def _v(e):
    return e.value if hasattr(e, "value") else e


def _paciente_por_token(db: Session, token: str) -> Paciente:
    if not token or len(token) < 12:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link inválido")
    p = db.query(Paciente).filter(Paciente.token_familia == token).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link inválido")
    return p


def _tem_consentimento_vigente(db: Session, paciente_id: int, tipo: TipoConsentimento) -> bool:
    """True se existe consentimento do tipo, ainda não revogado (LGPD)."""
    c = (
        db.query(Consentimento)
        .filter(
            Consentimento.paciente_id == paciente_id,
            Consentimento.tipo == tipo,
            Consentimento.revogado_em.is_(None),
        )
        .first()
    )
    return c is not None


def _exigir_consentimento(db: Session, paciente_id: int, tipo: TipoConsentimento):
    """Bloqueia (403) o compartilhamento se o consentimento não estiver vigente.
    Reversível: a clínica registra o consentimento e o portal volta a abrir."""
    if not _tem_consentimento_vigente(db, paciente_id, tipo):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Compartilhamento não autorizado. Fale com a clínica para registrar o consentimento.",
        )


@router.get("/{token}")
def portal(token: str, db: Session = Depends(get_db)):
    p = _paciente_por_token(db, token)
    # LGPD: só expõe o conteúdo clínico se o tratamento de dados foi consentido.
    _exigir_consentimento(db, p.id, TipoConsentimento.TRATAMENTO_DADOS)

    objetivos = (
        db.query(ObjetivoTerapeutico)
        .join(PlanoTerapeutico, PlanoTerapeutico.id == ObjetivoTerapeutico.plano_id)
        .filter(
            PlanoTerapeutico.paciente_id == p.id,
            ObjetivoTerapeutico.status != StatusObjetivoTerapeutico.DESCONTINUADO,
        )
        .order_by(ObjetivoTerapeutico.ordem, ObjetivoTerapeutico.id)
        .all()
    )
    evolucoes = (
        db.query(Evolucao)
        .filter(Evolucao.paciente_id == p.id, Evolucao.assinado_em.isnot(None))
        .order_by(Evolucao.assinado_em.desc())
        .limit(5)
        .all()
    )
    primeiro_nome = (p.nome or "").strip().split(" ")[0]
    return {
        "paciente": {"nome": primeiro_nome, "status": _v(p.status)},
        "objetivos": [
            {"descricao": o.descricao, "especialidade": _v(o.especialidade), "status": _v(o.status)}
            for o in objetivos
        ],
        "evolucoes": [
            {"texto": e.texto, "data": str(e.assinado_em) if e.assinado_em else None}
            for e in evolucoes
        ],
    }


# ---------------------------------------------------------------------------
# Programa de casa (a familia marca "fez/nao fez" hoje)
# ---------------------------------------------------------------------------
@router.get("/{token}/tarefas")
def tarefas(token: str, db: Session = Depends(get_db)):
    p = _paciente_por_token(db, token)
    ts = (db.query(TarefaCasa)
          .filter(TarefaCasa.paciente_id == p.id, TarefaCasa.ativo.is_(True))
          .order_by(TarefaCasa.id.desc()).all())
    hoje = datetime.now(timezone.utc).date()
    ids = [t.id for t in ts] or [0]
    checks = {c.tarefa_id: c for c in db.query(TarefaCasaCheck).filter(
        TarefaCasaCheck.tarefa_id.in_(ids), TarefaCasaCheck.data == hoje).all()}
    return {"tarefas": [{
        "id": t.id, "titulo": t.titulo, "descricao": t.descricao,
        "feito_hoje": bool(checks[t.id].feito) if t.id in checks else False,
    } for t in ts]}


class CheckIn(BaseModel):
    feito: bool = True
    observacao: str | None = None


@router.post("/{token}/tarefas/{tarefa_id}/check")
def marcar_tarefa(token: str, tarefa_id: int, body: CheckIn, db: Session = Depends(get_db)):
    p = _paciente_por_token(db, token)
    t = db.query(TarefaCasa).filter(
        TarefaCasa.id == tarefa_id, TarefaCasa.paciente_id == p.id).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarefa nao encontrada")
    hoje = datetime.now(timezone.utc).date()
    c = db.query(TarefaCasaCheck).filter(
        TarefaCasaCheck.tarefa_id == t.id, TarefaCasaCheck.data == hoje).first()
    if c:
        c.feito = body.feito
        c.observacao = body.observacao
    else:
        c = TarefaCasaCheck(tarefa_id=t.id, data=hoje, feito=body.feito,
                            observacao=body.observacao, criado_em=datetime.now(timezone.utc))
        db.add(c)
    db.commit()
    return {"tarefa_id": t.id, "feito_hoje": body.feito}


# ---------------------------------------------------------------------------
# Mensagens (canal equipe <-> familia)
# ---------------------------------------------------------------------------
@router.get("/{token}/mensagens")
def familia_mensagens(token: str, db: Session = Depends(get_db)):
    p = _paciente_por_token(db, token)
    msgs = (db.query(MensagemFamilia)
            .filter(MensagemFamilia.paciente_id == p.id)
            .order_by(MensagemFamilia.id).limit(200).all())
    return {"mensagens": [{
        "id": m.id, "origem": _v(m.origem), "texto": m.texto,
        "criado_em": str(m.criado_em) if m.criado_em else None,
    } for m in msgs]}


class MensagemFamiliaIn(BaseModel):
    texto: str


@router.post("/{token}/mensagens", status_code=status.HTTP_201_CREATED)
def familia_enviar_mensagem(token: str, body: MensagemFamiliaIn, db: Session = Depends(get_db)):
    p = _paciente_por_token(db, token)
    if not (body.texto or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mensagem vazia")
    m = MensagemFamilia(
        escola_id=p.escola_id, paciente_id=p.id, origem=OrigemMensagem.FAMILIA,
        texto=body.texto.strip(), criado_em=datetime.now(timezone.utc),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id}
