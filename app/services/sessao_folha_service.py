"""
Servico de leitura de FOLHA DE SESSAO (MODO PAPEL clinico).

Espelha prova_folha_service.py: o terapeuta imprime a folha de registro (metas
+ bolhas de tentativa), marca a mao durante o atendimento, fotografa e envia.
O Claude Vision LE a foto e transcreve, por meta, quantas tentativas/acertos e o
nivel de ajuda. NAO calcula mastery, NAO decide nada: a saida e SEMPRE revisada
por um humano antes de virar registro (confirmar), como no Modo Papel de provas.

Reaproveita os helpers de visao (_parse_json, _media_type) no mesmo formato.
"""
import base64
import json
from typing import Any, Dict, List

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)

MEDIA_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "application/pdf": "application/pdf",
}

NIVEIS_AJUDA = [
    "INDEPENDENTE", "AJUDA_VERBAL", "AJUDA_GESTUAL",
    "AJUDA_FISICA_PARCIAL", "AJUDA_FISICA_TOTAL",
]


def _media_type(content_type: str) -> str:
    return MEDIA_TYPES.get((content_type or "").lower(), "image/jpeg")


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


def _montar_prompt(objetivos: List[Dict[str, Any]]) -> str:
    linhas = []
    for o in objetivos:
        linhas.append("Meta id=%s: %s" % (o.get("id"), (o.get("descricao") or "").strip()))
    descricao = "\n".join(linhas) if linhas else "(nenhuma meta na folha)"
    return (
        "Voce le FOLHAS DE REGISTRO DE SESSAO terapeutica preenchidas a mao e\n"
        "transcreve fielmente as marcacoes. NAO calcule, NAO avalie, NAO invente.\n"
        "Se algo estiver ilegivel ou em branco, diga isso.\n\n"
        "A folha tem estas metas:\n"
        + descricao +
        "\n\nPara CADA meta, extraia das marcacoes:\n"
        "- \"tentativas\": numero total de tentativas registradas (inteiro);\n"
        "- \"acertos\": numero de acertos/respostas independentes (inteiro);\n"
        "- \"nivel_ajuda\": um de " + ", ".join(NIVEIS_AJUDA) + " (ou \"\" se nao marcado);\n"
        "- \"confianca\": \"alta\", \"media\" ou \"baixa\".\n"
        "Se houver um codigo no cabecalho no formato SE-000000, informe em\n"
        "\"codigo_folha_detectado\".\n\n"
        "Responda APENAS com JSON valido, sem markdown, neste formato:\n"
        "{\n"
        "  \"codigo_folha_detectado\": \"SE-000000 ou null\",\n"
        "  \"registros\": [\n"
        "    {\"objetivo_id\": 1, \"tentativas\": 10, \"acertos\": 6,\n"
        "     \"nivel_ajuda\": \"AJUDA_VERBAL\", \"confianca\": \"alta\", \"obs\": \"\"}\n"
        "  ],\n"
        "  \"observacoes\": \"folha cortada, borrada, etc.\"\n"
        "}"
    )


@tm.feature(F.SESSAO_FOLHA_LEITURA)
def transcrever_folha_sessao(
    image_bytes: bytes,
    content_type: str,
    objetivos: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Le a foto/scan da folha de sessao e devolve a transcricao estruturada
    (NAO persiste, NAO calcula mastery). Formato: {codigo_folha_detectado,
    registros: [...], observacoes}."""
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    media = _media_type(content_type)
    is_pdf = media == "application/pdf"
    prompt = _montar_prompt(objetivos)

    client = get_anthropic_client(timeout=120.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document" if is_pdf else "image",
                    "source": {"type": "base64", "media_type": media, "data": b64},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    texto = message.content[0].text if message.content else ""
    dados = _parse_json(texto)
    if not isinstance(dados, dict) or "registros" not in dados:
        logger.warning("Folha de sessao sem 'registros'. Inicio: %s", texto[:300])
        dados = {
            "codigo_folha_detectado": None,
            "registros": [],
            "observacoes": "IA nao retornou o formato esperado.",
        }
    return dados
