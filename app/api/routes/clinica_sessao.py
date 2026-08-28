"""
🏥 AdaptAI - Rotas de SESSAO do vertical CLINICA (Modo Papel + evolucao IA + graficos).

Complementa clinica.py com:
  - Modo Papel clinico: imprimir folha de registro -> foto -> Vision transcreve
    -> humano revisa -> confirmar grava os registros de tentativa.
  - Rascunho de evolucao por IA (evolucao_service), no padrao "IA rascunha,
    humano assina".
  - Serie de evolucao por objetivo (dados para o grafico de mastery).

Mesmo isolamento do clinica.py: router exige o modulo CLINICA e todo acesso a
paciente passa pelo guard acesso_clinico (anti-IDOR).
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.services import evolucao_service, sessao_folha_service
from app.services import faturamento_service
from app.models.clinica_terapia import (
    PlanoTerapeutico, ObjetivoTerapeutico, Sessao, RegistroTentativa, Evolucao,
    StatusObjetivoTerapeutico, NivelAjuda,
)

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Sessão)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _agora():
    return datetime.now(timezone.utc)


def _v(e):
    return e.value if hasattr(e, "value") else e


def _sessao_com_acesso(db, sessao_id, current_user) -> Sessao:
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id).first()
    if not sessao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessao nao encontrada")
    acesso_clinico.verificar_acesso_paciente(db, sessao.paciente_id, current_user)
    return sessao


def _objetivos_do_paciente(db, paciente_id) -> List[ObjetivoTerapeutico]:
    """Objetivos (nao descontinuados) dos planos do paciente."""
    return (
        db.query(ObjetivoTerapeutico)
        .join(PlanoTerapeutico, PlanoTerapeutico.id == ObjetivoTerapeutico.plano_id)
        .filter(
            PlanoTerapeutico.paciente_id == paciente_id,
            ObjetivoTerapeutico.status != StatusObjetivoTerapeutico.DESCONTINUADO,
        )
        .order_by(ObjetivoTerapeutico.ordem, ObjetivoTerapeutico.id)
        .all()
    )


# Limiar de mastery (media de independencia dos ultimos registros).
MASTERY_PCT = 80.0
MASTERY_JANELA = 3


def _recalcular_status_objetivo(db, objetivo_id: int) -> None:
    """Atualiza o status do objetivo a partir dos ultimos registros.
    Regra simples e conservadora (o profissional sempre pode ajustar a mao):
      media dos ultimos N %independencia >= MASTERY_PCT -> MASTERY;
      houve algum registro e ainda em BASELINE -> EM_AQUISICAO."""
    obj = db.query(ObjetivoTerapeutico).filter(ObjetivoTerapeutico.id == objetivo_id).first()
    if not obj or obj.status in (StatusObjetivoTerapeutico.MANUTENCAO,
                                 StatusObjetivoTerapeutico.GENERALIZACAO,
                                 StatusObjetivoTerapeutico.DESCONTINUADO):
        return
    ultimos = (
        db.query(RegistroTentativa)
        .filter(RegistroTentativa.objetivo_id == objetivo_id)
        .order_by(RegistroTentativa.id.desc())
        .limit(MASTERY_JANELA)
        .all()
    )
    pcts = [float(r.percentual_independencia) for r in ultimos
            if r.percentual_independencia is not None]
    if not pcts:
        return
    media = sum(pcts) / len(pcts)
    novo = obj.status
    if media >= MASTERY_PCT:
        novo = StatusObjetivoTerapeutico.MASTERY
    elif obj.status == StatusObjetivoTerapeutico.BASELINE:
        novo = StatusObjetivoTerapeutico.EM_AQUISICAO
    if novo != obj.status:
        obj.status = novo
        obj.atualizado_em = _agora()
        db.commit()


# ============================================================================
# Objetivos do paciente (para o detalhe + grafico)
# ============================================================================
@router.get("/pacientes/{paciente_id}/objetivos")
def listar_objetivos(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    objs = _objetivos_do_paciente(db, p.id)
    return [{
        "id": o.id, "plano_id": o.plano_id, "descricao": o.descricao,
        "especialidade": _v(o.especialidade), "status": _v(o.status),
        "criterio_mastery": o.criterio_mastery,
        "linha_base": float(o.linha_base) if o.linha_base is not None else None,
    } for o in objs]


# ============================================================================
# Rascunho de evolucao por IA
# ============================================================================
@router.post("/sessoes/{sessao_id}/evolucao/rascunhar", status_code=status.HTTP_201_CREATED)
def rascunhar_evolucao(
    sessao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessao = _sessao_com_acesso(db, sessao_id, current_user)

    # Monta os dados objetivos da sessao (metas + desempenho registrado).
    regs = (
        db.query(RegistroTentativa, ObjetivoTerapeutico)
        .join(ObjetivoTerapeutico, ObjetivoTerapeutico.id == RegistroTentativa.objetivo_id)
        .filter(RegistroTentativa.sessao_id == sessao.id)
        .all()
    )
    metas = []
    for reg, obj in regs:
        metas.append({
            "descricao": obj.descricao,
            "especialidade": _v(obj.especialidade),
            "tentativas": reg.tentativas,
            "acertos": reg.acertos,
            "percentual_independencia": float(reg.percentual_independencia)
                if reg.percentual_independencia is not None else None,
            "nivel_ajuda": _v(reg.nivel_ajuda),
        })

    texto = evolucao_service.rascunhar_evolucao(
        metas=metas,
        especialidade=_v(sessao.especialidade),
        observacao=sessao.observacao,
    )

    ev = Evolucao(
        escola_id=sessao.escola_id,
        paciente_id=sessao.paciente_id,
        sessao_id=sessao.id,
        profissional_id=sessao.profissional_id,
        especialidade=sessao.especialidade,
        texto=texto,
        rascunho_ia=True,
        criado_em=_agora(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"id": ev.id, "sessao_id": ev.sessao_id, "paciente_id": ev.paciente_id,
            "texto": ev.texto, "rascunho_ia": True, "assinada": False}


# ============================================================================
# Serie de evolucao por objetivo (dados do grafico de mastery)
# ============================================================================
@router.get("/objetivos/{objetivo_id}/evolucao")
def serie_evolucao_objetivo(
    objetivo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = db.query(ObjetivoTerapeutico).filter(ObjetivoTerapeutico.id == objetivo_id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Objetivo nao encontrado")
    plano = db.query(PlanoTerapeutico).filter(PlanoTerapeutico.id == obj.plano_id).first()
    if not plano:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano do objetivo nao encontrado")
    acesso_clinico.verificar_acesso_paciente(db, plano.paciente_id, current_user)

    linhas = (
        db.query(RegistroTentativa, Sessao)
        .join(Sessao, Sessao.id == RegistroTentativa.sessao_id)
        .filter(RegistroTentativa.objetivo_id == obj.id)
        .order_by(Sessao.data_sessao)
        .all()
    )
    pontos = []
    for reg, sess in linhas:
        pct = reg.percentual_independencia
        if pct is None and reg.tentativas:
            pct = round((reg.acertos or 0) * 100.0 / reg.tentativas, 2)
        pontos.append({
            "data": str(sess.data_sessao) if sess.data_sessao else None,
            "percentual_independencia": float(pct) if pct is not None else None,
            "tentativas": reg.tentativas, "acertos": reg.acertos,
            "nivel_ajuda": _v(reg.nivel_ajuda),
        })
    return {
        "objetivo_id": obj.id, "descricao": obj.descricao,
        "status": _v(obj.status),
        "criterio_mastery": obj.criterio_mastery,
        "linha_base": float(obj.linha_base) if obj.linha_base is not None else None,
        "serie": pontos,
    }


# ============================================================================
# Modo Papel clinico — folha de sessao
# ============================================================================
@router.get("/sessoes/{sessao_id}/completa")
def sessao_completa(
    sessao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dados registrados da sessao (para a folha preenchida / PDF): registros de
    tentativa por objetivo + evolucao assinada, se houver. Minimizacao: nao
    retorna nome do paciente (o profissional preenche na impressao)."""
    sessao = _sessao_com_acesso(db, sessao_id, current_user)
    regs = (
        db.query(RegistroTentativa, ObjetivoTerapeutico)
        .join(ObjetivoTerapeutico, ObjetivoTerapeutico.id == RegistroTentativa.objetivo_id)
        .filter(RegistroTentativa.sessao_id == sessao.id)
        .order_by(ObjetivoTerapeutico.ordem, ObjetivoTerapeutico.id)
        .all()
    )
    ev = (
        db.query(Evolucao)
        .filter(Evolucao.sessao_id == sessao.id)
        .order_by(Evolucao.id.desc())
        .first()
    )
    def _num(v):
        return float(v) if v is not None else None
    return {
        "sessao_id": sessao.id,
        "data_sessao": str(sessao.data_sessao) if sessao.data_sessao else None,
        "especialidade": _v(sessao.especialidade),
        "presenca": _v(sessao.presenca),
        "observacao": sessao.observacao,
        "registros": [
            {
                "objetivo": obj.descricao,
                "especialidade": _v(obj.especialidade),
                "tentativas": reg.tentativas,
                "acertos": reg.acertos,
                "percentual_independencia": _num(reg.percentual_independencia),
                "nivel_ajuda": _v(reg.nivel_ajuda),
            }
            for reg, obj in regs
        ],
        "evolucao": (
            {"texto": ev.texto, "assinada": ev.assinado_em is not None,
             "assinado_em": str(ev.assinado_em) if ev.assinado_em else None}
            if ev else None
        ),
    }


@router.get("/sessoes/{sessao_id}/folha-impressao")
def folha_impressao(
    sessao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessao = _sessao_com_acesso(db, sessao_id, current_user)
    objetivos = _objetivos_do_paciente(db, sessao.paciente_id)
    return {
        "sessao_id": sessao.id,
        "codigo_folha": "SE-%06d" % sessao.id,
        "data_sessao": str(sessao.data_sessao) if sessao.data_sessao else None,
        "especialidade": _v(sessao.especialidade),
        "objetivos": [
            {"id": o.id, "descricao": o.descricao,
             "especialidade": _v(o.especialidade),
             "criterio_mastery": o.criterio_mastery}
            for o in objetivos
        ],
    }


@router.post("/sessoes/{sessao_id}/folha")
async def enviar_folha(
    sessao_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sobe a foto da folha; a IA transcreve as marcacoes. NAO persiste — o
    profissional revisa e chama /folha/confirmar."""
    sessao = _sessao_com_acesso(db, sessao_id, current_user)
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio")

    objetivos = _objetivos_do_paciente(db, sessao.paciente_id)
    dados = sessao_folha_service.transcrever_folha_sessao(
        image_bytes=conteudo,
        content_type=file.content_type or "image/jpeg",
        objetivos=[{"id": o.id, "descricao": o.descricao} for o in objetivos],
    )
    # so leitura; devolve para revisao humana
    return {"sessao_id": sessao.id, "transcricao": dados}


class RegistroRevisado(BaseModel):
    objetivo_id: int
    tentativas: int = Field(0, ge=0)
    acertos: int = Field(0, ge=0)
    nivel_ajuda: Optional[NivelAjuda] = None


class ConfirmarFolha(BaseModel):
    registros: List[RegistroRevisado]


@router.post("/sessoes/{sessao_id}/folha/confirmar", status_code=status.HTTP_201_CREATED)
def confirmar_folha(
    sessao_id: int,
    body: ConfirmarFolha,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grava os registros de tentativa (ja revisados pelo profissional)."""
    sessao = _sessao_com_acesso(db, sessao_id, current_user)
    # ids de objetivos validos para este paciente (evita gravar meta de outro)
    validos = {o.id for o in _objetivos_do_paciente(db, sessao.paciente_id)}

    criados = []
    for r in body.registros:
        if r.objetivo_id not in validos:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Objetivo %s nao pertence a este paciente" % r.objetivo_id,
            )
        if r.acertos > r.tentativas:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "acertos nao pode ser maior que tentativas (objetivo %s)" % r.objetivo_id,
            )
        pct = round(r.acertos * 100.0 / r.tentativas, 2) if r.tentativas else None
        reg = RegistroTentativa(
            sessao_id=sessao.id,
            objetivo_id=r.objetivo_id,
            tentativas=r.tentativas,
            acertos=r.acertos,
            nivel_ajuda=r.nivel_ajuda,
            percentual_independencia=pct,
            criado_em=_agora(),
        )
        db.add(reg)
        criados.append(r.objetivo_id)
    db.commit()
    # recalcula mastery dos objetivos afetados (conservador; profissional ajusta)
    for oid in set(criados):
        _recalcular_status_objetivo(db, oid)
    # faturamento automatico da sessao (best-effort: nunca derruba a confirmacao)
    faturamento_id = None
    try:
        fat = faturamento_service.faturar_sessao(db, sessao, current_user.id)
        faturamento_id = fat.id if fat else None
    except Exception:  # noqa: BLE001
        faturamento_id = None
    return {"sessao_id": sessao.id, "registros_criados": len(criados),
            "faturamento_id": faturamento_id}
