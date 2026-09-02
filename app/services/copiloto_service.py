"""
Copiloto de decisao clinica por IA (vertical CLINICA).

A partir dos DADOS OBJETIVOS de um objetivo terapeutico (descricao, criterio de
mastery, linha de base, status e a serie de sessoes: %, acertos/tentativas,
nivel de ajuda, fase), a IA sugere a PROXIMA ACAO no programa.

Principio do projeto: "IA sugere, humano decide". Minimizacao de dado: NAO
recebe nome de paciente; trabalha so com a meta e os numeros.
"""
import json
import re
from typing import Any, Dict, List, Optional

from app.core.anthropic_client import get_anthropic_client, get_default_model
from app.core.logging_config import get_logger

import tokenmeter as tm
from app.core.features import F

logger = get_logger(__name__)

ACOES = ["AVANCAR", "REDUZIR_AJUDA", "MANTER", "MUDAR_PROCEDIMENTO", "GENERALIZAR", "REVER_CRITERIO"]


def _serie_txt(serie: List[Dict[str, Any]]) -> str:
    linhas = []
    for p in serie:
        data = p.get("data") or "?"
        pct = p.get("percentual_independencia")
        ac = p.get("acertos"); tent = p.get("tentativas")
        nivel = p.get("nivel_ajuda") or ""
        fase = p.get("fase") or ""
        met = []
        if pct is not None:
            met.append("%s%%" % pct)
        if ac is not None and tent is not None:
            met.append("%s/%s" % (ac, tent))
        if nivel:
            met.append("ajuda:%s" % nivel)
        if fase:
            met.append("fase:%s" % fase)
        linhas.append("- %s: %s" % (str(data)[:10], ", ".join(met) if met else "sem dados"))
    return "\n".join(linhas) if linhas else "- (sem registros)"


def _montar_prompt(descricao, criterio, linha_base, status, serie) -> str:
    crit = ("Criterio de mastery: %s\n" % criterio) if criterio else ""
    lb = ("Linha de base: %s%%\n" % linha_base) if linha_base is not None else ""
    st = ("Status atual do objetivo: %s\n" % status) if status else ""
    return (
        "Voce e um supervisor de terapia ABA para criancas/adolescentes com TEA.\n"
        "Analise a evolucao de UM objetivo terapeutico e recomende a PROXIMA ACAO\n"
        "no programa, baseado APENAS nos dados abaixo. Nao invente fatos, nao cite\n"
        "nome de paciente, nao faca diagnostico medico.\n\n"
        "Objetivo/programa: %s\n" % (descricao or "(sem descricao)")
        + crit + lb + st +
        "\nSerie das sessoes (mais antiga -> mais recente):\n"
        + _serie_txt(serie) + "\n\n"
        "Escolha UMA recomendacao entre estas chaves EXATAS:\n"
        "AVANCAR (criterio atingido, avancar de fase/alvo),\n"
        "REDUZIR_AJUDA (bom desempenho, reduzir nivel de prompt),\n"
        "MANTER (progredindo, manter o procedimento),\n"
        "MUDAR_PROCEDIMENTO (estagnado, revisar estrategia/antecedentes/reforco),\n"
        "GENERALIZAR (dominado; programar generalizacao para casa/escola),\n"
        "REVER_CRITERIO (dados insuficientes ou criterio inadequado).\n\n"
        "Responda SOMENTE com um JSON valido, sem markdown, no formato:\n"
        '{\"recomendacao\": \"<CHAVE>\", \"titulo\": \"<3-6 palavras>\", '
        '\"justificativa\": \"<1-2 frases citando os numeros>\", '
        '\"proxima_acao\": \"<acao concreta e pratica>\", \"confianca\": <0.0-1.0>}'
    )


def _parse_json(texto: str) -> Dict[str, Any]:
    t = (texto or "").strip()
    t = re.sub(r"^```(json)?|```$", "", t, flags=re.MULTILINE).strip()
    ini = t.find("{"); fim = t.rfind("}")
    if ini != -1 and fim != -1 and fim > ini:
        t = t[ini:fim + 1]
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        return {}


@tm.feature(F.CLINICA_COPILOTO)
def sugerir_proxima_acao(
    descricao: Optional[str],
    criterio: Optional[str],
    linha_base: Optional[float],
    status: Optional[str],
    serie: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Devolve dict {recomendacao, titulo, justificativa, proxima_acao, confianca}."""
    prompt = _montar_prompt(descricao, criterio, linha_base, status, serie)
    client = get_anthropic_client(timeout=60.0, max_retries=2)
    message = client.messages.create(
        model=get_default_model(),
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = message.content[0].text if message.content else ""
    data = _parse_json(texto)
    rec = data.get("recomendacao")
    if rec not in ACOES:
        rec = "MANTER"
    conf = data.get("confianca")
    try:
        conf = round(float(conf), 2)
        conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = None
    return {
        "recomendacao": rec,
        "titulo": (data.get("titulo") or "").strip() or None,
        "justificativa": (data.get("justificativa") or "").strip() or None,
        "proxima_acao": (data.get("proxima_acao") or "").strip() or None,
        "confianca": conf,
    }
