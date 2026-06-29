"""
Tarefa 3.3 - Revogacao server-side de refresh token (logout).

A revogacao JA esta implementada via a tabela RevokedToken (auth.py): o logout
grava o jti do refresh e o /auth/refresh recusa jti revogado. Faltava o teste -
este arquivo trava o comportamento:

  - refresh token valido renova access (200);
  - apos /auth/logout, o MESMO refresh token e recusado em /auth/refresh (401);
  - logout e idempotente (200 mesmo repetido / token ja invalido).

Harness autocontido (espelha test_idor_ownership): sqlite em memoria + auth router.
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
from app.core.security import create_refresh_token
from app.api.routes import auth


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
def user(TestSession):
    db = TestSession()
    u = User(name="Prof", email="revoke@test.com", hashed_password="x",
             role=UserRole.TEACHER, is_active=True)
    db.add(u); db.commit(); db.refresh(u); db.close()
    return {"email": "revoke@test.com"}


@pytest.fixture(scope="module")
def client(TestSession):
    app = FastAPI()
    app.include_router(auth.router)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _novo_refresh(email):
    return create_refresh_token(data={"sub": email})


def test_refresh_valido_renova_access(client, user):
    rt = _novo_refresh(user["email"])
    r = client.post("/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 200
    assert r.json().get("access_token")


def test_logout_revoga_e_refresh_passa_a_401(client, user):
    rt = _novo_refresh(user["email"])
    # antes do logout: funciona
    assert client.post("/auth/refresh", json={"refresh_token": rt}).status_code == 200
    # logout revoga
    assert client.post("/auth/logout", json={"refresh_token": rt}).status_code == 200
    # depois do logout: recusado
    r = client.post("/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 401


def test_logout_idempotente(client, user):
    rt = _novo_refresh(user["email"])
    assert client.post("/auth/logout", json={"refresh_token": rt}).status_code == 200
    # repetir o logout do mesmo token continua 200 (best-effort)
    assert client.post("/auth/logout", json={"refresh_token": rt}).status_code == 200
