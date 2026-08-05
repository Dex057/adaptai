"""
AdaptAI - Servico de IA para feedback FORMATIVO de redacao (superficie mobile).

Diferente de redacao_ai_service (que corrige no padrao ENEM, 5 competencias,
0-1000). Aqui o retorno e curto, acolhedor e formativo, no espirito da escrita
de criancas/adolescentes.

Conteudo unico por texto -> NAO cacheado.
"""
from typing import Any, Dict, Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model

# tokenmeter: atribuicao de consumo de IA (ver app/core/features.py)
import tokenmeter as tm
from app.core.features import F


class RedacaoFeedbackAIService:
    """Servico de IA para feedback formativo de redacao."""

    @tm.feature(F.REDACAO_FEEDBACK)
    async def gerar_feedback(
        self,
        texto: str,
        aluno_info: Optional[Dict[str, Any]] = None,
        foco: Optional[str] = None,
    ) -> str:
        contexto_aluno = ""
        if aluno_info:
            contexto_aluno = (
                f"Estudante: {aluno_info.get('nome', 'nao informado')} "
                f"(serie: {aluno_info.get('serie', 'nao informada')}; "
                f"perfil: {aluno_info.get('diagnostico', 'nao informado')}).\n"
            )
        foco_txt = f"Foco pedido pelo professor: {foco}.\n" if foco else ""

        prompt = f"""Voce e um(a) professor(a) de educacao inclusiva dando um retorno FORMATIVO e acolhedor
sobre a producao escrita de um estudante (NAO use o padrao ENEM nem notas).

{contexto_aluno}{foco_txt}
Texto do estudante:
\"\"\"{texto}\"\"\"

Escreva em portugues do Brasil, em markdown, EXATAMENTE com estas secoes (use "## "):
## O que esta otimo
## Vamos olhar juntos
## Para a proxima

Regras:
- Tom gentil, encorajador e honesto; linguagem adequada a criancas/adolescentes.
- Em "O que esta otimo" e "Vamos olhar juntos", use itens iniciados por "- ".
- Sem notas, sem jargao tecnico, sem preambulo fora das secoes."""

        response = get_anthropic_client().messages.create(
            model=get_default_model(),
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


# Instancia global do servico
redacao_feedback_ai_service = RedacaoFeedbackAIService()
