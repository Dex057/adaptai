"""
Testes da gestao de professores pela escola (app/api/routes/gestao_usuarios.py)
e da visao derivada "minhas turmas" (GET /students/turmas).

Trava:
  - ADMIN da escola A cria/edita/reseta senha de professor, sempre escopado ao
    proprio escola_id (o professor nasce com escola_id = o do admin, nunca NULL);
  - TEACHER nao acessa o CRUD (require_admin);
  - ADMIN da escola B nao ve nem edita professores da escola A;
  - o admin nao consegue desativar/rebaixar a propria conta;
  - enforce_limite_professores bloqueia acima do limite do plano;
  - /students/turmas agrupa os alunos do professor por serie+turma.

Estrategia: engine sqlite em memoria + create_all; app minimo com os 2 routers.
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
from app.models.escola import Escola
from app.models.plano import Plano
from app.models.assinatura import Assinatura, StatusAssinatura
from app.core.security import create_access_token, get_password_hash
from app.api.routes import gestao_usuarios, students


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
        escola_a = Escola(nome="Escola A", email="a@esc.com")
        escola_b = Escola(nome="Escola B", email="b@esc.com")
        db.add_all([escola_a, escola_b])
        db.commit()
        db.refresh(escola_a)
        db.refresh(escola_b)

        # Plano com limite baixo para exercitar o enforcement.
        plano = Plano(nome="Teste", slug="teste", valor=0, limite_alunos=100, limite_professores=3)
        db.add(plano)
        db.commit()
        db.refresh(plano)

        db.add(Assinatura(
            escola_id=escola_a.id, plano_id=plano.id,
            status=StatusAssinatura.ATIVA.value, valor_mensal=0,
        ))

        admin_a = User(name="Admin A", email="admin_a@esc.com",
                       hashed_password=get_password_hash("SenhaForte123"),
                       role=UserRole.ADMIN, escola_id=escola_a.id, is_active=True)
        teacher_a = User(name="Prof A1", email="prof_a1@esc.com",
                         hashed_password=get_password_hash("SenhaForte123"),
                         role=UserRole.TEACHER, escola_id=escola_a.id, is_active=True)
        admin_b = User(name="Admin B", email="admin_b@esc.com",
                       hashed_password=get_password_hash("SenhaForte123"),
                       role=UserRole.ADMIN, escola_id=escola_b.id, is_active=True)
        db.add_all([admin_a, teacher_a, admin_b])
        db.commit()
        db.refresh(admin_a)
        db.refresh(teacher_a)
        db.refresh(admin_b)

        # Alunos do teacher_a em 2 turmas para testar /students/turmas.
        db.add_all([
            Student(name="Aluno 1", grade_level="5º ano", turma="A",
                    created_by_user_id=teacher_a.id, escola_id=escola_a.id, is_active=True),
            Student(name="Aluno 2", grade_level="5º ano", turma="A",
                    created_by_user_id=teacher_a.id, escola_id=escola_a.id, is_active=True),
            Student(name="Aluno 3", grade_level="6º ano", turma="B",
                    created_by_user_id=teacher_a.id, escola_id=escola_a.id, is_active=True),
        ])
        db.commit()

        return {
            "escola_a_id": escola_a.id,
            "admin_a_id": admin_a.id,
            "teacher_a_id": teacher_a.id,
            "token_admin_a": create_access_token({"sub": admin_a.email}),
            "token_teacher_a": create_access_token({"sub": teacher_a.email}),
            "token_admin_b": create_access_token({"sub": admin_b.email}),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(TestSession):
    app = FastAPI()
    app.include_router(gestao_usuarios.router)
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


class TestCriarProfessor:
    def test_admin_cria_professor_herda_escola(self, client, seed):
        r = client.post("/escola/professores/", headers=auth(seed["token_admin_a"]), json={
            "name": "Prof Novo", "email": "prof_novo@esc.com",
            "password": "SenhaForte123", "role": "teacher",
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["escola_id"] == seed["escola_a_id"]
        assert body["role"] == "teacher"
        assert body["is_active"] is True

    def test_teacher_nao_pode_criar(self, client, seed):
        r = client.post("/escola/professores/", headers=auth(seed["token_teacher_a"]), json={
            "name": "X", "email": "x@esc.com", "password": "SenhaForte123", "role": "teacher",
        })
        assert r.status_code == 403

    def test_email_duplicado_400(self, client, seed):
        r = client.post("/escola/professores/", headers=auth(seed["token_admin_a"]), json={
            "name": "Dup", "email": "prof_a1@esc.com", "password": "SenhaForte123", "role": "teacher",
        })
        assert r.status_code == 400

    def test_nao_cria_admin(self, client, seed):
        r = client.post("/escola/professores/", headers=auth(seed["token_admin_a"]), json={
            "name": "Chefe", "email": "chefe@esc.com", "password": "SenhaForte123", "role": "admin",
        })
        assert r.status_code == 422

    def test_limite_do_plano_bloqueia(self, client, seed):
        # Plano limite_professores=3. Ja existem admin_a + prof_a1 + prof_novo = 3.
        r = client.post("/escola/professores/", headers=auth(seed["token_admin_a"]), json={
            "name": "Excedente", "email": "excedente@esc.com",
            "password": "SenhaForte123", "role": "teacher",
        })
        assert r.status_code == 403
        assert "Limite de professores" in r.json()["detail"]


class TestListarEEditar:
    def test_listar_so_da_minha_escola(self, client, seed):
        r = client.get("/escola/professores/", headers=auth(seed["token_admin_a"]))
        assert r.status_code == 200
        emails = {u["email"] for u in r.json()}
        assert "prof_a1@esc.com" in emails
        assert "admin_b@esc.com" not in emails

    def test_admin_b_nao_edita_professor_de_a(self, client, seed):
        r = client.patch(f"/escola/professores/{seed['teacher_a_id']}",
                         headers=auth(seed["token_admin_b"]), json={"name": "Hackeado"})
        assert r.status_code == 404

    def test_admin_nao_desativa_a_si_mesmo(self, client, seed):
        r = client.patch(f"/escola/professores/{seed['admin_a_id']}",
                         headers=auth(seed["token_admin_a"]), json={"is_active": False})
        assert r.status_code == 400

    def test_desativar_professor(self, client, seed):
        r = client.patch(f"/escola/professores/{seed['teacher_a_id']}",
                         headers=auth(seed["token_admin_a"]), json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False
        # reativa para nao afetar outros testes
        client.patch(f"/escola/professores/{seed['teacher_a_id']}",
                     headers=auth(seed["token_admin_a"]), json={"is_active": True})

    def test_reset_senha_responde(self, client, seed):
        r = client.post(f"/escola/professores/{seed['teacher_a_id']}/reset-senha",
                        headers=auth(seed["token_admin_a"]))
        assert r.status_code == 200
        assert "email_enviado" in r.json()


class TestMinhasTurmas:
    def test_agrupa_por_serie_e_turma(self, client, seed):
        r = client.get("/students/turmas", headers=auth(seed["token_teacher_a"]))
        assert r.status_code == 200
        turmas = {(t["serie"], t["turma"]): t["total_alunos"] for t in r.json()}
        assert turmas[("5º ano", "A")] == 2
        assert turmas[("6º ano", "B")] == 1
