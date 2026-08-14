"""
Testes das funcoes puras do modo papel (leitura da folha).

Cobrem o parser de JSON da IA (que precisa aguentar markdown/preambulo) e a
montagem do prompt. Nao chamam a IA nem o banco - sao deterministicos.
Rodar: pytest tests/test_prova_folha_service.py
"""
from app.services.prova_folha_service import _parse_json, _montar_prompt


def test_parse_json_limpo():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_com_cerca_markdown():
    assert _parse_json('```json\n{"respostas": []}\n```') == {"respostas": []}


def test_parse_json_com_preambulo_e_postambulo():
    assert _parse_json('Claro, aqui esta:\n{"x": 2}\nfim.') == {"x": 2}


def test_parse_json_invalido_volta_dict_vazio():
    assert _parse_json('nao tem json aqui') == {}
    assert _parse_json('') == {}


def test_montar_prompt_distingue_objetiva_de_dissertativa():
    questoes = [
        {"numero": 1, "tipo": "multipla_escolha", "opcoes": ["A) sol", "B) lua"]},
        {"numero": 2, "tipo": "dissertativa", "opcoes": None},
    ]
    p = _montar_prompt(questoes)
    assert "Questao 1 (objetiva)" in p
    assert "A) sol | B) lua" in p
    assert "Questao 2 (dissertativa)" in p
    # a instrucao central: nunca corrigir, so transcrever
    assert "NAO corrija" in p
