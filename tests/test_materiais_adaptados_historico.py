"""
Testes do historico de materiais adaptados (visao do professor) - 18/08/2026.

Contexto: em producao, GET /materiais-adaptados/historico/student/{id} caiu com

    pymysql.err.OperationalError: (1038, 'Out of sort memory, consider
    increasing server sort buffer size')

A causa nao era o volume de linhas, e sim o TAMANHO delas: a listagem fazia
`db.query(MaterialAdaptadoGerado)` (todas as colunas) e ordenava por
created_at. Desde que hq_tirinha/album_figurinhas passaram a embutir imagens
em base64 no `resultado_json`, cada linha carrega megabytes para o filesort do
MySQL - por causa de um campo que a listagem nem usa.

Alem disso, a aba "Historico" do frontend chamava esse endpoint UMA VEZ POR
ALUNO em paralelo, so para descobrir quem tinha material. O endpoint
/historico/resumo troca isso por um GROUP BY.

Estes testes travam as duas coisas:
  - a listagem nao seleciona nem devolve `resultado_json`;
  - o resumo conta certo, respeita a ordem e nao vaza aluno de outro professor.
"""
from datetime import datetime, timedelta, timezone

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
from app.models.material_adaptado_gerado import MaterialAdaptadoGerado
from app.api.dependencies import get_current_active_user
from app.api.routes import materiais_adaptados


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
    """Professor com 2 alunos (um com 2 materiais, outro sem) + aluno de outro professor."""
    db = TestSession()
    try:
        prof = User(name="Prof", email="prof_hist@test.com", hashed_password="x",
                    role=UserRole.TEACHER, is_active=True)
        outro = User(name="Outro", email="outro_hist@test.com", hashed_password="x",
                     role=UserRole.TEACHER, is_active=True)
        db.add_all([prof, outro])
        db.commit()
        db.refresh(prof)
        db.refresh(outro)

        com_material = Student(name="Com Material", grade_level="5o ano",
                               email="com_hist@test.com",
                               created_by_user_id=prof.id, is_active=True)
        sem_material = Student(name="Sem Material", grade_level="6o ano",
                               email="sem_hist@test.com",
                               created_by_user_id=prof.id, is_active=True)
        alheio = Student(name="Alheio", grade_level="7o ano",
                         email="alheio_hist@test.com",
                         created_by_user_id=outro.id, is_active=True)
        db.add_all([com_material, sem_material, alheio])
        db.commit()
        for a in (com_material, sem_material, alheio):
            db.refresh(a)

        agora = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        antigo = MaterialAdaptadoGerado(
            student_id=com_material.id, disciplina="Matematica", serie="5o ano",
            conteudo="Fracoes", tipos_material=["flashcards"],
            resultado_json={"flashcards": {"cards": ["a" * 100]}},
            created_by=prof.id, created_at=agora - timedelta(days=1),
        )
        recente = MaterialAdaptadoGerado(
            student_id=com_material.id, disciplina="Ciencias", serie="5o ano",
            conteudo="Agua", tipos_material=["hq_tirinha"],
            resultado_json={"hq_tirinha": {"quadrinhos": ["imagem-base64-gigante"]}},
            created_by=prof.id, created_at=agora,
        )
        do_alheio = MaterialAdaptadoGerado(
            student_id=alheio.id, disciplina="Historia", serie="7o ano",
            conteudo="Grecia", tipos_material=["linha_tempo"],
            resultado_json={"linha_tempo": {"eventos": []}},
            created_by=outro.id, created_at=agora,
        )
        db.add_all([antigo, recente, do_alheio])
        db.commit()
        for m in (antigo, recente, do_alheio):
            db.refresh(m)

        return {
            "prof_id": prof.id,
            "com_material_id": com_material.id,
            "sem_material_id": sem_material.id,
            "alheio_id": alheio.id,
            "antigo_id": antigo.id,
            "recente_id": recente.id,
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession, seed):
    app = FastAPI()
    app.include_router(materiais_adaptados.router)

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


class TestListagemDoHistorico:
    def test_lista_os_materiais_do_aluno_do_mais_novo_para_o_mais_antigo(self, client, seed):
        r = client.get(f"/materiais-adaptados/historico/student/{seed['com_material_id']}")
        assert r.status_code == 200
        corpo = r.json()
        assert [m["id"] for m in corpo["items"]] == [seed["recente_id"], seed["antigo_id"]]
        assert corpo["meta"]["total"] == 2
        # chaves legadas que o frontend antigo ainda usa
        assert corpo["total"] == 2
        assert len(corpo["materiais"]) == 2

    def test_listagem_nao_devolve_resultado_json(self, client, seed):
        r = client.get(f"/materiais-adaptados/historico/student/{seed['com_material_id']}")
        item = r.json()["items"][0]
        assert "resultado_json" not in item
        assert "resultado" not in item

    def test_listagem_nao_seleciona_resultado_json_no_sql(self, client, db_engine, seed):
        """
        O ponto do 1038: o campo pesado nao pode entrar no SELECT que ordena.

        Verificar so a resposta nao bastaria - a versao quebrada tambem escondia
        o campo na serializacao, depois de o MySQL ja ter carregado tudo.
        """
        capturadas = []

        @event.listens_for(db_engine, "before_cursor_execute")
        def _capturar(conn, cursor, statement, params, context, executemany):
            capturadas.append(statement)

        try:
            r = client.get(f"/materiais-adaptados/historico/student/{seed['com_material_id']}")
            assert r.status_code == 200
        finally:
            event.remove(db_engine, "before_cursor_execute", _capturar)

        selects = [s for s in capturadas if "materiais_adaptados_gerados" in s]
        assert selects, "nenhuma query na tabela do historico foi capturada"
        assert not any("resultado_json" in s for s in selects), (
            "resultado_json voltou para o SELECT da listagem - "
            f"e o que causava 1038 Out of sort memory: {selects}"
        )

    def test_detalhe_continua_trazendo_o_resultado(self, client, seed):
        """O JSON completo continua disponivel onde ele e realmente necessario."""
        r = client.get(f"/materiais-adaptados/historico/{seed['recente_id']}")
        assert r.status_code == 200
        assert r.json()["resultado"]["hq_tirinha"]["quadrinhos"]

    def test_aluno_de_outro_professor_e_403(self, client, seed):
        r = client.get(f"/materiais-adaptados/historico/student/{seed['alheio_id']}")
        assert r.status_code == 403


class TestResumoDoHistorico:
    def test_conta_materiais_por_aluno_em_uma_chamada(self, client, seed):
        r = client.get("/materiais-adaptados/historico/resumo")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["total_alunos"] == 1
        assert corpo["total_materiais"] == 2
        assert corpo["items"][0]["id"] == seed["com_material_id"]
        assert corpo["items"][0]["total_materiais"] == 2
        assert corpo["items"][0]["name"] == "Com Material"
        assert corpo["items"][0]["grade_level"] == "5o ano"

    def test_omite_aluno_sem_material(self, client, seed):
        r = client.get("/materiais-adaptados/historico/resumo")
        ids = [i["id"] for i in r.json()["items"]]
        assert seed["sem_material_id"] not in ids

    def test_nao_vaza_aluno_de_outro_professor(self, client, seed):
        r = client.get("/materiais-adaptados/historico/resumo")
        ids = [i["id"] for i in r.json()["items"]]
        assert seed["alheio_id"] not in ids

    def test_resumo_nao_carrega_resultado_json(self, client, db_engine):
        capturadas = []

        @event.listens_for(db_engine, "before_cursor_execute")
        def _capturar(conn, cursor, statement, params, context, executemany):
            capturadas.append(statement)

        try:
            assert client.get("/materiais-adaptados/historico/resumo").status_code == 200
        finally:
            event.remove(db_engine, "before_cursor_execute", _capturar)

        assert not any("resultado_json" in s for s in capturadas)

    def test_rota_resumo_nao_e_engolida_pela_rota_de_id(self, client):
        """
        /historico/resumo tem que ser declarada ANTES de /historico/{material_id},
        senao o FastAPI tenta converter "resumo" em int e devolve 422.
        """
        assert client.get("/materiais-adaptados/historico/resumo").status_code == 200
