"""
TC-034/040 - `GET /student/meu-pei` nao pode responder `null`.
TC-129 - o aluno precisa ver `prazo_vencido` na propria meta.

O que estava quebrado: o endpoint declarava `response_model=Optional[PEIResumo]`
e fazia `return None` quando o aluno nao tinha PEI. Do lado do cliente isso e um
200 com corpo `null` - qualquer leitura de `.objetivos`/`.total_objetivos`
estoura TypeError, e o Portal do Aluno abria em branco em vez de mostrar "voce
ainda nao tem PEI". Agora a resposta e sempre um objeto: `tem_pei: false` com
listas vazias.

E o `prazo_vencido`, que so existia em `GET /pei/{id}/completo` (visao do
professor), passou a acompanhar cada objetivo tambem aqui.
"""
from datetime import date, timedelta

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
from app.models.pei import PEI, PEIObjetivo
from app.core.security import create_access_token
from app.api.routes import student_pei


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
    """
    Dois alunos: um com PEI (uma meta vencida e uma no prazo) e um sem PEI
    nenhum - o caso que devolvia `null`.
    """
    db = TestSession()
    try:
        prof = User(name="Prof", email="prof_pei@test.com", hashed_password="x",
                    role=UserRole.TEACHER, is_active=True)
        db.add(prof)
        db.commit()
        db.refresh(prof)

        com_pei = Student(name="Com PEI", grade_level="4o ano", email="com_pei@test.com",
                          created_by_user_id=prof.id, is_active=True)
        sem_pei = Student(name="Sem PEI", grade_level="4o ano", email="sem_pei@test.com",
                          created_by_user_id=prof.id, is_active=True)
        db.add_all([com_pei, sem_pei])
        db.commit()
        db.refresh(com_pei)
        db.refresh(sem_pei)

        pei = PEI(student_id=com_pei.id, created_by=prof.id, ano_letivo="2026", status="ativo")
        db.add(pei)
        db.commit()
        db.refresh(pei)

        ontem = date.today() - timedelta(days=1)
        proximo_mes = date.today() + timedelta(days=30)
        db.add_all([
            PEIObjetivo(pei_id=pei.id, area="linguagem", titulo="Meta atrasada",
                        trimestre=1, status="em_progresso", prazo=ontem,
                        valor_atual=20, valor_alvo=100),
            PEIObjetivo(pei_id=pei.id, area="matematica", titulo="Meta no prazo",
                        trimestre=1, status="em_progresso", prazo=proximo_mes,
                        valor_atual=50, valor_alvo=100),
            PEIObjetivo(pei_id=pei.id, area="linguagem", titulo="Meta entregue tarde",
                        trimestre=1, status="atingido", prazo=ontem,
                        valor_atual=100, valor_alvo=100),
        ])
        db.commit()

        return {
            "token_com_pei": create_access_token({"sub": f"student:{com_pei.email}"}),
            "token_sem_pei": create_access_token({"sub": f"student:{sem_pei.email}"}),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession):
    app = FastAPI()
    app.include_router(student_pei.router, prefix="/student")

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


class TestAlunoSemPEI:
    def test_nunca_responde_null(self, client, seed):
        """O bug do TC-034/040: `null` no corpo derrubava o Portal do Aluno."""
        r = client.get("/student/meu-pei", headers=auth(seed["token_sem_pei"]))
        assert r.status_code == 200
        body = r.json()
        assert body is not None
        assert body["tem_pei"] is False

    def test_corpo_e_navegavel_sem_checagem_de_null(self, client, seed):
        """As chaves que o cliente le tem que existir mesmo sem PEI."""
        body = client.get("/student/meu-pei", headers=auth(seed["token_sem_pei"])).json()
        assert body["objetivos"] == []
        assert body["total_objetivos"] == 0
        assert body["progresso_geral"] == 0
        assert body["objetivos_por_area"] == {}
        assert body["id"] is None


class TestAlunoComPEI:
    def test_traz_o_pei_com_tem_pei_true(self, client, seed):
        body = client.get("/student/meu-pei", headers=auth(seed["token_com_pei"])).json()
        assert body["tem_pei"] is True
        assert body["id"] is not None
        assert body["total_objetivos"] == 3

    def test_prazo_vencido_por_objetivo(self, client, seed):
        """TC-129 no lado do aluno."""
        body = client.get("/student/meu-pei", headers=auth(seed["token_com_pei"])).json()
        por_titulo = {o["titulo"]: o for o in body["objetivos"]}

        assert por_titulo["Meta atrasada"]["prazo_vencido"] is True
        assert por_titulo["Meta no prazo"]["prazo_vencido"] is False
        # Entregue depois do prazo nao conta como vencida: nao ha acao pendente.
        assert por_titulo["Meta entregue tarde"]["prazo_vencido"] is False


def test_sem_token_401(client):
    assert client.get("/student/meu-pei").status_code == 401
