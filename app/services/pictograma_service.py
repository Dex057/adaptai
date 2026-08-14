"""
Servico de pictogramas ARASAAC (apoio visual padronizado).

ARASAAC (https://arasaac.org) e a maior biblioteca aberta de pictogramas para
comunicacao aumentativa e apoio a compreensao, referencia em educacao especial
no mundo lusofono/hispanico. Os simbolos sao GRATUITOS (licenca Creative Commons
BY-NC-SA) e a API e publica, sem chave.

Aqui so CONSULTAMOS: buscamos pictogramas por termo (em portugues) e montamos a
URL estatica da imagem no CDN da ARASAAC. Nao copiamos a imagem para o nosso
storage - o registro em `ilustracoes` guarda apenas o arasaac_id e a URL.

Por que um proxy no backend (e nao o front chamando a ARASAAC direto):
  - evita depender de CORS do dominio externo no navegador;
  - deixa um unico ponto para tratar timeout/erro e, no futuro, cache.
"""
from typing import List, Dict, Any
import httpx

from app.core.logging_config import get_logger

logger = get_logger(__name__)

ARASAAC_API = "https://api.arasaac.org/api"
ARASAAC_STATIC = "https://static.arasaac.org/pictograms"

# Idioma padrao dos termos/keywords. A ARASAAC suporta pt (portugues), entre
# varios outros. Mantemos pt-BR mapeado para "pt".
IDIOMA_PADRAO = "pt"

# Tamanhos de imagem que o CDN expoe (px). 500 e um bom meio-termo para tela.
TAMANHO_PADRAO = 500


def url_pictograma(arasaac_id: int, tamanho: int = TAMANHO_PADRAO) -> str:
    """Monta a URL estatica (CDN) de um pictograma pelo id.

    Ex.: url_pictograma(2349) ->
         https://static.arasaac.org/pictograms/2349/2349_500.png
    """
    return "%s/%d/%d_%d.png" % (ARASAAC_STATIC, int(arasaac_id), int(arasaac_id), int(tamanho))


def _normalizar_idioma(idioma: str) -> str:
    """pt-BR / pt_br / PT -> pt. Qualquer outra coisa passa em minusculo."""
    if not idioma:
        return IDIOMA_PADRAO
    base = idioma.strip().lower().replace("_", "-").split("-")[0]
    return base or IDIOMA_PADRAO


def buscar_pictogramas(
    termo: str,
    idioma: str = IDIOMA_PADRAO,
    limite: int = 24,
) -> List[Dict[str, Any]]:
    """Busca pictogramas na ARASAAC por um termo em texto livre.

    Retorna uma lista de dicts prontos para o front:
        [{"arasaac_id": 2349, "keyword": "casa", "url": "https://.../2349_500.png"}]

    Nunca lanca por erro de rede/HTTP: em falha, loga e devolve lista vazia -
    a feature de apoio visual e auxiliar e nao deve derrubar a tela do professor.
    """
    termo = (termo or "").strip()
    if not termo:
        return []

    lang = _normalizar_idioma(idioma)
    url = "%s/pictograms/%s/search/%s" % (ARASAAC_API, lang, termo)

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
        if resp.status_code == 404:
            # A ARASAAC responde 404 quando nao ha resultado para o termo.
            return []
        resp.raise_for_status()
        dados = resp.json()
    except Exception:
        logger.warning("Falha ao buscar pictogramas ARASAAC (termo=%r, lang=%s)", termo, lang, exc_info=True)
        return []

    if not isinstance(dados, list):
        return []

    resultados: List[Dict[str, Any]] = []
    for item in dados[: max(1, int(limite))]:
        pid = item.get("_id") or item.get("id")
        if pid is None:
            continue
        # keywords vem como lista de objetos {"keyword": "...", ...}. Pegamos a
        # primeira como legenda; se faltar, caimos no proprio termo buscado.
        legenda = termo
        kws = item.get("keywords")
        if isinstance(kws, list) and kws:
            primeira = kws[0]
            if isinstance(primeira, dict) and primeira.get("keyword"):
                legenda = primeira["keyword"]
            elif isinstance(primeira, str):
                legenda = primeira
        resultados.append({
            "arasaac_id": int(pid),
            "keyword": legenda,
            "url": url_pictograma(int(pid)),
        })
    return resultados
