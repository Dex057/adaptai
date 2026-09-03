"""
Servico de geracao de HISTORIA SOCIAL por IA (vertical CLINICA).

A partir de um tema (ex.: "esperar a vez", "escovar os dentes"), a IA escreve
uma historia social curta em 1a pessoa, frase a frase, cada uma com um termo
para buscar pictograma ARASAAC. O router resolve os pictogramas e a familia/
equipe transforma numa prancha tipo HISTORIA_SOCIAL.

Regra do projeto: a IA rascunha; o profissional revisa antes de usar. Nao passa
nome do paciente para a IA.
"""
import json
from typing import Any, Dict

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)


def _parse_json(texto: str) -> dict:
    bruto = (texto or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(bruto)
    except Exception:
        ini, fim = bruto.find("{"), bruto.rfind("}")
        if ini != -1 and fim != -1 and fim > ini:
            try:
                return json.loads(bruto[ini:fim + 1])
            except Exception:
                pass
    return {}


def _montar_prompt(tema: str) -> str:
    return (
        "Voce escreve HISTORIAS SOCIAIS para criancas com TEA — textos curtos, em\n"
        "1a pessoa, positivos e concretos, que explicam uma situacao e o\n"
        "comportamento esperado. NAO cite nome de pessoa.\n\n"
        "Tema: " + (tema or "").strip() + "\n\n"
        "Escreva de 5 a 8 frases curtas (uma ideia por frase). Para cada frase,\n"
        "sugira um TERMO de 1-2 palavras para buscar um pictograma que a ilustre.\n\n"
        "Responda APENAS com JSON valido, sem markdown, neste formato:\n"
        "{\n"
        "  \"titulo\": \"...\",\n"
        "  \"frases\": [ {\"texto\": \"...\", \"termo\": \"...\"} ]\n"
        "}"
    )


@tm.feature(F.HISTORIA_SOCIAL)
def gerar_historia(tema: str) -> Dict[str, Any]:
    """Devolve {'titulo': str, 'frases': [{'texto','termo'}]}. Nunca persiste."""
    if not (tema or "").strip():
        return {"titulo": "", "frases": []}
    prompt = _montar_prompt(tema)
    client = get_anthropic_client(timeout=90.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = message.content[0].text if message.content else ""
    dados = _parse_json(texto)
    frases = dados.get("frases") if isinstance(dados, dict) else None
    if not isinstance(frases, list):
        logger.warning("Historia social sem 'frases'. Inicio: %s", (texto or "")[:200])
        return {"titulo": (dados.get("titulo") if isinstance(dados, dict) else "") or "", "frases": []}
    limpas = []
    for f in frases:
        if isinstance(f, dict) and str(f.get("texto", "")).strip():
            limpas.append({
                "texto": str(f["texto"]).strip(),
                "termo": str(f.get("termo", "")).strip(),
            })
    return {"titulo": (dados.get("titulo") or tema).strip(), "frases": limpas}
