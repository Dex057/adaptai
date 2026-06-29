"""
Tarefa 1.2 - Guard cross-tenant na resolucao por id.

Prova, de forma consistente, que um usuario da escola A pedindo recurso da
escola B recebe 403 - em alunos, PEI, provas, e (via verificar_acesso_aluno
sobre student_id) relatorios e materiais. Cobre as duas dimensoes do guard:
  - TEACHER: bloqueado por ownership (created_by);
  - ADMIN/COORDINATOR: bloqueado por escola (escola_id);
  - SUPER_ADMIN: acessa tudo (bypass).

Harness autocontido (espelha test_idor_ownership): sqlite em memoria + schema
real, chamando os guards de dependencies.py diretamente.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.escola import Escola
from app.models.student import Student
from app.models.prova import Prova, StatusProva
from app.models.relatorio import Relatorio
from app.models.pei import PEI, PEIObjetivo
from app.api.dependencies import (
    verificar_acesso_aluno,
    verificar_acesso_pei,
    verificar_acesso_objetivo_pei,
    verificar_acesso_prova,
)


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
def seed(TestSession):
    db = TestSession()
    ea = Escola(nome="Escola A", email="a@esc.test")
    eb = Escola(nome="Escola B", email="b@esc.test")
    db.add_all([ea, eb]); db.commit(); db.refresh(ea); db.refresh(eb)

    def montar(esc, tag, role=UserRole.TEACHER):
        u = User(name=f"User {tag}", email=f"u_{tag}@test.com", hashed_password="x",
                 role=role, is_active=True, escola_id=esc.id)
        db.add(u); db.commit(); db.refresh(u)
        return u

    teacher_a = montar(ea, "teacherA")
    admin_a = montar(ea, "adminA", role=UserRole.ADMIN)
    teacher_b = montar(eb, "teacherB")

    def recursos(esc, owner, tag):
        s = Student(name=f"Aluno {tag}", grade_level="5o", escola_id=esc.id,
                    created_by_user_id=owner.id, is_active=True)
        db.add(s); db.commit(); db.refresh(s)
        p = Prova(titulo=f"Prova {tag}", conteudo_prompt="c", materia="Mat",
                  quantidade_questoes=1, status=StatusProva.ATIVA, criado_por_id=owner.id, escola_id=esc.id)
        r = Relatorio(student_id=s.id, tipo="Laudo", created_by=owner.id, escola_id=esc.id)
        pei = PEI(student_id=s.id, created_by=owner.id, escola_id=esc.id)
        db.add_all([p, r, pei]); db.commit(); db.refresh(p); db.refresh(r); db.refresh(pei)
        obj = PEIObjetivo(pei_id=pei.id)
        db.add(obj); db.commit(); db.refresh(obj)
        return {"aluno": s, "prova": p, "relatorio": r, "pei": pei, "objetivo": obj}

    a = recursos(ea, teacher_a, "A")
    b = recursos(eb, teacher_b, "B")
    sadm = User(name="root", email="root@test.com", hashed_password="x",
                role=UserRole.SUPER_ADMIN, is_active=True, escola_id=None)
    db.add(sadm); db.commit(); db.refresh(sadm)
    return {"db": db, "teacher_a": teacher_a, "admin_a": admin_a, "teacher_b": teacher_b,
            "a": a, "b": b, "sadm": sadm}


# ---- ALUNOS ----
def test_teacher_A_nao_acessa_aluno_B(seed):
    with pytest.raises(HTTPException) as e:
        verificar_acesso_aluno(seed["db"], seed["b"]["aluno"].id, seed["teacher_a"])
    assert e.value.status_code in (403, 404)

def test_admin_A_nao_acessa_aluno_B_por_escola(seed):
    with pytest.raises(HTTPException) as e:
        verificar_acesso_aluno(seed["db"], seed["b"]["aluno"].id, seed["admin_a"])
    assert e.value.status_code in (403, 404)

def test_admin_A_acessa_aluno_da_propria_escola(seed):
    aluno = verificar_acesso_aluno(seed["db"], seed["a"]["aluno"].id, seed["admin_a"])
    assert aluno.id == seed["a"]["aluno"].id

def test_teacher_A_acessa_proprio_aluno(seed):
    aluno = verificar_acesso_aluno(seed["db"], seed["a"]["aluno"].id, seed["teacher_a"])
    assert aluno.id == seed["a"]["aluno"].id


# ---- RELATORIOS / MATERIAIS (via verificar_acesso_aluno sobre student_id) ----
def test_relatorio_de_B_inacessivel_para_A(seed):
    # relatorios.py e materiais_adaptados.py guardam por relatorio.student_id / material.student_id
    with pytest.raises(HTTPException) as e:
        verificar_acesso_aluno(seed["db"], seed["b"]["relatorio"].student_id, seed["teacher_a"])
    assert e.value.status_code in (403, 404)


# ---- PEI ----
def test_teacher_A_nao_acessa_pei_B(seed):
    with pytest.raises(HTTPException) as e:
        verificar_acesso_pei(seed["db"], seed["b"]["pei"].id, seed["teacher_a"])
    assert e.value.status_code in (403, 404)

def test_teacher_A_nao_acessa_objetivo_pei_B(seed):
    with pytest.raises(HTTPException) as e:
        verificar_acesso_objetivo_pei(seed["db"], seed["b"]["objetivo"].id, seed["teacher_a"])
    assert e.value.status_code in (403, 404)


# ---- PROVAS ----
def test_teacher_A_nao_acessa_prova_B(seed):
    with pytest.raises(HTTPException) as e:
        verificar_acesso_prova(seed["b"]["prova"], seed["teacher_a"])
    assert e.value.status_code in (403, 404)

def test_teacher_A_acessa_propria_prova(seed):
    assert verificar_acesso_prova(seed["a"]["prova"], seed["teacher_a"]).id == seed["a"]["prova"].id


# ---- SUPER_ADMIN: bypass consistente ----
def test_super_admin_acessa_recursos_de_qualquer_escola(seed):
    assert verificar_acesso_aluno(seed["db"], seed["b"]["aluno"].id, seed["sadm"]).id == seed["b"]["aluno"].id
    assert verificar_acesso_pei(seed["db"], seed["b"]["pei"].id, seed["sadm"]).id == seed["b"]["pei"].id
    assert verificar_acesso_prova(seed["b"]["prova"], seed["sadm"]).id == seed["b"]["prova"].id
