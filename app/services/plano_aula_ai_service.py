"""
AdaptAI - Servico de IA para Plano de aula simples (superficie mobile).

Gera UMA aula (objetivo, sequencia, adaptacoes por perfil, avaliacao) alinhada a
BNCC e ao Desenho Universal para a Aprendizagem (DUA). Diferente do
planejamento_bncc_service (que gera PEI anual por aluno).

Conteudo reutilizavel entre professores -> usa o cache de IA (cached_completion).
"""
from typing import List, Optional

from app.services.ai_cache_service import cached_completion


class PlanoAulaAIService:
    """Servico de IA para plano de aula simples."""

    def gerar(
        self,
        componente: str,
        tema: Optional[str] = None,
        duracao: Optional[str] = "1 aula",
        serie: Optional[str] = None,
        perfis: Optional[List[str]] = None,
    ) -> str:
        tema_txt = (tema or "").strip() or "um tema central do componente"
        serie_txt = (serie or "").strip() or "ensino fundamental"
        perfis_txt = ", ".join(perfis) if perfis else "turma inclusiva com diferentes perfis de apoio"

        prompt = f"""Voce e um(a) professor(a) especialista em educacao inclusiva no Brasil.
Crie UM plano de aula curto e pratico, alinhado a BNCC e ao Desenho Universal para a Aprendizagem (DUA).

Componente: {componente}
Tema: {tema_txt}
Serie/ano: {serie_txt}
Duracao: {duracao}
Perfis na turma: {perfis_txt}

Escreva em portugues do Brasil, em markdown, EXATAMENTE com estas secoes (use "## "):
## Objetivo (BNCC)
## Sequencia da aula
## Adaptacoes por perfil
## Avaliacao

Regras:
- Em "Sequencia da aula" e "Adaptacoes por perfil", use itens iniciados por "- ".
- Linguagem clara e acionavel. Sem preambulo nem fechamento fora das secoes."""

        return cached_completion(
            prompt=prompt,
            max_tokens=1200,
            cache_type="plano_aula_simples",
            use_cache=True,
        )


# Instancia global do servico (mesmo padrao dos demais services)
plano_aula_ai_service = PlanoAulaAIService()
