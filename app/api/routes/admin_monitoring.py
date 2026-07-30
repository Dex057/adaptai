"""
Endpoints administrativos para monitoramento do sistema.

Acesso restrito a ADMIN ou SUPER_ADMIN.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.api.dependencies import require_admin
from app.models.user import User
from app.models.background_task import BackgroundTask, BackgroundTaskStatus
from app.models.ai_usage_log import AIUsageLog
from app.services.ai_cache_service import cache_stats, cleanup_old_cache
from app.services.background_tasks import task_manager


router = APIRouter(prefix="/admin", tags=["Admin - Monitoramento"])


@router.get("/ai-cache/stats")
def obter_stats_cache_ia(current_user: User = Depends(require_admin)):
    """
    Retorna estatisticas do cache de IA.
    
    Util para acompanhar economia de creditos Anthropic:
    - total_entries: quantas respostas unicas foram cacheadas
    - total_hits: quantas vezes o cache foi reutilizado (= chamadas economizadas)
    - top_types: quais tipos de material mais se beneficiam
    """
    return cache_stats()


@router.post("/ai-cache/cleanup")
def limpar_cache_ia_antigo(
    ttl_hours: int = 672,
    current_user: User = Depends(require_admin),
):
    """
    Remove entradas de cache nao usadas ha mais de ttl_hours.
    Default: 4 semanas (672h).
    """
    removidos = cleanup_old_cache(ttl_hours=ttl_hours)
    return {
        "removidos": removidos,
        "ttl_hours": ttl_hours,
    }


@router.get("/background-tasks/stats")
def obter_stats_background_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Retorna estatisticas de tarefas em background.
    Util para ver se ha tasks travadas, taxa de falhas, etc.
    """
    por_status = (
        db.query(BackgroundTask.status, func.count(BackgroundTask.id))
        .group_by(BackgroundTask.status)
        .all()
    )
    
    por_tipo = (
        db.query(BackgroundTask.task_type, func.count(BackgroundTask.id))
        .group_by(BackgroundTask.task_type)
        .limit(20)
        .all()
    )
    
    # Ultimas 10 tasks falhas (debugging)
    falhas_recentes = (
        db.query(BackgroundTask)
        .filter(BackgroundTask.status == BackgroundTaskStatus.FAILED)
        .order_by(BackgroundTask.created_at.desc())
        .limit(10)
        .all()
    )
    
    return {
        "por_status": [
            {"status": s.value if s else "null", "count": c}
            for s, c in por_status
        ],
        "por_tipo": [
            {"tipo": t or "null", "count": c}
            for t, c in por_tipo
        ],
        "falhas_recentes": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "error": (t.error or "")[:200],
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in falhas_recentes
        ],
    }


@router.post("/background-tasks/cleanup")
def limpar_background_tasks_antigas(current_user: User = Depends(require_admin)):
    """Remove tasks mais antigas que o TTL configurado (default 7 dias)."""
    removidos = task_manager.cleanup_old_tasks()
    return {"removidos": removidos or 0}


@router.get("/ai-usage/stats")
def obter_stats_uso_ia(
    dias: int = 30,
    feature: str = None,
    user_id: int = None,
    student_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Retorna consumo de tokens/custo da IA (Claude) agregado por feature e por
    modelo, na janela dos ultimos `dias` (default 30).

    Filtros opcionais (combinaveis): `feature` (ex.: "jornada_terapeutica"),
    `user_id`, `student_id`. Uteis para responder perguntas pontuais, ex.:
    "quanto a jornada terapeutica custou para o usuario 42 nos ultimos 90 dias"
    -> ?feature=jornada_terapeutica&user_id=42&dias=90

    Nem toda feature grava user_id/student_id (depende do que cada chamada a
    registrar_uso_ia informou) - ver docs/API_AI_USAGE_STATS.md.

    Fonte: tabela ai_usage_log, gravada por app.core.ai_usage.registrar_uso_ia
    apos cada chamada real a Claude nas features de IA (PEI, jornada
    terapeutica, planejamento, analise qualitativa, prova de reforco).
    """
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    base = db.query(AIUsageLog).filter(AIUsageLog.created_at >= desde)

    if feature is not None:
        base = base.filter(AIUsageLog.feature == feature)
    if user_id is not None:
        base = base.filter(AIUsageLog.user_id == user_id)
    if student_id is not None:
        base = base.filter(AIUsageLog.student_id == student_id)

    def agregados(coluna):
        return (
            base.with_entities(
                coluna,
                func.count(AIUsageLog.id),
                func.sum(AIUsageLog.input_tokens),
                func.sum(AIUsageLog.output_tokens),
                func.sum(AIUsageLog.cost_usd),
            )
            .group_by(coluna)
            .order_by(func.sum(AIUsageLog.cost_usd).desc())
            .all()
        )

    def linha(chave, chamadas, input_tokens, output_tokens, custo):
        return {
            "chamadas": int(chamadas or 0),
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "custo_usd": float(custo) if custo is not None else None,
            **chave,
        }

    total_chamadas, total_input, total_output, total_custo = base.with_entities(
        func.count(AIUsageLog.id),
        func.sum(AIUsageLog.input_tokens),
        func.sum(AIUsageLog.output_tokens),
        func.sum(AIUsageLog.cost_usd),
    ).first()

    recentes = base.order_by(AIUsageLog.id.desc()).limit(20).all()

    return {
        "periodo_dias": dias,
        "filtros": {"feature": feature, "user_id": user_id, "student_id": student_id},
        "total": {
            "chamadas": int(total_chamadas or 0),
            "input_tokens": int(total_input or 0),
            "output_tokens": int(total_output or 0),
            "custo_usd": float(total_custo) if total_custo is not None else None,
        },
        "por_feature": [
            linha({"feature": feature}, chamadas, in_tok, out_tok, custo)
            for feature, chamadas, in_tok, out_tok, custo in agregados(AIUsageLog.feature)
        ],
        "por_modelo": [
            linha({"model": model}, chamadas, in_tok, out_tok, custo)
            for model, chamadas, in_tok, out_tok, custo in agregados(AIUsageLog.model)
        ],
        "chamadas_recentes": [
            {
                "id": r.id,
                "feature": r.feature,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "custo_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "student_id": r.student_id,
                "user_id": r.user_id,
                "escola_id": r.escola_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recentes
        ],
    }
