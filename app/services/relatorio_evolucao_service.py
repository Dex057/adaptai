"""
Servico de RELATORIO DE EVOLUCAO consolidado por IA (vertical CLINICA).

Junta as evolucoes ASSINADAS de um paciente num periodo e a IA redige um
rascunho de relatorio consolidado (para escola/convenio/familia). Segue a regra
do projeto: a IA rascunha; o profissional revisa, completa a identificacao e
assina. Nao passamos nome do paciente a IA (minimizacao); o cabecalho de
identificacao e responsabilidade do profissional.
"""
from typing import Any, Dict, List, Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)


def _linhas(evolucoes: List[Dict[str, Any]]) -> str:
    linhas = []
    for e in evolucoes:
        data = (e.get("data") or "")[:10]
        esp = e.get("especialidade") or ""
        texto = (e.get("texto") or "").strip()
        cabec = "[%s%s]" % (data, (" · " + esp) if esp else "")
        linhas.append("%s %s" % (cabec, texto))
    return "\n\n".join(linhas) if linhas else "(sem evolucoes assinadas no periodo)"


def _montar_prompt(evolucoes: List[Dict[str, Any]], periodo: Optional[str]) -> str:
    per = ("Periodo: %s\n" % periodo) if periodo else ""
    return (
        "Voce e assistente de uma equipe que atende criancas/adolescentes com TEA.\n"
        "A partir das notas de evolucao ASSINADAS abaixo, redija um RASCUNHO de\n"
        "RELATORIO DE EVOLUCAO consolidado, em portugues, tom clinico e objetivo.\n"
        "Baseie-se APENAS no material fornecido. NAO invente, NAO cite nome do\n"
        "paciente, NAO faca diagnostico novo.\n\n"
        + per +
        "Notas de evolucao (por data/especialidade):\n"
        + _linhas(evolucoes) + "\n\n"
        "Estruture o relatorio em: (1) sintese do periodo; (2) evolucao por area/\n"
        "especialidade; (3) avancos e pontos de atencao; (4) encaminhamentos/\n"
        "sugestoes. Seja conciso (250-400 palavras). Responda SOMENTE com o texto\n"
        "do relatorio (sem cabecalho de identificacao, que o profissional preenche)."
    )


@tm.feature(F.RELATORIO_EVOLUCAO_CLINICO)
def gerar_relatorio_consolidado(
    evolucoes: List[Dict[str, Any]],
    periodo: Optional[str] = None,
) -> str:
    """Devolve o TEXTO do rascunho de relatorio consolidado. Nunca persiste."""
    if not evolucoes:
        return ("Nao ha evolucoes assinadas no periodo selecionado para consolidar. "
                "Assine as evolucoes das sessoes e gere novamente.")
    prompt = _montar_prompt(evolucoes, periodo)
    client = get_anthropic_client(timeout=90.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = (message.content[0].text if message.content else "") or ""
    texto = texto.strip()
    if not texto:
        logger.warning("Relatorio consolidado vazio da IA.")
        texto = "(A IA nao retornou texto. Redija o relatorio manualmente.)"
    return texto
