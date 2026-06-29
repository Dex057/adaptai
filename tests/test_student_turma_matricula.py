"""
Tarefa B - Persistir turma e matricula no cadastro individual de aluno.

Trava a correcao: antes, StudentCreate nao declarava turma/matricula e o
create_student usava hasattr(...) -> sempre False -> gravava None. Agora os
campos estao no schema e a rota grava direto.

Estrategia (autocontida, espelha test_idor_ownership): sqlite em memoria +
schema real, app FastAPI minimo so com o router de students, override de get_db,
token JWT real. Professor sem escola (grandfather -> enforce_limite_alunos no-op).
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
        prof = User(name="Prof Turma", email="prof_turma@test.com",
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


def test_create_persiste_turma_e_matricula(client, seed):
    """POST /students/ com turma e matricula -> persistem (nao None)."""
    payload = {
        "name": "Aluno Com Turma",
        "grade_level": "5o Ano",
        "turma": "B",
        "matricula": "2026-0042",
    }
    r = client.post("/students/", json=payload, headers=auth(seed["token"]))
    assert r.status_code == 201, r.text

    body = r.json()
    # A resposta (StudentResponse) ecoa os campos de volta para a UI.
    assert body["turma"] == "B"
    assert body["matricula"] == "2026-0042"

    # Recupera o aluno e confirma a persistencia (nao None).
    rget = client.get(f"/students/{body['id']}", headers=auth(seed["token"]))
    assert rget.status_code == 200, rget.text
    got = rget.json()
    assert got["turma"] == "B"
    assert got["matricula"] == "2026-0042"


def test_create_sem_turma_matricula_fica_none(client, seed):
    """Sem os campos, segue opcional -> None (sem quebrar o fluxo legado)."""
    payload = {"name": "Aluno Sem Turma", "grade_level": "3o Ano"}
    r = client.post("/students/", json=payload, headers=auth(seed["token"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["turma"] is None
    assert body["matricula"] is None
