"""
AdaptAI - Rota de Comunicacao com a familia (IA).

Gera um recado acolhedor aos responsaveis a partir de um contexto curto.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import (
    get_user_from_token,
    oauth2_scheme,
    verificar_acesso_aluno,
)
from app.core.rate_limit import check_rate_limit
from app.database import SessionLocal
from app.schemas.comunicacao import MensagemFamiliaRequest, MensagemFamiliaResponse
from app.services.comunicacao_ai_service import comunicacao_ai_service

router = APIRouter(prefix="/comunicacao", tags=["Comunicacao"])


@router.post("/familia/mensagem", response_model=MensagemFamiliaResponse)
async def gerar_mensagem_familia(
    request: MensagemFamiliaRequest,
    http_request: Request,
    token: str = Depends(oauth2_scheme),
):
    """
    Gera uma mensagem acolhedora para a familia do estudante.

    Anti-abuso: limitado a 40 geracoes/hora por IP (cada uma custa tokens de IA).
    """
    check_rate_limit(
        http_request,
        key="comunicacao_familia",
        max_requests=40,
        window_seconds=3600,
        error_message="Muitas mensagens em pouco tempo. Aguarde e tente novamente.",
    )
    current_user = get_user_from_token(token)

    # SEGURANCA: valida acesso ao aluno (evita IDOR)
    db = SessionLocal()
    try:
        aluno = verificar_acesso_aluno(db, request.aluno_id, current_user)
        aluno_info = {
            "nome": aluno.name,
            "serie": aluno.grade_level,
            "diagnostico": aluno.diagnosis,
        }
    finally:
        db.close()

    try:
        mensagem = await comunicacao_ai_service.gerar_mensagem_familia(
            aluno_info=aluno_info,
            tom=request.tom,
            nota=request.nota,
            professor_nome=getattr(current_user, "name", None),
        )
        return MensagemFamiliaResponse(mensagem=mensagem)
    except HTTPException:
        raise
    except Exception as e:
        # SEGURANCA: nao vazar erro interno
        print(f"[ERRO] Erro ao gerar mensagem para familia: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar mensagem. Tente novamente.",
        )
