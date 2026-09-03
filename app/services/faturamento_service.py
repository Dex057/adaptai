"""
Faturamento automatico por sessao.

Ao confirmar a folha de uma sessao, gera um item de faturamento usando o preco
configurado para a especialidade da sessao (0 se nao configurado). Dedup por
sessao: nunca gera dois itens para a mesma sessao.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.clinica_faturamento import (
    Faturamento, PrecoEspecialidade, StatusFaturamento,
)


def faturar_sessao(db: Session, sessao, criado_por_id=None):
    """Cria um Faturamento para a sessao (uma unica vez).
    Retorna o Faturamento criado, ou None se ja existia um para esta sessao."""
    if sessao is None or sessao.id is None:
        return None

    ja = db.query(Faturamento).filter(Faturamento.sessao_id == sessao.id).first()
    if ja:
        return None

    preco = (
        db.query(PrecoEspecialidade)
        .filter(
            PrecoEspecialidade.escola_id == sessao.escola_id,
            PrecoEspecialidade.especialidade == sessao.especialidade,
        )
        .first()
    )
    valor = preco.valor if preco else Decimal("0.00")

    data = sessao.data_sessao or datetime.now(timezone.utc)
    competencia = data.strftime("%Y-%m")
    esp = sessao.especialidade.value if hasattr(sessao.especialidade, "value") else sessao.especialidade

    f = Faturamento(
        escola_id=sessao.escola_id,
        paciente_id=sessao.paciente_id,
        sessao_id=sessao.id,
        convenio_id=None,
        competencia=competencia,
        valor=valor,
        status=StatusFaturamento.A_FATURAR,
        observacao="Sessao %s" % esp,
        criado_por_id=criado_por_id,
        criado_em=datetime.now(timezone.utc),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f
