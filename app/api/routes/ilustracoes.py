"""
🎨 AdaptAI - Rotas de Ilustração de conteúdo (apoio visual)

Duas fontes, tres contextos:
  - Fonte ARASAAC (pictograma): busca gratuita, sem chave, ideal para TEA/TDAH.
  - Fonte IA (Flux via provedor): ilustracao gerada a partir do conteudo.
  - Contexto: material, questao (de prova) ou tema de redacao.

Propriedade (conteudo x ponte): a ilustracao pertence ao CONTEUDO, nunca ao
aluno. Toda rota verifica que o professor e dono do conteudo antes de ler/gravar
(anti-IDOR), no mesmo padrao de _verificar_acesso_prova.
"""
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.core.logging_config import get_logger
from app.core.rate_limit import check_rate_limit
from app.models.user import User, UserRole
from app.models.material import Material
from app.models.prova import QuestaoGerada, Prova
from app.models.redacao import TemaRedacao
from app.models.ilustracao import (
    Ilustracao,
    ContextoIlustracao,
    FonteIlustracao,
    StatusIlustracao,
)
from app.services.pictograma_service import buscar_pictogramas, url_pictograma
from app.services import ilustracao_service
from app.services.image_providers import (
    ProvedorImagemIndisponivel,
    ErroGeracaoImagem,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ilustracoes", tags=["🎨 Ilustrações"])


_CONTEXTOS = {
    "material": ContextoIlustracao.MATERIAL,
    "questao": ContextoIlustracao.QUESTAO,
    "redacao_tema": ContextoIlustracao.REDACAO_TEMA,
}

_EXT_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def _mapear_contexto(contexto_tipo: str) -> ContextoIlustracao:
    ctx = _CONTEXTOS.get((contexto_tipo or "").strip().lower())
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="contexto_tipo invalido. Use: material, questao ou redacao_tema.",
        )
    return ctx


def _is_super_admin(user: User) -> bool:
    return user.role == UserRole.SUPER_ADMIN


def _resolver_conteudo(
    db: Session,
    contexto: ContextoIlustracao,
    contexto_id: int,
    current_user: User,
) -> Tuple[str, str]:
    """Verifica acesso ao conteudo (anti-IDOR) e devolve (texto, descricao_curta).

    `texto` alimenta o prompt da IA; `descricao_curta` vira a legenda default.
    Levanta 404 se o conteudo nao existe e 403 se nao pertence ao professor.
    """
    if contexto == ContextoIlustracao.MATERIAL:
        mat = db.query(Material).filter(Material.id == contexto_id).first()
        if not mat:
            raise HTTPException(status_code=404, detail="Material nao encontrado.")
        if not _is_super_admin(current_user) and mat.criado_por_id != current_user.id:
            raise HTTPException(status_code=403, detail="Voce nao tem acesso a este material.")
        texto = " - ".join(p for p in [mat.titulo, mat.descricao, mat.materia] if p)
        return texto, (mat.titulo or "material")

    if contexto == ContextoIlustracao.QUESTAO:
        q = db.query(QuestaoGerada).filter(QuestaoGerada.id == contexto_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Questao nao encontrada.")
        prova = db.query(Prova).filter(Prova.id == q.prova_id).first()
        if not prova:
            raise HTTPException(status_code=404, detail="Prova da questao nao encontrada.")
        if not _is_super_admin(current_user) and prova.criado_por_id != current_user.id:
            raise HTTPException(status_code=403, detail="Voce nao tem acesso a esta questao.")
        return (q.enunciado or "questao"), ("Questao %s" % (q.numero or ""))

    # REDACAO_TEMA
    tema = db.query(TemaRedacao).filter(TemaRedacao.id == contexto_id).first()
    if not tema:
        raise HTTPException(status_code=404, detail="Tema de redacao nao encontrado.")
    # Tema pode ser global (criado_por_id NULL) - nesse caso qualquer professor
    # pode ilustrar. Se tem dono, precisa ser o dono (ou super admin).
    if tema.criado_por_id is not None and not _is_super_admin(current_user) \
            and tema.criado_por_id != current_user.id:
        raise HTTPException(status_code=403, detail="Voce nao tem acesso a este tema.")
    texto = " - ".join(p for p in [tema.titulo, tema.area_tematica, tema.tema] if p)
    return texto, (tema.titulo or "tema de redacao")


def _serializar(ilus: Ilustracao, request: Request) -> dict:
    """Monta o payload de saida.

    - ARASAAC: `url` aponta direto para o CDN publico (o <img> do front usa sem auth).
    - IA: `url` fica null e `endpoint` traz o caminho protegido (o front busca via
      axios com o token e mostra como blob). O endpoint e relativo ao baseURL da
      API (/api/v1), entao o front chama api.get(endpoint, {responseType:'blob'}).
    """
    if ilus.fonte == FonteIlustracao.ARASAAC:
        url = ilus.imagem_url or (url_pictograma(ilus.arasaac_id) if ilus.arasaac_id else None)
        endpoint = None
    else:
        url = None
        endpoint = "/ilustracoes/%d/imagem" % ilus.id
    return {
        "id": ilus.id,
        "contexto_tipo": ilus.contexto_tipo.value if hasattr(ilus.contexto_tipo, "value") else ilus.contexto_tipo,
        "contexto_id": ilus.contexto_id,
        "fonte": ilus.fonte.value if hasattr(ilus.fonte, "value") else ilus.fonte,
        "status": ilus.status.value if hasattr(ilus.status, "value") else ilus.status,
        "descricao": ilus.descricao,
        "arasaac_id": ilus.arasaac_id,
        "url": url,
        "endpoint": endpoint,
    }


# --------------------------------------------------------------------------- #
#  Busca de pictogramas (proxy ARASAAC)
# --------------------------------------------------------------------------- #
@router.get("/pictogramas/buscar")
def buscar_pictogramas_route(
    termo: str = Query(..., min_length=1, description="Termo em portugues"),
    idioma: str = Query("pt"),
    current_user: User = Depends(get_current_user),
):
    """Busca pictogramas na ARASAAC. Proxy no backend (evita CORS no navegador)."""
    resultados = buscar_pictogramas(termo, idioma=idioma)
    return {"termo": termo, "total": len(resultados), "pictogramas": resultados}


# --------------------------------------------------------------------------- #
#  Listar ilustracoes de um conteudo
# --------------------------------------------------------------------------- #
@router.get("")
def listar_ilustracoes(
    request: Request,
    contexto_tipo: str = Query(...),
    contexto_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contexto = _mapear_contexto(contexto_tipo)
    _resolver_conteudo(db, contexto, contexto_id, current_user)  # valida acesso

    itens = (
        db.query(Ilustracao)
        .filter(Ilustracao.contexto_tipo == contexto, Ilustracao.contexto_id == contexto_id)
        .order_by(Ilustracao.criado_em.desc())
        .all()
    )
    return {"total": len(itens), "ilustracoes": [_serializar(i, request) for i in itens]}


# --------------------------------------------------------------------------- #
#  Criar ilustracao (ARASAAC ou IA)
# --------------------------------------------------------------------------- #
class IlustracaoCreate(BaseModel):
    contexto_tipo: str = Field(..., description="material | questao | redacao_tema")
    contexto_id: int
    fonte: str = Field(..., description="arasaac | ia")
    descricao: Optional[str] = Field(None, max_length=500)
    # ARASAAC
    arasaac_id: Optional[int] = None
    imagem_url: Optional[str] = Field(None, max_length=1000)
    # IA
    tamanho: Optional[str] = Field("quadrado", description="quadrado | paisagem | retrato")


@router.post("", status_code=status.HTTP_201_CREATED)
def criar_ilustracao(
    payload: IlustracaoCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contexto = _mapear_contexto(payload.contexto_tipo)
    texto_conteudo, descricao_default = _resolver_conteudo(
        db, contexto, payload.contexto_id, current_user
    )

    fonte = (payload.fonte or "").strip().lower()

    # ---- ARASAAC: so registra o vinculo (imagem mora no CDN) ----
    if fonte == "arasaac":
        if not payload.arasaac_id:
            raise HTTPException(status_code=400, detail="arasaac_id e obrigatorio para fonte ARASAAC.")
        ilus = Ilustracao(
            contexto_tipo=contexto,
            contexto_id=payload.contexto_id,
            fonte=FonteIlustracao.ARASAAC,
            status=StatusIlustracao.PRONTA,
            descricao=(payload.descricao or descricao_default)[:500],
            arasaac_id=int(payload.arasaac_id),
            imagem_url=payload.imagem_url or url_pictograma(int(payload.arasaac_id)),
            criado_por_id=current_user.id,
        )
        db.add(ilus)
        db.commit()
        db.refresh(ilus)
        return _serializar(ilus, request)

    # ---- IA: gera prompt (Claude) -> imagem (provedor) -> salva arquivo ----
    if fonte == "ia":
        # Custo: geracao de imagem paga por imagem. Limita por professor.
        check_rate_limit(
            request, key="ilustracao_ia", max_requests=40, window_seconds=3600,
            error_message="Muitas ilustracoes geradas em pouco tempo. Aguarde um instante.",
        )

        # Registro primeiro (status PENDENTE) para ter id no nome do arquivo.
        ilus = Ilustracao(
            contexto_tipo=contexto,
            contexto_id=payload.contexto_id,
            fonte=FonteIlustracao.IA,
            status=StatusIlustracao.PENDENTE,
            descricao=(payload.descricao or descricao_default)[:500],
            criado_por_id=current_user.id,
        )
        db.add(ilus)
        db.flush()  # garante ilus.id

        try:
            prompt = ilustracao_service.gerar_prompt_ilustracao(
                contexto.value, texto_conteudo, descricao=payload.descricao
            )
            image_bytes = ilustracao_service.gerar_ilustracao_ia(
                prompt, tamanho=(payload.tamanho or "quadrado")
            )
        except ProvedorImagemIndisponivel as e:
            ilus.status = StatusIlustracao.ERRO
            db.commit()
            logger.warning("Provedor de imagem indisponivel: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Geracao por IA nao esta configurada. Fale com o administrador (falta a chave do provedor).",
            )
        except ErroGeracaoImagem:
            ilus.status = StatusIlustracao.ERRO
            db.commit()
            logger.exception("Falha ao gerar ilustracao IA (ilustracao_id=%s)", ilus.id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Nao foi possivel gerar a ilustracao agora. Tente novamente em instantes.",
            )
        except Exception:
            ilus.status = StatusIlustracao.ERRO
            db.commit()
            logger.exception("Erro inesperado ao gerar ilustracao IA (ilustracao_id=%s)", ilus.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao gerar a ilustracao.",
            )

        nome_arquivo = ilustracao_service.salvar_bytes(ilus.id, image_bytes, ext="png")
        ilus.imagem_path = nome_arquivo
        ilus.prompt_ia = prompt
        ilus.status = StatusIlustracao.PRONTA
        db.commit()
        db.refresh(ilus)
        return _serializar(ilus, request)

    raise HTTPException(status_code=400, detail="fonte invalida. Use 'arasaac' ou 'ia'.")


# --------------------------------------------------------------------------- #
#  Servir a imagem gerada por IA (arquivo protegido)
# --------------------------------------------------------------------------- #
@router.get("/{ilustracao_id}/imagem")
def servir_imagem(
    ilustracao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ilus = db.query(Ilustracao).filter(Ilustracao.id == ilustracao_id).first()
    if not ilus:
        raise HTTPException(status_code=404, detail="Ilustracao nao encontrada.")
    # Valida acesso ao conteudo dono da ilustracao.
    _resolver_conteudo(db, ilus.contexto_tipo, ilus.contexto_id, current_user)

    if ilus.fonte != FonteIlustracao.IA or not ilus.imagem_path:
        # ARASAAC nao passa por aqui (a imagem esta no CDN).
        raise HTTPException(status_code=404, detail="Sem arquivo local para esta ilustracao.")

    caminho = ilustracao_service.caminho_storage() / ilus.imagem_path
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo da ilustracao nao encontrado.")

    ext = ilus.imagem_path.rsplit(".", 1)[-1].lower()
    media = _EXT_MEDIA.get(ext, "image/png")
    return FileResponse(str(caminho), media_type=media)


# --------------------------------------------------------------------------- #
#  Remover ilustracao
# --------------------------------------------------------------------------- #
@router.delete("/{ilustracao_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_ilustracao(
    ilustracao_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ilus = db.query(Ilustracao).filter(Ilustracao.id == ilustracao_id).first()
    if not ilus:
        raise HTTPException(status_code=404, detail="Ilustracao nao encontrada.")
    _resolver_conteudo(db, ilus.contexto_tipo, ilus.contexto_id, current_user)

    # Remove o arquivo local (IA), best-effort - nao falha a exclusao por isso.
    if ilus.fonte == FonteIlustracao.IA and ilus.imagem_path:
        try:
            caminho = ilustracao_service.caminho_storage() / ilus.imagem_path
            if caminho.exists():
                caminho.unlink()
        except Exception:
            logger.warning("Nao foi possivel apagar o arquivo da ilustracao %s", ilustracao_id, exc_info=True)

    db.delete(ilus)
    db.commit()
    return None
