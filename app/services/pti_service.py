"""
Servico de sugestao de PTI por IA (vertical CLINICA).

A partir de um CONTEXTO CLINICO em texto (resumo do laudo, avaliacao inicial,
observacoes da equipe), a IA sugere um conjunto de OBJETIVOS/METAS terapeuticas
por especialidade — um rascunho de Plano Terapeutico Individual. Segue a regra
do projeto: a IA rascunha; o profissional revisa, ajusta e aplica.

Nao passamos nome do paciente a IA (minimizacao). A saida e JSON estruturado,
no mesmo estilo dos demais servicos de IA do projeto.
"""
import json
from typing import Any, Dict, List, Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)

ESPECIALIDADES = [
    "PSICOLOGIA_ABA", "FONOAUDIOLOGIA", "TERAPIA_OCUPACIONAL", "PSICOPEDAGOGIA",
    "FISIOTERAPIA", "MUSICOTERAPIA", "NUTRICAO", "NEUROPEDIATRIA", "OUTRO",
]


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


def _montar_prompt(contexto: str, especialidades: Optional[List[str]]) -> str:
    alvo = especialidades or ESPECIALIDADES
    lista = ", ".join(alvo)
    return (
        "Voce apoia uma equipe multidisciplinar que atende criancas/adolescentes\n"
        "com TEA. A partir do CONTEXTO CLINICO abaixo, proponha de 4 a 8 OBJETIVOS\n"
        "terapeuticos, distribuidos entre as especialidades indicadas. Baseie-se\n"
        "APENAS no contexto; NAO invente diagnostico, NAO cite nome de pessoa.\n\n"
        "Especialidades permitidas (use EXATAMENTE estes rotulos): " + lista + "\n\n"
        "CONTEXTO CLINICO:\n" + (contexto or "").strip() + "\n\n"
        "Cada objetivo deve ser observavel e mensuravel (estilo SMART) e ter um\n"
        "criterio de mastery (ex.: \"80% de independencia em 3 sessoes seguidas\").\n\n"
        "Responda APENAS com JSON valido, sem markdown, neste formato:\n"
        "{\n"
        "  \"objetivos\": [\n"
        "    {\"especialidade\": \"FONOAUDIOLOGIA\",\n"
        "     \"descricao\": \"...\",\n"
        "     \"criterio_mastery\": \"...\"}\n"
        "  ]\n"
        "}"
    )


@tm.feature(F.PTI_RASCUNHO)
def sugerir_objetivos(
    contexto: str,
    especialidades: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Devolve {'objetivos': [{especialidade, descricao, criterio_mastery}]}.
    Nunca persiste. Filtra especialidades invalidas para OUTRO."""
    if not (contexto or "").strip():
        return {"objetivos": []}
    prompt = _montar_prompt(contexto, especialidades)
    client = get_anthropic_client(timeout=90.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = message.content[0].text if message.content else ""
    dados = _parse_json(texto)
    objetivos = dados.get("objetivos") if isinstance(dados, dict) else None
    if not isinstance(objetivos, list):
        logger.warning("Sugestao de PTI sem 'objetivos'. Inicio: %s", (texto or "")[:300])
        return {"objetivos": []}

    limpos = []
    for o in objetivos:
        if not isinstance(o, dict):
            continue
        esp = str(o.get("especialidade", "")).upper()
        if esp not in ESPECIALIDADES:
            esp = "OUTRO"
        desc = str(o.get("descricao", "")).strip()
        if not desc:
            continue
        limpos.append({
            "especialidade": esp,
            "descricao": desc,
            "criterio_mastery": str(o.get("criterio_mastery", "")).strip() or None,
        })
    return {"objetivos": limpos}
