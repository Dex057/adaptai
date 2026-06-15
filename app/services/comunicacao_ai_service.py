"""
AdaptAI - Servico de IA para Comunicacao com a familia.

Gera um recado curto e acolhedor aos responsaveis, sem jargao tecnico,
ajustando o tom ao contexto informado pelo professor.

Conteudo unico por situacao -> NAO cacheado (mesmo criterio de
redacao_ai_service / diario_ai_service).

Usa cliente Anthropic centralizado (core/anthropic_client.py).
"""
from typing import Any, Dict, Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model


class ComunicacaoAIService:
    """Servico de IA para mensagens a familia."""

    async def gerar_mensagem_familia(
        self,
        aluno_info: Dict[str, Any],
        tom: str = "Atualizacao do dia",
        nota: Optional[str] = None,
        professor_nome: Optional[str] = None,
    ) -> str:
        nome = (aluno_info.get("nome") or "o estudante").split(" ")[0]
        diagnostico = aluno_info.get("diagnostico") or "nao informado"
        contexto = (nota or "").strip() or "teve um bom dia de modo geral"
        assinatura = professor_nome or "Professor(a)"

        prompt = f"""Voce e um(a) professor(a) de educacao inclusiva no Brasil escrevendo um recado curto pelo aplicativo para a familia de um estudante.

Tom desejado: {tom}.
Estudante: {nome} (perfil: {diagnostico}).
Contexto informado pelo professor: "{contexto}".

Escreva a mensagem em portugues do Brasil:
- comece com "Ola!"
- linguagem simples e calorosa, SEM jargao tecnico nem siglas
- 3 a 5 frases
- termine com abertura para dialogo
- assine como "{assinatura}"

Responda APENAS com o texto da mensagem, sem titulos nem aspas."""

        response = get_anthropic_client().messages.create(
            model=get_default_model(),
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


# Instancia global do servico (mesmo padrao de redacao_ai_service)
comunicacao_ai_service = ComunicacaoAIService()
