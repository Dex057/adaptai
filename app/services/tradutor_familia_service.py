"""
Tradutor clinico -> familia por IA (vertical CLINICA).

Transforma a nota de evolucao (tecnica, assinada) em um resumo curto, caloroso e
em linguagem SIMPLES para os pais/responsaveis verem no portal da familia. O
texto tecnico continua no prontuario; a familia so ve a versao aprovada pelo
profissional (IA rascunha, humano aprova/edita).
"""
from typing import Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)


def _montar_prompt(texto: str, primeiro_nome: Optional[str]) -> str:
    nome = (primeiro_nome or "").strip() or "a crianca"
    return (
        "Voce ajuda uma clinica a se comunicar com os pais de criancas com TEA.\n"
        "Reescreva a nota de evolucao abaixo em um resumo CURTO (2-4 frases), em\n"
        "portugues simples, caloroso e respeitoso, para os responsaveis de %s\n" % nome +
        "entenderem. Sem jargao tecnico, sem siglas, sem diagnostico, sem numeros\n"
        "de porcentagem se puder evitar. Destaque o que a crianca fez bem e um\n"
        "proximo passo, com tom de parceria. NAO invente fatos que nao estejam na\n"
        "nota. Responda SOMENTE com o texto do resumo (sem titulo).\n\n"
        "Nota de evolucao (tecnica):\n" + (texto or "").strip()
    )


@tm.feature(F.EVOLUCAO_FAMILIA)
def traduzir(texto: str, primeiro_nome: Optional[str] = None) -> str:
    prompt = _montar_prompt(texto, primeiro_nome)
    client = get_anthropic_client(timeout=60.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    out = message.content[0].text if message.content else ""
    return (out or "").strip() or None
