"""
Normalizacao de saida da IA (2026-08-11)
========================================

Problema que isto resolve: em alguns fluxos a Anthropic devolvia uma STRING
contendo JSON (as vezes embrulhada em cercas ```json), o valor era gravado como
veio em `resultado_json`, e o frontend acabava exibindo JSON cru para o ALUNO.

A correcao definitiva e aqui, no backend: se o dado sai limpo da API, nenhum
cliente (web, mobile, integracao futura) precisa repetir a defesa.
Existe uma rede de seguranca equivalente no frontend
(adaptai-frontend/src/utils/conteudoIA.js), necessaria apenas por causa do
conteudo torto que ja esta gravado no banco.

Uso:

    from app.services.ai_output import normalizar_saida_ia

    bruto = client.messages.create(...)          # texto da resposta
    resultado = normalizar_saida_ia(bruto, contexto="mapa_mental")
"""

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ```json ... ```  ou  ``` ... ```
_CERCA = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def normalizar_saida_ia(bruto: Any, *, contexto: str = "") -> Dict[str, Any]:
    """
    Devolve SEMPRE um dict pronto para o frontend renderizar.

    Trata os quatro formatos que aparecem na pratica:

      1. dict ja parseado            -> passa direto
      2. lista                       -> {"itens": [...]}
      3. string com JSON (com ou sem cerca ```json) -> parse
      4. prosa livre / JSON invalido -> {"_raw": texto, "_formato": "texto"}

    O caso 4 e o mais importante: em vez de deixar a string vazar para a tela,
    marcamos explicitamente como texto e o viewer a renderiza como paragrafo.
    """
    if isinstance(bruto, dict):
        return bruto
    if isinstance(bruto, list):
        return {"itens": bruto}
    if bruto is None:
        return {}
    if not isinstance(bruto, str):
        return {"_raw": str(bruto), "_formato": "desconhecido"}

    texto = bruto.strip()
    if not texto:
        return {}

    m = _CERCA.match(texto)
    if m:
        texto = m.group(1).strip()

    try:
        parsed = json.loads(texto)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"itens": parsed}
        # JSON valido mas escalar ("texto", 42, true)
        return {"_raw": str(parsed), "_formato": "texto"}
    except json.JSONDecodeError:
        pass

    # Ultimo recurso: recorta do primeiro { ao ultimo } — cobre o caso de o
    # modelo escrever "Claro! Aqui esta: { ... } Espero ter ajudado."
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini != -1 and fim > ini:
        try:
            parsed = json.loads(texto[ini:fim + 1])
            if isinstance(parsed, dict):
                logger.info(
                    "Saida de IA recuperada por recorte de chaves",
                    extra={"contexto": contexto},
                )
                return parsed
        except json.JSONDecodeError:
            pass

    # Nao e JSON. Nao e erro fatal — mas precisa aparecer no log para virar
    # ajuste de prompt em vez de passar despercebido.
    logger.warning(
        "Saida de IA nao parseavel como JSON - devolvida como texto",
        extra={"contexto": contexto, "preview": texto[:200]},
    )
    return {"_raw": bruto, "_formato": "texto"}


def eh_texto_livre(conteudo: Any) -> bool:
    """True quando normalizar_saida_ia desistiu e marcou o conteudo como texto."""
    return isinstance(conteudo, dict) and conteudo.get("_formato") == "texto"
