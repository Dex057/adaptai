"""
Testes de regressao de IDOR (ownership) nos endpoints sensiveis.

Travam as correcoes de seguranca aplicadas: um professor (B) NAO pode acessar
laudo/prova/redacao de aluno de outro professor (A). Cobre relatorios (LGPD -
dado de saude), provas, redacoes e a exigencia de auth em applications/answers.

Estrategia (autocontida, nao mexe no conftest compartilhado):
  - engine sqlite em memoria + create_all do schema real;
  - app FastAPI minimo com apenas os 4 routers sob teste;
  - override de get_db para a sessao de teste (cobre tambem get_current_user,
    que depende de get_db);
  - seed: Prof A e Prof B (TEACHER), 1 aluno cada, e 1 laudo/prova/tema/redacao
    pertencentes ao aluno do Prof A;
  - tokens JWT reais via create_access_token({"sub": email}).

Regra esperada (verificar_acesso_aluno / _verificar_acesso_prova para TEACHER):
  - dono            -> 200
  - outro professor -> 403 (sem permissao) ou 404 (nao encontrado no escopo dele)
  - sem token       -> 401
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.models  # noqa: F401 - registra TODOS os models no metadata + resolve relationships
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.relatorio import Relatorio
from app.models.prova import Prova, StatusProva
from app.models.redacao import TemaRedacao, RedacaoAluno, StatusRedacao
from app.core.security import create_access_token
from app.api.routes import relatorios, provas, redacoes, applications


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(scope="module")
def db_engine():
    """Engine sqlite em memoria, compartilhada no modulo (StaticPool)."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(eng)
    except Exception as e:  # pragma: no cover - so dispara se schema nao for sqlite-compativel
        pytest.skip(f"Schema nao montavel em sqlite para testes de IDOR: {e}")
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture(scope="module")
def TestSession(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture(scope="module")
def seed(TestSession):
    """Cria Prof A/B, alunos, e recursos pertencentes ao aluno do Prof A."""
    db = TestSession()
    try:
        prof_a = User(name="Prof A", email="profa_idor@test.com",
                      hashed_password="x", role=UserRole.TEACHER, is_active=True)
        prof_b = User(name="Prof B", email="profb_idor@test.com",
                      hashed_password="x", role=UserRole.TEACHER, is_active=True)
        db.add_all([prof_a, prof_b])
        db.commit()
        db.refresh(prof_a)
        db.refresh(prof_b)

        aluno_a = Student(name="Aluno A", grade_level="5o ano",
                          created_by_user_id=prof_a.id, is_active=True)
        aluno_b = Student(name="Aluno B", grade_level="5o ano",
                          created_by_user_id=prof_b.id, is_active=True)
        db.add_all([aluno_a, aluno_b])
        db.commit()
        db.refresh(aluno_a)
        db.refresh(aluno_b)

        rel = Relatorio(student_id=aluno_a.id, tipo="Laudo", created_by=prof_a.id)
        prova = Prova(titulo="Prova A", conteudo_prompt="conteudo", materia="Matematica",
                      quantidade_questoes=1, status=StatusProva.ATIVA, criado_por_id=prof_a.id)
        tema = TemaRedacao(titulo="Tema A", tema="tema", proposta="proposta",
                           criado_por_id=prof_a.id)
        db.add_all([rel, prova, tema])
        db.commit()
        db.refresh(rel)
        db.refresh(prova)
        db.refresh(tema)

        red = RedacaoAluno(tema_id=tema.id, aluno_id=aluno_a.id, status=StatusRedacao.RASCUNHO)
        db.add(red)
        db.commit()
        db.refresh(red)

        return {
            "aluno_a_id": aluno_a.id,
            "aluno_b_id": aluno_b.id,
            "rel_id": rel.id,
            "prova_id": prova.id,
            "tema_id": tema.id,
            "red_id": red.id,
            "token_a": create_access_token({"sub": prof_a.email}),
            "token_b": create_access_token({"sub": prof_b.email}),
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def client(db_engine, TestSession):
    app = FastAPI()
    for router in (relatorios.router, provas.router, redacoes.router, applications.router):
        app.include_router(router)

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


# ============================================================
# RELATORIOS (laudos medicos - LGPD)
# ============================================================

class TestRelatoriosIDOR:
    def test_obter_outro_professor_403(self, client, seed):
        r = client.get(f"/relatorios/{seed['rel_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_obter_dono_200(self, client, seed):
        r = client.get(f"/relatorios/{seed['rel_id']}", headers=auth(seed["token_a"]))
        assert r.status_code == 200

    def test_excluir_outro_professor_403(self, client, seed):
        # 403 ocorre ANTES de qualquer delete (verificar_acesso_aluno), entao o seed nao e mutado.
        r = client.delete(f"/relatorios/{seed['rel_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_listar_por_aluno_outro_professor_403(self, client, seed):
        r = client.get(f"/relatorios/?student_id={seed['aluno_a_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_listar_por_aluno_dono_200(self, client, seed):
        r = client.get(f"/relatorios/?student_id={seed['aluno_a_id']}", headers=auth(seed["token_a"]))
        assert r.status_code == 200

    def test_arquivos_do_aluno_outro_professor_403(self, client, seed):
        r = client.get(f"/relatorios/student/{seed['aluno_a_id']}/files", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_baixar_arquivo_outro_professor_403(self, client, seed):
        # verificar_acesso_aluno roda antes de tocar o disco -> 403 sem precisar de arquivo.
        r = client.get(f"/relatorios/{seed['rel_id']}/arquivo", headers=auth(seed["token_b"]))
        assert r.status_code == 403


# ============================================================
# PROVAS
# ============================================================

class TestProvasIDOR:
    def test_obter_outro_professor_403(self, client, seed):
        r = client.get(f"/provas/{seed['prova_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_obter_dono_200(self, client, seed):
        r = client.get(f"/provas/{seed['prova_id']}", headers=auth(seed["token_a"]))
        assert r.status_code == 200

    def test_deletar_outro_professor_403(self, client, seed):
        r = client.delete(f"/provas/{seed['prova_id']}", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_provas_do_aluno_outro_professor_403(self, client, seed):
        r = client.get(f"/provas/aluno/{seed['aluno_a_id']}/provas", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_provas_do_aluno_dono_200(self, client, seed):
        r = client.get(f"/provas/aluno/{seed['aluno_a_id']}/provas", headers=auth(seed["token_a"]))
        assert r.status_code == 200


# ============================================================
# REDACOES
# ============================================================

class TestRedacoesIDOR:
    def test_historico_outro_professor_403(self, client, seed):
        r = client.get(f"/redacoes/aluno/{seed['aluno_a_id']}/historico", headers=auth(seed["token_b"]))
        assert r.status_code == 403

    def test_historico_dono_200(self, client, seed):
        r = client.get(f"/redacoes/aluno/{seed['aluno_a_id']}/historico", headers=auth(seed["token_a"]))
        assert r.status_code == 200

    def test_obter_redacao_aluno_outro_professor_403(self, client, seed):
        r = client.get(
            f"/redacoes/aluno/{seed['aluno_a_id']}/redacao/{seed['tema_id']}",
            headers=auth(seed["token_b"]),
        )
        assert r.status_code == 403


# ============================================================
# APPLICATIONS (antes SEM auth nenhuma)
# ============================================================

class TestApplicationsAuth:
    def test_submit_answer_sem_token_401(self, client):
        r = client.post("/applications/1/answers",
                        json={"question_id": 1, "selected_answer": "A", "time_spent_seconds": 5})
        assert r.status_code == 401

    def test_submit_answers_batch_sem_token_401(self, client):
        r = client.post("/applications/1/answers/batch",
                        json={"answers": [{"question_id": 1, "selected_answer": "A", "time_spent_seconds": 5}]})
        assert r.status_code == 401
