"""
Sanitizacao de SVG vindo da IA.

POR QUE ISTO EXISTE
-------------------
As atividades de geometria (material_service.gerar_atividade_geometria) pedem
ao Claude a FIGURA em SVG, e o frontend precisa injetar esse SVG no DOM para
que a figura apareca (nao da pra desenhar um triangulo com angulos corretos
usando <img> de um modelo de difusao — ver o docstring do service).

Injetar markup de terceiros no DOM e uma superficie de XSS classica. Ainda que
o texto venha do Claude e nao do usuario, quem escolhe o PROMPT e o professor:
um enunciado malicioso pode tentar induzir o modelo a devolver
`<svg><script>...</script></svg>` ou `onload="..."`. Confiar no modelo aqui
seria confiar em quem escreve o enunciado.

ESTRATEGIA: allowlist, nao blocklist.
Tudo o que nao estiver explicitamente permitido (tag ou atributo) e descartado.
Blocklist envelhece mal — sempre aparece um vetor novo (`<foreignObject>` com
HTML dentro, `xlink:href="javascript:"`, `<use href="#...">`, `style` com
`url()`, entidades...). Com allowlist, um vetor novo simplesmente nao passa,
porque nunca esteve na lista.

O que fica de fora de proposito:
  - script, style, foreignObject, image, use, a, animate*, set, handler
  - QUALQUER atributo on* (onload, onclick, ...)
  - href / xlink:href (nenhuma referencia externa ou a javascript:)
  - style="" (aceita url(...) e expressoes em alguns motores)

O resultado e um SVG puramente geometrico: formas, linhas, textos e transformes.
"""
from __future__ import annotations

import re
from typing import Optional
from xml.etree import ElementTree as ET

from app.core.logging_config import get_logger

logger = get_logger(__name__)

_SVG_NS = "http://www.w3.org/2000/svg"

# Tags permitidas (sem namespace). Qualquer outra e removida COM a subarvore.
_TAGS_PERMITIDAS = {
    "svg", "g", "defs", "title", "desc",
    "path", "line", "polyline", "polygon", "rect", "circle", "ellipse",
    "text", "tspan",
    "marker", "linearGradient", "radialGradient", "stop", "pattern",
}

# Atributos permitidos. Cobre geometria, apresentacao e o minimo de tipografia.
_ATTRS_PERMITIDOS = {
    # estrutura / identidade
    "id", "class", "viewBox", "width", "height", "xmlns", "preserveAspectRatio",
    # geometria
    "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "points", "dx", "dy", "transform", "pathLength",
    # apresentacao
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "opacity",
    "stroke-dasharray", "stroke-dashoffset", "stroke-linecap", "stroke-linejoin",
    "stroke-opacity", "stroke-miterlimit", "vector-effect", "shape-rendering",
    # tipografia (rotulos: "A", "B", "5 cm", "60°")
    "font-size", "font-family", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "alignment-baseline", "letter-spacing",
    # marcadores e gradientes (setas de medida, preenchimento suave)
    "marker-start", "marker-mid", "marker-end", "markerWidth", "markerHeight",
    "markerUnits", "refX", "refY", "orient", "offset", "stop-color",
    "stop-opacity", "gradientUnits", "patternUnits", "spreadMethod",
}

# Teto de tamanho: uma figura geometrica honesta cabe folgado em 40KB. Acima
# disso e ruido do modelo (ou tentativa de inflar o payload do material).
_TAMANHO_MAXIMO = 40_000


def _nome_local(tag: str) -> str:
    """Remove o namespace de '{http://...}circle' -> 'circle'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag else tag


def _limpar(elemento: ET.Element) -> None:
    """Poda recursiva in-place: remove filhos e atributos fora da allowlist."""
    permitidos = {}
    for chave, valor in elemento.attrib.items():
        nome = _nome_local(chave)
        # on* nunca passa, mesmo que por acaso batesse com a allowlist.
        if nome.lower().startswith("on"):
            continue
        if nome not in _ATTRS_PERMITIDOS:
            continue
        # Nenhum valor de atributo pode carregar URL/expressao executavel.
        if re.search(r"(javascript:|data:text/html|<|&#)", valor, re.IGNORECASE):
            continue
        permitidos[nome] = valor
    elemento.attrib = permitidos

    for filho in list(elemento):
        if _nome_local(filho.tag) not in _TAGS_PERMITIDAS:
            elemento.remove(filho)
            continue
        _limpar(filho)


def sanitizar_svg(svg: Optional[str], *, max_bytes: int = _TAMANHO_MAXIMO) -> Optional[str]:
    """Devolve um SVG seguro para injetar no DOM, ou None se nao der para
    aproveitar nada (SVG ausente, mal formado ou grande demais).

    Devolver None e um resultado legitimo: o viewer do frontend mostra a
    descricao textual da figura no lugar (mesmo fallback de quando a geracao
    da figura falha).
    """
    if not svg or not svg.strip():
        return None

    texto = svg.strip()

    # A IA costuma devolver dentro de cerca markdown mesmo quando o prompt pede
    # SVG puro. Tira a cerca antes de tentar parsear.
    texto = re.sub(r"^```(?:svg|xml|html)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto).strip()

    # Recorta do primeiro <svg ate o ultimo </svg>: descarta qualquer prosa
    # ("Aqui esta a figura:") e tambem prologo XML/DOCTYPE — e no DOCTYPE que
    # moram as entidades customizadas (billion laughs).
    inicio = texto.lower().find("<svg")
    fim = texto.lower().rfind("</svg>")
    if inicio == -1 or fim == -1:
        return None
    texto = texto[inicio:fim + len("</svg>")]

    if len(texto.encode("utf-8")) > max_bytes:
        logger.warning("SVG da IA descartado por tamanho (%d bytes)", len(texto))
        return None

    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as exc:
        logger.warning("SVG da IA descartado: XML invalido (%s)", exc)
        return None

    if _nome_local(raiz.tag) != "svg":
        return None

    _limpar(raiz)

    # viewBox e o que faz a figura escalar dentro do card do frontend. Sem ela,
    # width/height fixos em px estouram o layout no celular.
    if "viewBox" not in raiz.attrib:
        largura = raiz.attrib.get("width", "400")
        altura = raiz.attrib.get("height", "300")
        so_numero = re.compile(r"^\d+(\.\d+)?$")
        if so_numero.match(largura) and so_numero.match(altura):
            raiz.set("viewBox", f"0 0 {largura} {altura}")
        else:
            raiz.set("viewBox", "0 0 400 300")

    # width/height fixos brigam com o container responsivo — quem manda no
    # tamanho e o CSS do viewer.
    raiz.attrib.pop("width", None)
    raiz.attrib.pop("height", None)
    # xmlns NAO entra em attrib: quando o SVG original ja declarava o
    # namespace, o ElementTree o reemite sozinho e o resultado sairia com
    # xmlns duplicado (markup invalido). Conferimos na string final.
    raiz.attrib.pop("xmlns", None)

    ET.register_namespace("", _SVG_NS)
    limpo = ET.tostring(raiz, encoding="unicode")

    # ElementTree prefixa 'ns0:' quando o documento original declarava o
    # namespace SVG; register_namespace resolve na maioria dos casos, mas a
    # limpeza abaixo garante que nunca sobre prefixo no markup entregue.
    limpo = limpo.replace("ns0:", "").replace(":ns0", "")

    if "xmlns=" not in limpo:
        limpo = limpo.replace("<svg", f'<svg xmlns="{_SVG_NS}"', 1)
    return limpo
