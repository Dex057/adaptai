"""
Campo de lista que a IA devolve como texto corrido nao pode derrubar a prova.

O que estava quebrado: a IA devolveu `criterios_avaliacao` como um paragrafo em
vez de array. `provas.py` grava o valor cru numa Column(JSON) (que aceita
qualquer coisa) e o ValidationError so estourava quando o FastAPI serializava
`response_model=ProvaResponse` — depois do commit e fora do try/except da rota.
Efeito: a prova ficava gravada e ilegivel, com 500 em /gerar, GET /{id} e
PATCH /{id}, para sempre.

Terceira reincidencia da mesma classe (`numero` e `resposta_correta` cairam em
2026-08-11), por isso a normalizacao vive no schema e vale para todos os campos
de lista, e nao so no campo da vez.
"""
from datetime import datetime

import pytest

from app.schemas.prova import QuestaoGeradaResponse, QuestaoParaAluno

CRITERIO = (
    "Atribuir 0,5 ponto para cada resposta correta dos itens a e b "
    "(incluindo nome da posicao e valor)."
)


def _questao(**extra):
    base = dict(
        id=1, prova_id=1, numero=5, enunciado="Qual o valor posicional?",
        tipo="dissertativa", pontuacao=1.0, criado_em=datetime.now(),
    )
    base.update(extra)
    return base


def test_texto_corrido_vira_lista_de_um_item():
    """O caso que quebrou em producao: prosa onde o schema pede List[str]."""
    q = QuestaoGeradaResponse(**_questao(criterios_avaliacao=CRITERIO))
    assert q.criterios_avaliacao == [CRITERIO], "o criterio nao pode ser descartado"


def test_lista_passa_intacta():
    """Toda prova que funciona hoje precisa continuar identica."""
    q = QuestaoGeradaResponse(**_questao(criterios_avaliacao=["a", "b"]))
    assert q.criterios_avaliacao == ["a", "b"]


def test_none_continua_none():
    q = QuestaoGeradaResponse(**_questao(criterios_avaliacao=None))
    assert q.criterios_avaliacao is None


def test_lista_serializada_como_string_json_e_desempacotada():
    """A IA as vezes devolve o array dentro de aspas."""
    q = QuestaoGeradaResponse(**_questao(criterios_avaliacao='["um", "dois"]'))
    assert q.criterios_avaliacao == ["um", "dois"]


def test_string_vazia_nao_vira_item_em_branco():
    q = QuestaoGeradaResponse(**_questao(criterios_avaliacao="   "))
    assert q.criterios_avaliacao is None


@pytest.mark.parametrize("campo", ["opcoes", "tags"])
def test_campos_irmaos_tambem_protegidos(campo):
    """`opcoes` e `tags` sao gravados igualmente crus e tinham o mesmo defeito."""
    q = QuestaoGeradaResponse(**_questao(**{campo: "texto solto"}))
    assert getattr(q, campo) == ["texto solto"]


def test_opcoes_na_prova_do_aluno():
    """`opcoes` chega ao aluno em QuestaoParaAluno — quebrar aqui e pior."""
    q = QuestaoParaAluno(
        id=1, numero=1, enunciado="x", tipo="multipla_escolha",
        opcoes="A) unica", pontuacao=1.0,
    )
    assert q.opcoes == ["A) unica"]
