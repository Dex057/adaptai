"""
Modelo SQLAlchemy para registro de consumo de tokens do Claude.

MOTIVACAO: nenhuma das features que chamam a IA (PEI, jornada terapeutica,
planejamento diario/anual, analise qualitativa, prova de reforco) registrava
quantos tokens cada requisicao consumia - o `usage` devolvido pela API era
descartado. Esta tabela guarda uma linha por chamada a Claude, com a
contagem EXATA de tokens (vinda de `response.usage`, nao estimada) e uma
estimativa de custo em USD, para permitir consultas agregadas por feature,
aluno, usuario ou periodo.

Sem foreign keys propositalmente: e uma tabela de log/telemetria, nao de
dominio - nao deve impedir (nem ser afetada por) exclusao de alunos/usuarios.
Ver app/core/ai_usage.py para quem grava aqui.
"""
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Index
from datetime import datetime, timezone

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class AIUsageLog(Base):
    """
    Uma linha por chamada `messages.create` feita a Claude.
    """
    __tablename__ = "ai_usage_log"

    id = Column(Integer, primary_key=True, index=True)

    # Identifica a funcionalidade que originou a chamada, ex.:
    # "pei_analise_laudo", "pei_geracao", "jornada_terapeutica",
    # "planejamento_anual", "planejamento_trimestre",
    # "planejamento_anual_completo", "analise_qualitativa", "prova_reforco".
    feature = Column(String(50), nullable=False, index=True)

    # Modelo Claude usado nesta chamada (ex.: "claude-sonnet-4-6").
    model = Column(String(100), nullable=False)

    # Contagem exata de tokens devolvida pela API em response.usage.
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_creation_input_tokens = Column(Integer, nullable=False, default=0)
    cache_read_input_tokens = Column(Integer, nullable=False, default=0)

    # Estimativa de custo em USD (tabela de precos estatica - ver
    # app/core/ai_usage.py). Nulo quando o modelo nao esta na tabela de precos.
    cost_usd = Column(Numeric(12, 6), nullable=True)

    # Atribuicao opcional (sem FK - ver docstring do modulo).
    student_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    escola_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_ai_usage_feature_created", "feature", "created_at"),
    )
