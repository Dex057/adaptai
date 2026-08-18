"""
Testes da Biblioteca de Materiais (model `Material`).

Cobrem duas rodadas de correcao que se encontraram no mesmo codigo:

17/08 (migration 012, ja no main) - CONTEUDO EM DISCO EFEMERO. O HTML/JSON
gerado so existia em storage/materiais/{id}.*; o Railway roda em disco efemero
e perdia o arquivo a cada redeploy, com a linha ainda marcada 'disponivel'.
Passou a viver em `Material.conteudo_gerado`, lido por
services/material_conteudo.ler_conteudo().

18/08 - O PESO DESSA COLUNA NA LISTAGEM. `GET /materiais/` fazia
`db.query(Material)` (todas as colunas, agora incluindo um LONGTEXT com o
material inteiro) e ainda chamava `len(material.materiais_alunos)` por item -
uma query por material. Com colunas grandes no SELECT + ORDER BY, o MySQL
responde "1038 Out of sort memory", que e exatamente como o historico de
materiais adaptados caiu em producao. Aqui seriam 100 materiais completos por
pagina para montar uma lista de cards.

Estrategia igual a tests/test_student_materiais_adaptados.py: sqlite em
memoria, app minimo com os routers sob teste e override das dependencias.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.models  # noqa: F401 - registra todos os models no metadata
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.material import Material, MaterialAluno, TipoMaterial, StatusMaterial
from app.core.security import create_access_token
from app.api.dependencies import get_current_active_user
from app.api.routes import materiais, student_materiais
from app.services import material_conteudo


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(eng)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Schema nao montavel em sqlite: {e}")
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture(scope="module")
def TestSession(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture(scope="module")
def seed(TestSession):
    """Um professor, dois alunos e um material de cada tipo relevante."""
    db = TestSession()
    try:
        prof = User(name="Prof", email="prof_bib@test.com", hashed_password="x",
                    role=UserRole.TEACHER, is_active=True)
        db.add(prof)
        db.commit()
        db.refresh(prof)

        alunos = [
            Student(name=f"Aluno {i}", grade_level="5o ano",
                    email=f"aluno_bib_{i}@test.com",
                    created_by_user_id=prof.id, is_active=True)
            for i in (1, 2)
        ]
        db.add_all(alunos)
        db.commit()
        for a in alunos:
            db.refresh(a)

        visual = Material(
            titulo="Fotossintese", conteudo_prompt="explique fotossintese",
            tipo=TipoMaterial.VISUAL, materia="Biologia", serie_nivel="8o ano",
            status=StatusMaterial.DISPONIVEL, criado_por_id=prof.id,
            conteudo_gerado="<h1>Fotossintese</h1>", arquivo_path="1.html",
        )
        resumo = Material(
            titulo="Fracoes", conteudo_prompt="resuma fracoes",
            tipo=TipoMaterial.RESUMO, materia="Matematica", serie_nivel="5o ano",
            status=StatusMaterial.DISPONIVEL, criado_por_id=prof.id,
            conteudo_gerado="<h2>Fracoes</h2>", arquivo_path="2.html",
        )
        mapa = Material(
            titulo="Brasil Colonia", conteudo_prompt="mapa do periodo colonial",
            tipo=TipoMaterial.MAPA_MENTAL, materia="Historia", serie_nivel="7o ano",
            status=StatusMaterial.DISPONIVEL, criado_por_id=prof.id,
            conteudo_gerado=json.dumps({"titulo": "Brasil Colonia", "nos": []}),
            arquivo_path="3.json",
        )
        db.add_all([visual, resumo, mapa])
        db.commit()
        for m in (visual, resumo, mapa):
            db.refresh(m)

        # visual vai para os dois alunos; resumo so para o primeiro
        db.add_all([
            MaterialAluno(material_id=visual.id, aluno_id=alunos[0].id),
            MaterialAluno(material_id=visual.id, aluno_id=alunos[1].id),
            MaterialAluno(material_id=resumo.id, aluno_id=alunos[0].id),
        ])
        db.commit()

        ma_resumo = (
            db.query(MaterialAluno)
            .filter(MaterialAluno.material_id == resumo.id)
            .first()
        )

        return {
            "prof_id": prof.id,
            "visual_id": visual.id,
            "resumo_id": resumo.id,
            "mapa_id": mapa.id,
            "ma_resumo_id": ma_resumo.id,
            "token_aluno": create_access_token({"sub": f"student:{alunos[0].email}"}),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession, seed):
    app = FastAPI()
    app.include_router(materiais.router)
    app.include_router(student_materiais.router)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        db = TestSession()
        try:
            return db.query(User).filter(User.id == seed["prof_id"]).first()
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_user
    return TestClient(app)


class TestConteudoNoBanco:
    """O conteudo tem que sobreviver a um deploy - ou seja, morar no banco."""

    def test_html_volta_da_coluna(self, TestSession, seed):
        db = TestSession()
        try:
            m = db.query(Material).get(seed["visual_id"])
            assert material_conteudo.ler_conteudo(m) == ("html", "<h1>Fotossintese</h1>")
        finally:
            db.close()

    def test_mapa_mental_volta_como_dict(self, TestSession, seed):
        db = TestSession()
        try:
            m = db.query(Material).get(seed["mapa_id"])
            # No banco e texto; para quem le, dict.
            assert isinstance(m.conteudo_gerado, str)
            formato, conteudo = material_conteudo.ler_conteudo(m)
            assert formato == "json"
            assert conteudo == {"titulo": "Brasil Colonia", "nos": []}
        finally:
            db.close()

    def test_coluna_e_deferred(self, TestSession, db_engine, seed):
        """
        `conteudo_gerado` nao pode entrar num SELECT que a listagem faz.

        E um LONGTEXT com o material inteiro: num ORDER BY com 100 linhas, e a
        receita do "1038 Out of sort memory". O deferred no model e a rede de
        seguranca para qualquer query nova que use a entidade.
        """
        capturadas = []

        @event.listens_for(db_engine, "before_cursor_execute")
        def _capturar(conn, cursor, statement, params, context, executemany):
            capturadas.append(statement)

        db = TestSession()
        try:
            db.query(Material).filter(Material.criado_por_id == seed["prof_id"]).all()
        finally:
            db.close()
            event.remove(db_engine, "before_cursor_execute", _capturar)

        assert capturadas
        assert not any("conteudo_gerado" in s for s in capturadas), (
            f"conteudo_gerado entrou no SELECT da entidade: {capturadas}"
        )


class TestListagem:
    def test_lista_traz_todos_os_materiais_do_professor(self, client, seed):
        r = client.get("/materiais/?size=100")
        assert r.status_code == 200
        corpo = r.json()
        ids = [m["id"] for m in corpo["items"]]
        assert set(ids) == {seed["visual_id"], seed["resumo_id"], seed["mapa_id"]}
        assert corpo["meta"]["total"] == 3

    def test_total_alunos_vem_do_group_by(self, client, seed):
        """Contagem correta sem uma query por material (N+1)."""
        r = client.get("/materiais/?size=100")
        por_id = {m["id"]: m for m in r.json()["items"]}
        assert por_id[seed["visual_id"]]["total_alunos"] == 2
        assert por_id[seed["resumo_id"]]["total_alunos"] == 1
        assert por_id[seed["mapa_id"]]["total_alunos"] == 0

    def test_listagem_nao_seleciona_o_conteudo_no_sql(self, client, db_engine):
        """
        O ponto do 1038: a coluna grande nao pode entrar no SELECT que ordena.

        Verificar so a resposta nao bastaria - a versao anterior tambem nao
        devolvia o conteudo ao cliente, mas o MySQL ja tinha carregado tudo.
        """
        capturadas = []

        @event.listens_for(db_engine, "before_cursor_execute")
        def _capturar(conn, cursor, statement, params, context, executemany):
            capturadas.append(statement)

        try:
            assert client.get("/materiais/?size=100").status_code == 200
        finally:
            event.remove(db_engine, "before_cursor_execute", _capturar)

        selects = [s for s in capturadas if "FROM materiais" in s]
        assert selects
        assert not any("conteudo_gerado" in s for s in selects), (
            f"conteudo_gerado voltou para o SELECT da listagem: {selects}"
        )

    def test_listagem_faz_poucas_queries(self, client, db_engine, seed):
        """
        Antes eram 2 + uma por material (len(material.materiais_alunos)).
        Agora: COUNT + pagina + contagem agrupada.
        """
        capturadas = []

        @event.listens_for(db_engine, "before_cursor_execute")
        def _capturar(conn, cursor, statement, params, context, executemany):
            capturadas.append(statement)

        try:
            assert client.get("/materiais/?size=100").status_code == 200
        finally:
            event.remove(db_engine, "before_cursor_execute", _capturar)

        queries_materiais = [s for s in capturadas if "materiais" in s]
        assert len(queries_materiais) <= 3, (
            f"{len(queries_materiais)} queries para listar 3 materiais "
            f"(N+1 de volta?): {queries_materiais}"
        )

    def test_filtro_por_tipo(self, client, seed):
        r = client.get("/materiais/?tipo=resumo")
        assert r.status_code == 200
        assert [m["id"] for m in r.json()["items"]] == [seed["resumo_id"]]


class TestConteudoPelaRota:
    def test_professor_le_html_do_banco(self, client, seed):
        r = client.get(f"/materiais/{seed['visual_id']}/conteudo")
        assert r.status_code == 200
        assert r.json()["conteudo"] == "<h1>Fotossintese</h1>"

    def test_professor_le_mapa_mental_como_json(self, client, seed):
        r = client.get(f"/materiais/{seed['mapa_id']}/conteudo")
        assert r.status_code == 200
        assert r.json()["tipo"] == "json"
        assert r.json()["conteudo"]["titulo"] == "Brasil Colonia"

    def test_material_sem_conteudo_da_404(self, client, TestSession, seed):
        """Linha antiga cujo arquivo sumiu do disco efemero: 404, nao 500."""
        db = TestSession()
        try:
            orfao = Material(
                titulo="Sem conteudo", conteudo_prompt="x", tipo=TipoMaterial.VISUAL,
                materia="Artes", status=StatusMaterial.DISPONIVEL,
                criado_por_id=seed["prof_id"], arquivo_path="999999.html",
            )
            db.add(orfao)
            db.commit()
            db.refresh(orfao)
            orfao_id = orfao.id
        finally:
            db.close()

        assert client.get(f"/materiais/{orfao_id}/conteudo").status_code == 404


class TestPortalDoAluno:
    def test_aluno_abre_material_de_tipo_texto(self, client, seed):
        """Antes: 501 para resumo/texto_simplificado/roteiro_estudo/atividades."""
        r = client.get(
            f"/student/materiais/{seed['ma_resumo_id']}/visualizar",
            headers={"Authorization": f"Bearer {seed['token_aluno']}"},
        )
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["conteudo_tipo"] == "html"
        assert corpo["conteudo"] == "<h2>Fracoes</h2>"


class TestGeracaoEmBackground:
    """O caminho completo: gerar -> gravar na linha -> status disponivel."""

    @pytest.fixture(autouse=True)
    def _sem_disco(self, monkeypatch, TestSession):
        """
        Storage em no-op: o teste valida a persistencia NO BANCO, e escrever em
        storage/materiais/ durante a suite sujaria o repositorio.
        """
        monkeypatch.setattr(materiais, "SessionLocal", TestSession)
        monkeypatch.setattr(
            materiais.storage_service, "salvar_html",
            lambda material_id, conteudo: f"{material_id}.html",
        )
        monkeypatch.setattr(
            materiais.storage_service, "salvar_json",
            lambda material_id, conteudo: f"{material_id}.json",
        )

    def _criar_material(self, TestSession, seed, tipo, titulo):
        db = TestSession()
        try:
            novo = Material(
                titulo=titulo, conteudo_prompt="explique",
                tipo=tipo, materia="Portugues",
                status=StatusMaterial.GERANDO, criado_por_id=seed["prof_id"],
            )
            db.add(novo)
            db.commit()
            db.refresh(novo)
            return novo.id
        finally:
            db.close()

    def test_conteudo_gerado_vai_para_o_banco(self, TestSession, seed, monkeypatch):
        novo_id = self._criar_material(
            TestSession, seed, TipoMaterial.TEXTO_SIMPLIFICADO, "Verbos"
        )
        monkeypatch.setattr(
            materiais.material_service, "gerar_material_texto",
            lambda **kw: {"success": True, "html": "<p>Verbos</p>", "tokens_used": 10},
        )

        materiais.gerar_material_background(novo_id)

        db = TestSession()
        try:
            m = db.query(Material).get(novo_id)
            assert m.status == StatusMaterial.DISPONIVEL
            assert m.conteudo_gerado == "<p>Verbos</p>"
        finally:
            db.close()

    def test_falha_de_geracao_marca_erro_sem_conteudo(self, TestSession, seed, monkeypatch):
        novo_id = self._criar_material(
            TestSession, seed, TipoMaterial.VISUAL, "Cinetica"
        )
        monkeypatch.setattr(
            materiais.material_service, "gerar_material_visual",
            lambda **kw: {"success": False, "error": "resposta cortada"},
        )

        materiais.gerar_material_background(novo_id)

        db = TestSession()
        try:
            m = db.query(Material).get(novo_id)
            assert m.status == StatusMaterial.ERRO
            assert m.conteudo_gerado is None
            assert "cortada" in json.dumps(m.metadados)
        finally:
            db.close()


class TestRegenerar:
    def test_versao_anterior_e_arquivada_com_o_conteudo_inline(
        self, client, TestSession, seed, monkeypatch
    ):
        """
        O historico nao pode depender do arquivo em disco (que some no
        redeploy): a versao arquivada leva o conteudo junto.
        """
        db = TestSession()
        try:
            m = Material(
                titulo="Ciclo da agua", conteudo_prompt="explique o ciclo",
                tipo=TipoMaterial.RESUMO, materia="Ciencias",
                status=StatusMaterial.DISPONIVEL, criado_por_id=seed["prof_id"],
                conteudo_gerado="<p>versao 1</p>", arquivo_path="50.html",
            )
            db.add(m)
            db.commit()
            db.refresh(m)
            mat_id = m.id
        finally:
            db.close()

        monkeypatch.setattr(materiais, "SessionLocal", TestSession)
        monkeypatch.setattr(
            materiais.storage_service, "salvar_html",
            lambda material_id, conteudo: f"{material_id}.html",
        )
        monkeypatch.setattr(
            materiais.material_service, "gerar_material_texto",
            lambda **kw: {"success": True, "html": "<p>versao 2</p>", "tokens_used": 10},
        )

        r = client.post(f"/materiais/{mat_id}/regenerar")
        assert r.status_code == 200

        db = TestSession()
        try:
            m = db.query(Material).get(mat_id)
            assert m.versao == 2
            assert m.historico_versoes[0]["versao"] == 1
            assert m.historico_versoes[0]["conteudo"] == "<p>versao 1</p>"
            # A BackgroundTask do TestClient roda antes da resposta voltar.
            assert m.conteudo_gerado == "<p>versao 2</p>"
            assert m.status == StatusMaterial.DISPONIVEL
        finally:
            db.close()
