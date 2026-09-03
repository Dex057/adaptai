"""
Testes dos serviços de IA do vertical CLINICA (com o Anthropic mockado).
Validam parsing de JSON, filtragem e os caminhos de erro — sem chamar a IA real.
"""
from unittest.mock import MagicMock, patch


def _fake_client(text):
    """Cliente Anthropic falso: messages.create() -> objeto com content[0].text."""
    client = MagicMock()
    msg = MagicMock()
    parte = MagicMock()
    parte.text = text
    msg.content = [parte]
    client.messages.create.return_value = msg
    return client


class TestPtiService:
    def test_sugere_e_normaliza_especialidade_invalida(self):
        from app.services import pti_service
        payload = (
            '{"objetivos":[{"especialidade":"FONOAUDIOLOGIA",'
            '"descricao":"Ampliar vocabulario funcional","criterio_mastery":"80% em 3 sessoes"},'
            '{"especialidade":"INEXISTENTE","descricao":"meta X"}]}'
        )
        with patch.object(pti_service, "get_anthropic_client", return_value=_fake_client(payload)), \
             patch.object(pti_service, "get_default_model", return_value="modelo"):
            r = pti_service.sugerir_objetivos("resumo do laudo")
        assert len(r["objetivos"]) == 2
        assert r["objetivos"][0]["especialidade"] == "FONOAUDIOLOGIA"
        assert r["objetivos"][1]["especialidade"] == "OUTRO"  # inválida vira OUTRO

    def test_contexto_vazio_nao_chama_ia(self):
        from app.services import pti_service
        assert pti_service.sugerir_objetivos("   ")["objetivos"] == []


class TestSessaoFolhaService:
    def test_transcreve_registros_com_cerca_markdown(self):
        from app.services import sessao_folha_service
        payload = (
            "```json\n"
            '{"codigo_folha_detectado":"SE-000001","registros":['
            '{"objetivo_id":1,"tentativas":10,"acertos":6,"nivel_ajuda":"AJUDA_VERBAL","confianca":"alta"}],'
            '"observacoes":""}\n```'
        )
        with patch.object(sessao_folha_service, "get_anthropic_client", return_value=_fake_client(payload)), \
             patch.object(sessao_folha_service, "get_default_model", return_value="modelo"):
            r = sessao_folha_service.transcrever_folha_sessao(b"bytes", "image/png", [{"id": 1, "descricao": "meta"}])
        assert r["registros"][0]["acertos"] == 6
        assert r["codigo_folha_detectado"] == "SE-000001"

    def test_json_invalido_retorna_estrutura_vazia(self):
        from app.services import sessao_folha_service
        with patch.object(sessao_folha_service, "get_anthropic_client", return_value=_fake_client("nao veio json")), \
             patch.object(sessao_folha_service, "get_default_model", return_value="modelo"):
            r = sessao_folha_service.transcrever_folha_sessao(b"bytes", "image/png", [])
        assert r["registros"] == []


class TestRelatorioService:
    def test_sem_evolucoes_nao_chama_ia(self):
        from app.services import relatorio_evolucao_service
        txt = relatorio_evolucao_service.gerar_relatorio_consolidado([], None)
        assert "Nao ha evolucoes" in txt

    def test_gera_texto_com_evolucoes(self):
        from app.services import relatorio_evolucao_service
        with patch.object(relatorio_evolucao_service, "get_anthropic_client", return_value=_fake_client("Relatorio consolidado do periodo.")), \
             patch.object(relatorio_evolucao_service, "get_default_model", return_value="modelo"):
            txt = relatorio_evolucao_service.gerar_relatorio_consolidado(
                [{"data": "2026-08-01", "especialidade": "FONOAUDIOLOGIA", "texto": "evoluiu bem"}], "ago/2026")
        assert "consolidado" in txt.lower()


class TestEvolucaoService:
    def test_rascunha_evolucao(self):
        from app.services import evolucao_service
        with patch.object(evolucao_service, "get_anthropic_client", return_value=_fake_client("Nota de evolucao rascunhada.")), \
             patch.object(evolucao_service, "get_default_model", return_value="modelo"):
            txt = evolucao_service.rascunhar_evolucao(
                metas=[{"descricao": "pedir agua", "especialidade": "FONOAUDIOLOGIA",
                        "tentativas": 10, "acertos": 8, "percentual_independencia": 80.0, "nivel_ajuda": "INDEPENDENTE"}],
                especialidade="FONOAUDIOLOGIA", observacao="colaborativo")
        assert "evolucao" in txt.lower()
