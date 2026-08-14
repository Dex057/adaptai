"""
Leitura de redacoes respondidas no papel (MODO PAPEL).

Claude Vision transcreve o texto manuscrito da redacao - NAO corrige. A correcao
por competencias do ENEM e feita depois por redacao_ai_service.corrigir_redacao_enem,
sempre APOS revisao humana (professor). Reusa os helpers de prova_folha_service.

Regra do projeto: o prompt controla comportamento de IA; a saida e sempre revisada
por um humano antes de virar nota.
"""
import base64
from typing import Dict, Any

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger
from app.services.prova_folha_service import _parse_json, _media_type

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)

_PROMPT = (
    "Voce le uma REDACAO manuscrita por um aluno e transcreve fielmente o texto,\n"
    "SEM corrigir ortografia, gramatica ou pontuacao, e SEM completar nada.\n"
    "Mantenha a divisao em paragrafos. Se algum trecho estiver ilegivel, transcreva\n"
    "o que der e sinalize em \"observacoes\".\n\n"
    "Se houver um codigo no cabecalho no formato RA-000000, informe em\n"
    "\"codigo_folha_detectado\".\n\n"
    "Responda APENAS com JSON valido, sem markdown:\n"
    "{\n"
    "  \"codigo_folha_detectado\": \"RA-000000 ou null\",\n"
    "  \"texto\": \"texto completo da redacao, com quebras de linha entre paragrafos\",\n"
    "  \"observacoes\": \"trechos ilegiveis, folha cortada, etc.\"\n"
    "}"
)


@tm.feature(F.REDACAO_PAPEL)
def transcrever_redacao(image_bytes: bytes, content_type: str) -> Dict[str, Any]:
    """Le a foto/scan da redacao e devolve o texto transcrito (NAO corrige).

    Retorna dict: {codigo_folha_detectado, texto, observacoes}.
    """
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    media = _media_type(content_type)
    is_pdf = media == "application/pdf"

    client = get_anthropic_client(timeout=120.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document" if is_pdf else "image",
                    "source": {"type": "base64", "media_type": media, "data": b64},
                },
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )
    texto_bruto = message.content[0].text if message.content else ""
    dados = _parse_json(texto_bruto)
    if not isinstance(dados, dict) or "texto" not in dados:
        logger.warning("Transcricao de redacao sem 'texto' JSON; usando texto cru.")
        dados = {
            "codigo_folha_detectado": None,
            "texto": (texto_bruto or "").strip(),
            "observacoes": "",
        }
    return dados
