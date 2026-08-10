"""
TC-129 - regra unica de "prazo da meta vencido" no PEI.

O calculo nasceu inline em `GET /pei/{pei_id}/completo` e existia so ali: o
resumo do PEI, a listagem por aluno e o Portal do Aluno mostravam a data crua e
nada mais, entao a mesma meta aparecia como atrasada em uma tela e neutra em
outra. Centralizar aqui evita que as telas voltem a divergir.
"""
from datetime import date, datetime, timezone
from typing import Optional


def prazo_vencido(prazo: Optional[date], status: Optional[str]) -> bool:
    """
    Meta vencida = tem prazo definido, o prazo ja passou e ela nao foi atingida.

    Meta atingida nunca conta como vencida, mesmo entregue depois do prazo - o
    que interessa ao professor e o que ainda precisa de acao.
    """
    if not prazo:
        return False
    return prazo < datetime.now(timezone.utc).date() and status != "atingido"


def contar_vencidos(objetivos) -> int:
    """Quantos objetivos da colecao estao com prazo vencido."""
    return sum(1 for o in objetivos if prazo_vencido(o.prazo, o.status))
