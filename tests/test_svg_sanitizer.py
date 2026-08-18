"""
Testes de app/services/svg_sanitizer.py.

Estes testes sao a rede de seguranca da atividade de geometria: a figura de
cada exercicio e um SVG escrito pelo Claude e o frontend precisa renderiza-lo.
Quem escolhe o prompt e o professor, entao um enunciado malicioso pode tentar
induzir o modelo a devolver markup executavel. O sanitizador usa allowlist —
o que estes testes verificam e que a allowlist nao vazou.

O modulo nao depende de banco nem de rede, entao roda em qualquer ambiente.
"""
import pytest

from app.services.svg_sanitizer import sanitizar_svg


# --------------------------------------------------------------------------- #
# O que NAO pode passar
# --------------------------------------------------------------------------- #

def test_remove_script():
    limpo = sanitizar_svg(
        '<svg viewBox="0 0 10 10"><script>alert(1)</script>'
        '<circle cx="5" cy="5" r="4"/></svg>'
    )
    assert "script" not in limpo
    assert "circle" in limpo  # o resto da figura sobrevive


@pytest.mark.parametrize("atributo", ["onload", "onclick", "onmouseover", "onerror"])
def test_remove_handlers_inline(atributo):
    limpo = sanitizar_svg(
        f'<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" {atributo}="x()"/></svg>'
    )
    assert atributo not in limpo


def test_remove_referencias_externas():
    """href/xlink:href sao a porta de javascript: e de carregamento externo."""
    limpo = sanitizar_svg(
        '<svg viewBox="0 0 10 10">'
        '<use href="javascript:alert(1)"/>'
        '<a href="http://exemplo.com"><text>clique</text></a>'
        '<image href="http://exemplo.com/x.png"/>'
        "</svg>"
    )
    assert "href" not in limpo
    assert "javascript" not in limpo


def test_remove_foreignobject():
    """foreignObject e HTML arbitrario dentro de SVG."""
    limpo = sanitizar_svg(
        '<svg viewBox="0 0 10 10"><foreignObject>'
        '<div onclick="x()">oi</div></foreignObject></svg>'
    )
    assert "foreignObject" not in limpo
    assert "div" not in limpo


def test_remove_style():
    """style aceita url(...) e expressoes em alguns motores."""
    limpo = sanitizar_svg(
        '<svg viewBox="0 0 10 10">'
        '<rect x="1" y="1" width="2" height="2" style="background:url(javascript:1)"/>'
        "</svg>"
    )
    assert "style" not in limpo


def test_descarta_svg_gigante():
    """Teto de tamanho: figura honesta nao passa de dezenas de KB."""
    enorme = '<svg viewBox="0 0 1 1">' + '<circle cx="1" cy="1" r="1"/>' * 3000 + "</svg>"
    assert sanitizar_svg(enorme) is None


# --------------------------------------------------------------------------- #
# O que PRECISA passar (senao a figura fica inutil)
# --------------------------------------------------------------------------- #

def test_preserva_geometria_e_rotulos():
    limpo = sanitizar_svg(
        '<svg viewBox="0 0 100 100">'
        '<polygon points="10,90 90,90 10,10" fill="none" stroke="#1f2937" stroke-width="2"/>'
        '<text x="5" y="95" font-size="14" text-anchor="middle">A</text>'
        '<text x="50" y="99" font-size="14">5 cm</text>'
        "</svg>"
    )
    assert "polygon" in limpo and 'points="10,90 90,90 10,10"' in limpo
    assert "stroke-width" in limpo
    assert ">A<" in limpo and "5 cm" in limpo
    assert "font-size" in limpo and "text-anchor" in limpo


def test_deriva_viewbox_e_remove_width_height():
    """Sem viewBox a figura nao escala no card; com width/height fixos ela
    estoura o layout no celular."""
    limpo = sanitizar_svg(
        '<svg width="400" height="300"><line x1="0" y1="0" x2="9" y2="9" stroke="#000"/></svg>'
    )
    assert 'viewBox="0 0 400 300"' in limpo
    abertura = limpo.split(">", 1)[0]
    assert "width=" not in abertura and "height=" not in abertura


def test_tira_cerca_markdown_e_prosa():
    """A IA costuma responder com cerca de codigo mesmo quando o prompt proibe."""
    limpo = sanitizar_svg(
        'Aqui esta a figura:\n```svg\n'
        '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>\n```'
    )
    assert limpo.startswith("<svg")
    assert limpo.endswith("</svg>")


def test_xmlns_presente_e_unico():
    """xmlns duplicado e markup invalido; ausente quebra o render."""
    com_ns = sanitizar_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 5 5">'
        '<circle cx="1" cy="1" r="1"/></svg>'
    )
    sem_ns = sanitizar_svg('<svg viewBox="0 0 5 5"><circle cx="1" cy="1" r="1"/></svg>')
    assert com_ns.count("xmlns=") == 1
    assert sem_ns.count("xmlns=") == 1


# --------------------------------------------------------------------------- #
# Entradas degeneradas: None e resposta valida (o viewer cai na descricao)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("entrada", [None, "", "   ", "Nao consegui desenhar.", "<svg><circle</svg>"])
def test_entradas_invalidas_viram_none(entrada):
    assert sanitizar_svg(entrada) is None
