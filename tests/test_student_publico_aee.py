"""
Tarefa D - Marcador publico-alvo AEE (derivado do diagnosis, sem coluna).

Prova a inferencia de Student.publico_aee: True para condicoes do publico-alvo
do AEE (TEA, deficiencias, altas habilidades) e False para transtornos
funcionais especificos (TDAH, dislexia, etc.) ou ausencia de diagnostico.

Estrategia (autocontida, espelha test_student_turma_matricula): sqlite em
memoria + schema real, app FastAPI so com o router de students, override de
get_db, JWT real. Confirma o eco de publico_aee no StudentResponse.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.student import Student
from app.core.security import create_access_token
from app.api.routes import students


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
    db = TestSession()
    try:
        prof = User(name="Prof AEE", email="prof_aee@test.com",
                    hashed_password="x", role=UserRole.TEACHER, is_active=True,
                    escola_id=None)
        db.add(prof)
        db.commit()
        db.refresh(prof)
        return {"token": create_access_token({"sub": prof.email})}
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession):
    app = FastAPI()
    app.include_router(students.router)

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


def _criar(client, token, diagnosis):
    payload = {"name": "Aluno AEE", "grade_level": "5o Ano", "diagnosis": diagnosis}
    r = client.post("/students/", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


# ---- Publico-alvo AEE -> True ----
@pytest.mark.parametrize("diagnosis", [
    {"tea": {"level": 1}},
    {"deficiencia_visual": True},
    {"deficiencia_auditiva": True},
    {"deficiencia_intelectual": True},
    {"deficiencia_fisica": True},
    {"sindrome_down": True},
    {"altas_habilidades": True},
    {"tdah": True, "tea": {"level": 2}},  # combinado: TEA garante AEE
])
def test_publico_aee_true(client, seed, diagnosis):
    body = _criar(client, seed["token"], diagnosis)
    assert body["publico_aee"] is True


# ---- Nao publico-alvo (transtornos funcionais) ou sem diagnostico -> False ----
@pytest.mark.parametrize("diagnosis", [
    {"tdah": True},
    {"dislexia": True},
    {"discalculia": True},
    {"disgrafia": True},
    {"tod": True},
    {"tea": False},   # chave presente mas falsa nao conta
    {},
    None,
])
def test_publico_aee_false(client, seed, diagnosis):
    body = _criar(client, seed["token"], diagnosis)
    assert body["publico_aee"] is False
