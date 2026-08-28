"""
Guarda-corpo: nenhum `messages.create(...)` pode passar um kwarg que o SDK
anthropic instalado nao aceita.

CONTEXTO (2026-08-28): `requirements.txt` pinava so o piso (`anthropic>=0.39.0`).
Um redeploy puxou uma versao nova do SDK, que removeu `temperature` da assinatura
de `Messages.create()`. Toda geracao de IA passou a morrer com
`TypeError: got an unexpected keyword argument 'temperature'` -- em producao, na
primeira chamada, sem nenhum aviso em build ou deploy.

Este teste le o codigo por AST e confere cada kwarg contra a assinatura REAL do
SDK que esta instalado. Roda em milissegundos, nao chama a API, nao gasta credito,
e pega o proximo parametro que a Anthropic remover -- nao so `temperature`.
"""
import ast
import inspect
from pathlib import Path

import anthropic
import pytest

RAIZ = Path(__file__).resolve().parent.parent / "app"


def _kwargs_aceitos() -> set[str]:
    sig = inspect.signature(anthropic.resources.messages.Messages.create)
    if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
        pytest.skip("SDK aceita **kwargs: assinatura nao restringe nada")
    return set(sig.parameters) - {"self"}


def _chamadas_messages_create():
    """(arquivo, linha, kwargs) de cada `<algo>.messages.create(...)` em app/."""
    for arquivo in RAIZ.rglob("*.py"):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            func = no.func
            # casa `.messages.create(...)` em qualquer receptor
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "create"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "messages"
            ):
                nomes = {kw.arg for kw in no.keywords if kw.arg is not None}
                yield arquivo.relative_to(RAIZ.parent), no.lineno, nomes


def test_nenhum_kwarg_desconhecido_em_messages_create():
    aceitos = _kwargs_aceitos()
    problemas = [
        f"{arquivo}:{linha} passa {sorted(usados - aceitos)}"
        for arquivo, linha, usados in _chamadas_messages_create()
        if usados - aceitos
    ]
    assert not problemas, (
        "kwargs nao suportados pelo SDK anthropic "
        f"{anthropic.__version__}:\n  " + "\n  ".join(problemas)
    )


def test_o_teste_enxerga_as_chamadas():
    """Se o AST parar de casar as chamadas, o teste acima passa vazio e nao guarda nada."""
    assert list(_chamadas_messages_create()), "nenhuma chamada messages.create encontrada em app/"
