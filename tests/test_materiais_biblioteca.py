"""
Testes da Biblioteca de Materiais (model `Material`) - rodada 18/08/2026.

O que estava quebrado, e que estes testes travam:

1. CONTEUDO EM DISCO EFEMERO. O HTML/JSON gerado pela IA so existia em
   backend/storage/materiais/{id}.*; o Railway roda em disco efemero e perdia
   o arquivo a cada redeploy, com a linha ainda marcada 'disponivel'. Para o
   professor, o material "nao persistia". Agora o conteudo mora na linha
   (Material.conteudo) - ver app/services/material_conteudo.py.

2. LISTAGEM PESADA E COM N+1. GET /materiais/ selecionava a entidade inteira
   (com os campos grandes) e chamava len(material.materiais_alunos) por item,
   uma query por material. Com colunas grandes no SELECT + ORDER BY, o MySQL
   respondia "1038 Out of sort memory" e a tela abria com "Nao foi possivel
   carregar os materiais".

3. PORTAL DO ALUNO SO ABRIA 2 DOS 6 TIPOS. resumo/texto_simplificado/
   roteiro_estudo/atividades - gerados na mesma Biblioteca - respondiam 501.

Estrategia igual a tests/test_student_materiais_adaptados.py: sqlite em
memoria, app minimo com os routers sob teste e override das dependencias.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
        )
        resumo = Material(
            titulo="Fracoes", conteudo_prompt="resuma fracoes",
            tipo=TipoMaterial.RESUMO, materia="Matematica", serie_nivel="5o ano",
            status=StatusMaterial.DISPONIVEL, criado_por_id=prof.id,
        )
        mapa = Material(
            titulo="Brasil Colonia", conteudo_prompt="mapa do periodo colonial",
            tipo=TipoMaterial.MAPA_MENTAL, materia="Historia", serie_nivel="7o ano",
            status=StatusMaterial.DISPONIVEL, criado_por_id=prof.id,
        )
        db.add_all([visual, resumo, mapa])
        db.commit()
        for m in (visual, resumo, mapa):
            db.refresh(m)

        material_conteudo.escrever(visual, "<h1>Fotossintese</h1>")
        material_conteudo.escrever(resumo, "<h2>Fracoes</h2>")
        material_conteudo.escrever(mapa, {"titulo": "Brasil Colonia", "nos": []})

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
            "prof_email": prof.email,
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

    def test_html_vai_para_a_coluna_e_volta(self, TestSession, seed):
        db = TestSession()
        try:
            m = db.query(Material).get(seed["visual_id"])
            assert m.conteudo == "<h1>Fotossintese</h1>"
            assert material_conteudo.ler(m) == "<h1>Fotossintese</h1>"
        finally:
            db.close()

    def test_mapa_mental_volta_como_dict(self, TestSession, seed):
        db = TestSession()
        try:
            m = db.query(Material).get(seed["mapa_id"])
            # No banco e texto; para quem le, dict.
            assert isinstance(m.conteudo, str)
            assert material_conteudo.ler(m) == {"titulo": "Brasil Colonia", "nos": []}
        finally:
            db.close()

    def test_arquivo_path_continua_preenchido(self, TestSession, seed):
        """Campo legado segue como marcador de 'ja gerou' (expand/contract)."""
        db = TestSession()
        try:
            assert db.query(Material).get(seed["visual_id"]).arquivo_path.endswith(".html")
            assert db.query(Material).get(seed["mapa_id"]).arquivo_path.endswith(".json")
        finally:
            db.close()

    def test_arquivar_versao_preserva_o_conteudo_atual(self, TestSession, seed):
        db = TestSession()
        try:
            m = db.query(Material).get(seed["resumo_id"])
            assert material_conteudo.arquivar_versao(m, 1) is True
            assert m.conteudo_versoes["1"] == "<h2>Fracoes</h2>"
            # O conteudo atual NAO some ao arquivar: ate a regeneracao terminar,
            # o professor continua vendo a versao anterior.
            assert m.conteudo == "<h2>Fracoes</h2>"
            assert material_conteudo.ler_versao(m, 1) == "<h2>Fracoes</h2>"
            db.rollback()
        finally:
            db.close()


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

    def test_lista_nao_devolve_o_conteudo(self, client, seed):
        """O campo pesado nao entra na listagem (nem no SELECT, nem na resposta)."""
        r = client.get("/materiais/?size=100")
        item = r.json()["items"][0]
        assert "conteudo" not in item
        assert "conteudo_versoes" not in item

    def test_filtro_por_tipo(self, client, seed):
        r = client.get("/materiais/?tipo=resumo")
        assert r.status_code == 200
        assert [m["id"] for m in r.json()["items"]] == [seed["resumo_id"]]


class TestConteudoPelaRota:
    def test_professor_le_html_do_banco(self, client, seed):
        r = client.get(f"/materiais/{seed['visual_id']}/conteudo")
        assert r.status_code == 200
        assert r.json() == {"tipo": "html", "conteudo": "<h1>Fotossintese</h1>"}

    def test_professor_le_mapa_mental_como_json(self, client, seed):
        r = client.get(f"/materiais/{seed['mapa_id']}/conteudo")
        assert r.status_code == 200
        assert r.json()["tipo"] == "json"
        assert r.json()["conteudo"]["titulo"] == "Brasil Colonia"

    def test_material_sem_conteudo_da_404_com_orientacao(self, client, TestSession, seed):
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

        r = client.get(f"/materiais/{orfao_id}/conteudo")
        assert r.status_code == 404
        assert "Regenerar" in r.json()["detail"]


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
    def test_conteudo_gerado_vai_para_o_banco(self, TestSession, seed, monkeypatch):
        """O caminho completo: gerar -> gravar na linha -> status disponivel."""
        db = TestSession()
        try:
            novo = Material(
                titulo="Verbos", conteudo_prompt="explique verbos",
                tipo=TipoMaterial.TEXTO_SIMPLIFICADO, materia="Portugues",
                status=StatusMaterial.GERANDO, criado_por_id=seed["prof_id"],
            )
            db.add(novo)
            db.commit()
            db.refresh(novo)
            novo_id = novo.id
        finally:
            db.close()

        monkeypatch.setattr(materiais, "SessionLocal", TestSession)
        monkeypatch.setattr(
            materiais.material_service, "gerar_material_texto",
            lambda **kw: {"success": True, "html": "<p>Verbos</p>", "tokens_used": 10},
        )

        materiais.gerar_material_background(novo_id)

        db = TestSession()
        try:
            m = db.query(Material).get(novo_id)
            assert m.status == StatusMaterial.DISPONIVEL
            assert m.conteudo == "<p>Verbos</p>"
            assert m.arquivo_path == f"{novo_id}.html"
        finally:
            db.close()

    def test_falha_de_geracao_marca_erro_sem_conteudo(self, TestSession, seed, monkeypatch):
        db = TestSession()
        try:
            novo = Material(
                titulo="Cinetica", conteudo_prompt="explique cinetica",
                tipo=TipoMaterial.VISUAL, materia="Quimica",
                status=StatusMaterial.GERANDO, criado_por_id=seed["prof_id"],
            )
            db.add(novo)
            db.commit()
            db.refresh(novo)
            novo_id = novo.id
        finally:
            db.close()

        monkeypatch.setattr(materiais, "SessionLocal", TestSession)
        monkeypatch.setattr(
            materiais.material_service, "gerar_material_visual",
            lambda **kw: {"success": False, "error": "resposta cortada"},
        )

        materiais.gerar_material_background(novo_id)

        db = TestSession()
        try:
            m = db.query(Material).get(novo_id)
            assert m.status == StatusMaterial.ERRO
            assert m.conteudo is None
            assert "cortada" in json.dumps(m.metadados)
        finally:
            db.close()
