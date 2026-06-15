"""
AdaptAI - Rota de Plano de aula simples (IA) — superficie mobile.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_active_user
from app.core.rate_limit import check_rate_limit
from app.models.user import User
from app.schemas.plano_aula import PlanoAulaRequest, PlanoAulaResponse
from app.services.plano_aula_ai_service import plano_aula_ai_service

router = APIRouter(prefix="/plano-aula", tags=["Plano de aula"])


@router.post("/gerar", response_model=PlanoAulaResponse)
async def gerar_plano_aula(
    request_body: PlanoAulaRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    """
    Gera um plano de aula simples (objetivo, sequencia, adaptacoes, avaliacao).

    Anti-abuso: limitado a 20 geracoes/hora por IP.
    """
    check_rate_limit(
        request,
        key="gerar_plano_aula",
        max_requests=20,
        window_seconds=3600,
        error_message="Limite de geracoes atingido. Aguarde 1 hora.",
    )
    try:
        markdown = plano_aula_ai_service.gerar(
            componente=request_body.componente,
            tema=request_body.tema,
            duracao=request_body.duracao,
            serie=request_body.serie,
            perfis=request_body.perfis,
        )
        return PlanoAulaResponse(markdown=markdown)
    except Exception as e:
        print(f"[ERRO] Erro ao gerar plano de aula: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar plano de aula. Tente novamente.",
        )
