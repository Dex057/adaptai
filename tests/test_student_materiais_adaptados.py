"""
Testes da ponte de materiais adaptados para o Portal do Aluno (TC-027 cluster).

O que estava quebrado: o professor gerava material por POST /materiais-adaptados/gerar
(persistido em `materiais_adaptados_gerados`), mas o Portal do Aluno lia de
`materiais`/`materiais_alunos` - tabelas que aquele pipeline nunca popula. Nada do
que o professor gerava aparecia para o aluno (TC-027/028/031/032/033/081/088/118/
123/124/125). A rota /student/materiais-adaptados/ e a leitura que faltava.

Alem de "o aluno ve o proprio material", estes testes travam o isolamento: como
o filtro por aluno vem do token (e nao de um parametro), material de outro aluno
nao pode vazar - nem pela listagem, nem pelo detalhe.

Estrategia identica a tests/test_idor_ownership.py: sqlite em memoria, app minimo
com o router sob teste e override de get_db.
"""
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
from app.models.material_adaptado_gerado import MaterialAdaptadoGerado
from app.core.security import create_access_token
from app.api.routes import student_materiais_adaptados


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
    """Dois alunos, cada um com material adaptado gerado pelo professor."""
    db = TestSession()
    try:
        prof = User(name="Prof", email="prof_mat@test.com", hashed_password="x",
                    role=UserRole.TEACHER, is_active=True)
        db.add(prof)
        db.commit()
        db.refresh(prof)

        aluno_a = Student(name="Aluno A", grade_level="5o ano", email="aluno_a_mat@test.com",
                          created_by_user_id=prof.id, is_active=True)
        aluno_b = Student(name="Aluno B", grade_level="5o ano", email="aluno_b_mat@test.com",
                          created_by_user_id=prof.id, is_active=True)
        db.add_all([aluno_a, aluno_b])
        db.commit()
        db.refresh(aluno_a)
        db.refresh(aluno_b)

        mat_a = MaterialAdaptadoGerado(
            student_id=aluno_a.id, disciplina="Matematica", serie="5o ano",
            conteudo="Fracoes", tipos_material=["resumo_estruturado", "flashcards"],
            resultado_json={"resumo_estruturado": {"titulo": "Fracoes"}}, created_by=prof.id,
        )
        mat_b = MaterialAdaptadoGerado(
            student_id=aluno_b.id, disciplina="Historia", serie="5o ano",
            conteudo="Brasil Colonia", tipos_material=["linha_tempo"],
            resultado_json={"linha_tempo": {"eventos": []}}, created_by=prof.id,
        )
        db.add_all([mat_a, mat_b])
        db.commit()
        db.refresh(mat_a)
        db.refresh(mat_b)

        return {
            "mat_a_id": mat_a.id,
            "mat_b_id": mat_b.id,
            "token_a": create_access_token({"sub": f"student:{aluno_a.email}"}),
            "token_b": create_access_token({"sub": f"student:{aluno_b.email}"}),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession):
    app = FastAPI()
    app.include_router(student_materiais_adaptados.router)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestListagem:
    def test_aluno_ve_o_material_gerado_para_ele(self, client, seed):
        """O caso do TC-027: o que o professor gerou tem que chegar no aluno."""
        r = client.get("/student/materiais-adaptados/", headers=auth(seed["token_a"]))
        assert r.status_code == 200
        materiais = r.json()
        assert len(materiais) == 1
        assert materiais[0]["id"] == seed["mat_a_id"]
        assert materiais[0]["disciplina"] == "Matematica"
        assert materiais[0]["tipos_material"] == ["resumo_estruturado", "flashcards"]

    def test_listagem_nao_traz_material_de_outro_aluno(self, client, seed):
        r = client.get("/student/materiais-adaptados/", headers=auth(seed["token_b"]))
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()]
        assert ids == [seed["mat_b_id"]]
        assert seed["mat_a_id"] not in ids

    def test_listagem_omite_o_conteudo_pesado(self, client, seed):
        """resultado_json fica so no detalhe - a lista carrega metadados."""
        r = client.get("/student/materiais-adaptados/", headers=auth(seed["token_a"]))
        assert "resultado" not in r.json()[0]

    def test_sem_token_401(self, client):
        r = client.get("/student/materiais-adaptados/")
        assert r.status_code == 401


class TestDetalhe:
    def test_aluno_abre_o_proprio_material_com_conteudo(self, client, seed):
        r = client.get(f"/student/materiais-adaptados/{seed['mat_a_id']}", headers=auth(seed["token_a"]))
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == seed["mat_a_id"]
        # Mesma chave usada na visao do professor, para o front reusar o viewer.
        assert body["resultado"] == {"resumo_estruturado": {"titulo": "Fracoes"}}

    def test_material_de_outro_aluno_404(self, client, seed):
        """404 e nao 403: nao vaza nem a existencia do material alheio."""
        r = client.get(f"/student/materiais-adaptados/{seed['mat_a_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 404

    def test_material_inexistente_404(self, client, seed):
        r = client.get("/student/materiais-adaptados/999999", headers=auth(seed["token_a"]))
        assert r.status_code == 404

    def test_sem_token_401(self, client, seed):
        r = client.get(f"/student/materiais-adaptados/{seed['mat_a_id']}")
        assert r.status_code == 401
