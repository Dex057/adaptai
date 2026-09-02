"""
Sintese de generalizacao nos 3 ambientes (clinica + casa + escola) por IA.

Le o desempenho do mesmo paciente na clinica (objetivos/PTI), em casa (programa
de casa) e na escola (PEI), e a IA aponta se os ganhos estao GENERALIZANDO entre
os ambientes + recomenda acoes. "IA sugere, humano decide". Sem nome de paciente.
"""
import json
import re
from typing import Any, Dict, List

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)


def _bloco_clinica(itens: List[Dict[str, Any]]) -> str:
    if not itens:
        return "- (sem objetivos clinicos)"
    out = []
    for o in itens:
        pct = o.get("pct_ultimo")
        out.append("- %s [%s]%s" % (
            (o.get("descricao") or "").strip(), o.get("status") or "",
            (" — ultimo %s%%" % pct) if pct is not None else " — sem coleta",
        ))
    return "\n".join(out)


def _bloco_casa(casa: Dict[str, Any]) -> str:
    itens = casa.get("itens") or []
    if not itens:
        return "- (sem programa de casa)"
    return "\n".join("- %s — feito %s/7 dias" % ((t.get("titulo") or "").strip(), t.get("feitos_7d", 0)) for t in itens)


def _bloco_escola(escola: Dict[str, Any]) -> str:
    if not escola.get("vinculado"):
        return "- (aluno nao vinculado a escola / sem PEI)"
    objs = escola.get("objetivos") or []
    if not objs:
        return "- (aluno vinculado, PEI sem objetivos)"
    out = []
    for o in objs:
        pct = o.get("pct")
        out.append("- %s [%s]%s" % (
            (o.get("titulo") or o.get("area") or "").strip(), o.get("status") or "",
            (" — %s%%" % pct) if pct is not None else "",
        ))
    return "\n".join(out)


def _montar_prompt(clinica, casa, escola) -> str:
    return (
        "Voce e um supervisor de terapia ABA para criancas/adolescentes com TEA.\n"
        "Compare o desempenho do MESMO paciente em tres ambientes e avalie se os\n"
        "ganhos estao GENERALIZANDO entre eles. Baseie-se APENAS nos dados. Nao\n"
        "invente, nao cite nome de paciente, nao faca diagnostico.\n\n"
        "CLINICA (objetivos do PTI):\n" + _bloco_clinica(clinica) + "\n\n"
        "CASA (programa de casa, ultimos 7 dias):\n" + _bloco_casa(casa) + "\n\n"
        "ESCOLA (objetivos do PEI):\n" + _bloco_escola(escola) + "\n\n"
        "Responda SOMENTE com JSON valido, sem markdown, no formato:\n"
        '{\"sintese\": \"<2-3 frases: onde ha generalizacao e onde ha lacuna>\", '
        '\"acoes\": [\"<acao pratica de generalizacao>\", \"<outra>\", \"<outra>\"]}'
    )


def _parse(texto: str) -> Dict[str, Any]:
    t = (texto or "").strip()
    t = re.sub(r"^```(json)?|```$", "", t, flags=re.MULTILINE).strip()
    a = t.find("{"); b = t.rfind("}")
    if a != -1 and b != -1 and b > a:
        t = t[a:b + 1]
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        return {}


@tm.feature(F.CLINICA_GENERALIZACAO)
def sintetizar(clinica, casa, escola) -> Dict[str, Any]:
    prompt = _montar_prompt(clinica, casa, escola)
    client = get_anthropic_client(timeout=60.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = message.content[0].text if message.content else ""
    data = _parse(texto)
    acoes = data.get("acoes")
    if not isinstance(acoes, list):
        acoes = []
    return {
        "sintese": (data.get("sintese") or "").strip() or None,
        "acoes": [str(a).strip() for a in acoes if str(a).strip()][:5],
    }
