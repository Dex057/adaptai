"""
Servico de leitura de folhas de prova respondidas no papel (MODO PAPEL).

O professor imprime a folha (ver rota folha-impressao), o aluno responde a mao,
o professor fotografa e envia. Aqui o Claude Vision LE a foto e transcreve, por
questao, o que o aluno marcou/escreveu - reaproveitando o mesmo mecanismo de
visao ja usado para laudos em relatorio_processor.py.

IMPORTANTE (regra do projeto): o prompt abaixo controla comportamento de IA e
deve ser validado com poucos exemplos reais antes de ser considerado estavel.
A saida e SEMPRE revisada por um humano (professor) antes de virar nota - esta
etapa nunca corrige sozinha.
"""
import base64
import json
from typing import List, Dict, Any

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


def _montar_prompt(questoes: List[Dict[str, Any]]) -> str:
    linhas = []
    for q in questoes:
        numero = q.get("numero")
        opcoes = q.get("opcoes")
        if opcoes:
            ops = " | ".join(str(o) for o in opcoes)
            linhas.append("Questao %s (objetiva): opcoes -> %s" % (numero, ops))
        else:
            linhas.append("Questao %s (dissertativa): resposta escrita a mao" % numero)
    descricao_questoes = "\n".join(linhas)

    return (
        "Voce le folhas de prova respondidas a mao por alunos e transcreve\n"
        "fielmente o que esta escrito/marcado. NAO corrija, NAO avalie, NAO invente.\n"
        "Se algo estiver ilegivel ou em branco, diga isso.\n\n"
        "A folha tem estas questoes:\n"
        + descricao_questoes +
        "\n\nINSTRUCOES:\n"
        "- Questao OBJETIVA: identifique a alternativa marcada (bolha preenchida) e\n"
        "  responda com a LETRA (ex: \"A\", \"B\", \"C\", \"D\"). Se marcou mais de uma,\n"
        "  liste todas. Se nenhuma, use \"\" (vazio).\n"
        "- Questao DISSERTATIVA: transcreva EXATAMENTE o texto manuscrito, sem\n"
        "  corrigir ortografia nem completar. Se ilegivel, transcreva o que der e\n"
        "  marque confianca \"baixa\".\n"
        "- Para cada questao informe \"confianca\": \"alta\", \"media\" ou \"baixa\".\n"
        "- Se houver um codigo no cabecalho no formato PA-000000, informe em\n"
        "  \"codigo_folha_detectado\".\n\n"
        "Responda APENAS com JSON valido, sem markdown, neste formato:\n"
        "{\n"
        "  \"codigo_folha_detectado\": \"PA-000000 ou null\",\n"
        "  \"respostas\": [\n"
        "    {\"numero\": 1, \"resposta\": \"B\", \"confianca\": \"alta\", \"obs\": \"\"}\n"
        "  ],\n"
        "  \"observacoes\": \"folha cortada, borrada, etc.\"\n"
        "}"
    )


@tm.feature(F.PROVA_CORRECAO_PAPEL)
def transcrever_folha(
    image_bytes: bytes,
    content_type: str,
    questoes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Le a foto/scan da folha e devolve a transcricao estruturada (NAO corrige).

    Retorna dict: {codigo_folha_detectado, respostas: [...], observacoes}.
    """
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    media = _media_type(content_type)
    is_pdf = media == "application/pdf"
    prompt = _montar_prompt(questoes)

    client = get_anthropic_client(timeout=120.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=3000,
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
    if not isinstance(dados, dict) or "respostas" not in dados:
        logger.warning("Transcricao de folha sem 'respostas'. Inicio: %s", texto[:300])
        dados = {
            "codigo_folha_detectado": None,
            "respostas": [],
            "observacoes": "IA nao retornou o formato esperado.",
        }
    return dados
