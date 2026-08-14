"""
🎨 AdaptAI - Ilustrações no PORTAL DO ALUNO (somente leitura)

O professor anexa ilustracoes ao conteudo (ver routes/ilustracoes.py). Aqui o
ALUNO apenas VE as ilustracoes do conteudo a que ELE tem acesso. A checagem de
acesso e diferente da do professor: nao e "sou dono", e "este conteudo esta
atribuido a mim" (via as tabelas-ponte MaterialAluno / ProvaAluno / RedacaoAluno).

Sem posse nova, sem escrita: o aluno nao cria nem remove ilustracao.
"""
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_student
from app.core.logging_config import get_logger
from app.models.student import Student
from app.models.material import MaterialAluno
from app.models.prova import QuestaoGerada, ProvaAluno
from app.models.redacao import RedacaoAluno
from app.models.ilustracao import (
    Ilustracao,
    ContextoIlustracao,
    FonteIlustracao,
)
from app.services.pictograma_service import url_pictograma
from app.services import ilustracao_service

logger = get_logger(__name__)

router = APIRouter(prefix="/student/ilustracoes", tags=["🎨 Ilustrações (Aluno)"])

_CONTEXTOS = {
    "material": ContextoIlustracao.MATERIAL,
    "questao": ContextoIlustracao.QUESTAO,
    "redacao_tema": ContextoIlustracao.REDACAO_TEMA,
}
_EXT_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _mapear_contexto(contexto_tipo: str) -> ContextoIlustracao:
    ctx = _CONTEXTOS.get((contexto_tipo or "").strip().lower())
    if ctx is None:
        raise HTTPException(status_code=400, detail="contexto_tipo invalido.")
    return ctx


def _verificar_acesso_aluno(
    db: Session,
    contexto: ContextoIlustracao,
    contexto_id: int,
    student: Student,
) -> None:
    """Garante que o conteudo esta atribuido a ESTE aluno. 403 caso contrario."""
    if contexto == ContextoIlustracao.MATERIAL:
        vinculo = (
            db.query(MaterialAluno)
            .filter(MaterialAluno.material_id == contexto_id, MaterialAluno.aluno_id == student.id)
            .first()
        )
        if not vinculo:
            raise HTTPException(status_code=403, detail="Voce nao tem acesso a este material.")
        return

    if contexto == ContextoIlustracao.QUESTAO:
        q = db.query(QuestaoGerada).filter(QuestaoGerada.id == contexto_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Questao nao encontrada.")
        vinculo = (
            db.query(ProvaAluno)
            .filter(ProvaAluno.prova_id == q.prova_id, ProvaAluno.aluno_id == student.id)
            .first()
        )
        if not vinculo:
            raise HTTPException(status_code=403, detail="Voce nao tem acesso a esta questao.")
        return

    # REDACAO_TEMA
    vinculo = (
        db.query(RedacaoAluno)
        .filter(RedacaoAluno.tema_id == contexto_id, RedacaoAluno.aluno_id == student.id)
        .first()
    )
    if not vinculo:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a este tema.")


def _serializar(ilus: Ilustracao) -> dict:
    """Igual ao do professor, mas o endpoint da imagem IA aponta para a rota do
    aluno (que valida acesso pela ponte, nao pela posse)."""
    if ilus.fonte == FonteIlustracao.ARASAAC:
        url = ilus.imagem_url or (url_pictograma(ilus.arasaac_id) if ilus.arasaac_id else None)
        endpoint = None
    else:
        url = None
        endpoint = "/student/ilustracoes/%d/imagem" % ilus.id
    return {
        "id": ilus.id,
        "fonte": ilus.fonte.value if hasattr(ilus.fonte, "value") else ilus.fonte,
        "descricao": ilus.descricao,
        "arasaac_id": ilus.arasaac_id,
        "url": url,
        "endpoint": endpoint,
    }


@router.get("")
def listar_ilustracoes_aluno(
    contexto_tipo: str = Query(...),
    contexto_id: int = Query(...),
    db: Session = Depends(get_db),
    current_student: Student = Depends(get_current_student),
):
    contexto = _mapear_contexto(contexto_tipo)
    _verificar_acesso_aluno(db, contexto, contexto_id, current_student)

    itens = (
        db.query(Ilustracao)
        .filter(Ilustracao.contexto_tipo == contexto, Ilustracao.contexto_id == contexto_id)
        .order_by(Ilustracao.criado_em.desc())
        .all()
    )
    return {"total": len(itens), "ilustracoes": [_serializar(i) for i in itens]}


@router.get("/{ilustracao_id}/imagem")
def servir_imagem_aluno(
    ilustracao_id: int,
    db: Session = Depends(get_db),
    current_student: Student = Depends(get_current_student),
):
    ilus = db.query(Ilustracao).filter(Ilustracao.id == ilustracao_id).first()
    if not ilus:
        raise HTTPException(status_code=404, detail="Ilustracao nao encontrada.")
    _verificar_acesso_aluno(db, ilus.contexto_tipo, ilus.contexto_id, current_student)

    if ilus.fonte != FonteIlustracao.IA or not ilus.imagem_path:
        raise HTTPException(status_code=404, detail="Sem arquivo local para esta ilustracao.")

    caminho = ilustracao_service.caminho_storage() / ilus.imagem_path
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo da ilustracao nao encontrado.")

    ext = ilus.imagem_path.rsplit(".", 1)[-1].lower()
    media = _EXT_MEDIA.get(ext, "image/png")
    return FileResponse(str(caminho), media_type=media)
