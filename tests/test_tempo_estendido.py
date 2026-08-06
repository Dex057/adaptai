"""
Testes da acomodacao de tempo estendido em provas (TC-151).

A regra mora em app/api/routes/student_provas.py::calcular_tempo_efetivo e le a
acomodacao de Student.profile_data (JSON), sem coluna dedicada. Estes testes
cobrem o contrato: quem tem acomodacao ganha tempo, quem nao tem fica igual, e
valores estranhos no JSON nunca reduzem o tempo do aluno.
"""
from types import SimpleNamespace

from app.api.routes.student_provas import (
    calcular_tempo_efetivo,
    FATOR_TEMPO_ESTENDIDO_PADRAO,
)


def aluno(profile_data):
    """Stub minimo - calcular_tempo_efetivo so le .profile_data do Student."""
    return SimpleNamespace(profile_data=profile_data)


class TestSemAcomodacao:
    def test_perfil_nulo_mantem_tempo_da_prova(self):
        assert calcular_tempo_efetivo(aluno(None), 60) == (False, 60)

    def test_perfil_vazio_mantem_tempo_da_prova(self):
        assert calcular_tempo_efetivo(aluno({}), 60) == (False, 60)

    def test_flag_false_mantem_tempo_da_prova(self):
        assert calcular_tempo_efetivo(aluno({"tempo_estendido": False}), 60) == (False, 60)

    def test_perfil_com_outras_chaves_nao_ativa_acomodacao(self):
        perfil = {"learning_style": "visual", "support_level": "medium"}
        assert calcular_tempo_efetivo(aluno(perfil), 60) == (False, 60)

    def test_profile_data_nao_dict_nao_quebra(self):
        # Dado legado/corrompido no JSON nao pode derrubar a prova do aluno.
        assert calcular_tempo_efetivo(aluno("string invalida"), 60) == (False, 60)


class TestComAcomodacao:
    def test_flag_booleana_aplica_fator_padrao(self):
        estendido, minutos = calcular_tempo_efetivo(aluno({"tempo_estendido": True}), 60)
        assert estendido is True
        assert minutos == int(60 * FATOR_TEMPO_ESTENDIDO_PADRAO)  # 90

    def test_fator_explicito_tem_precedencia_sobre_a_flag(self):
        perfil = {"tempo_estendido": True, "fator_tempo_estendido": 2}
        assert calcular_tempo_efetivo(aluno(perfil), 60) == (True, 120)

    def test_fator_fracionario_arredonda(self):
        # 45 * 1.5 = 67.5 -> 68 (arredondamento, nao truncamento: nunca tirar
        # tempo de quem tem direito a acomodacao).
        assert calcular_tempo_efetivo(aluno({"tempo_estendido": True}), 45) == (True, 68)


class TestValoresInvalidos:
    def test_fator_menor_que_um_nao_reduz_o_tempo(self):
        # Uma acomodacao nunca pode ENCURTAR a prova.
        assert calcular_tempo_efetivo(aluno({"fator_tempo_estendido": 0.5}), 60) == (False, 60)

    def test_fator_booleano_nao_e_tratado_como_numero(self):
        # Em Python True == 1: sem a checagem explicita de bool, isso viraria
        # fator 1 silenciosamente em vez de cair para o flag/padrao.
        assert calcular_tempo_efetivo(aluno({"fator_tempo_estendido": True}), 60) == (False, 60)

    def test_fator_nao_numerico_cai_para_a_flag(self):
        perfil = {"fator_tempo_estendido": "muito", "tempo_estendido": True}
        assert calcular_tempo_efetivo(aluno(perfil), 60) == (True, 90)


class TestProvaSemLimiteDeTempo:
    def test_limite_none_nao_tem_o_que_estender(self):
        assert calcular_tempo_efetivo(aluno({"tempo_estendido": True}), None) == (False, None)

    def test_limite_zero_nao_tem_o_que_estender(self):
        assert calcular_tempo_efetivo(aluno({"tempo_estendido": True}), 0) == (False, None)
