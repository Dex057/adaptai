"""
AdaptAI - Rota de feedback FORMATIVO de redacao (IA) — superficie mobile.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import (
    get_user_from_token,
    oauth2_scheme,
    verificar_acesso_aluno,
)
from app.core.rate_limit import check_rate_limit
from app.database import SessionLocal
from app.schemas.redacao_feedback import FeedbackRedacaoRequest, FeedbackRedacaoResponse
from app.services.redacao_feedback_ai_service import redacao_feedback_ai_service

router = APIRouter(prefix="/redacao", tags=["Redacao (feedback formativo)"])


@router.post("/feedback", response_model=FeedbackRedacaoResponse)
async def gerar_feedback_redacao(
    request: FeedbackRedacaoRequest,
    http_request: Request,
    token: str = Depends(oauth2_scheme),
):
    """
    Gera feedback formativo (nao-ENEM) sobre uma producao escrita.

    Anti-abuso: limitado a 30 geracoes/hora por IP.
    """
    check_rate_limit(
        http_request,
        key="redacao_feedback",
        max_requests=30,
        window_seconds=3600,
        error_message="Muitas analises em pouco tempo. Aguarde e tente novamente.",
    )
    current_user = get_user_from_token(token)

    aluno_info = None
    if request.student_id is not None:
        # SEGURANCA: valida acesso ao aluno (evita IDOR)
        db = SessionLocal()
        try:
            aluno = verificar_acesso_aluno(db, request.student_id, current_user)
            aluno_info = {
                "nome": aluno.name,
                "serie": aluno.grade_level,
                "diagnostico": aluno.diagnosis,
            }
        finally:
            db.close()

    try:
        markdown = await redacao_feedback_ai_service.gerar_feedback(
            texto=request.texto,
            aluno_info=aluno_info,
            foco=request.foco,
        )
        return FeedbackRedacaoResponse(markdown=markdown)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERRO] Erro ao gerar feedback de redacao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar feedback. Tente novamente.",
        )
