"""
Tarefa 4.1 (Caminho A) - limite mensal de PEI passa a ser cobrado de fato.

Agora que o endpoint persiste o PEI na tabela 'peis', enforce_limite_peis conta
ao vivo os PEIs criados no mes pela escola e bloqueia (403) ao atingir o
limite_peis_mes do plano. Grandfather: super_admin e escola sem assinatura
ativa/trial nao sao limitados.

Harness autocontido (sqlite em memoria + schema real), chamando enforce_limite_peis.
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
from app.models.plano import Plano
from app.models.assinatura import Assinatura, StatusAssinatura
from app.models.pei import PEI
from app.core.tenant import enforce_limite_peis


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        Base.metadata.create_all(eng)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Schema nao montavel em sqlite: {e}")
    s = sessionmaker(autocommit=False, autoflush=False, bind=eng)()
    yield s
    s.close()
    Base.metadata.drop_all(eng)


def _seed(db, *, limite=2, status=StatusAssinatura.ATIVA.value, com_assinatura=True):
    esc = Escola(nome="Escola", email="e@esc.test")
    db.add(esc); db.commit(); db.refresh(esc)
    plano = Plano(nome="Plano", slug="plano", valor=10.0, limite_peis_mes=limite)
    db.add(plano); db.commit(); db.refresh(plano)
    if com_assinatura:
        db.add(Assinatura(escola_id=esc.id, plano_id=plano.id, status=status, valor_mensal=10.0)); db.commit()
    user = User(name="Prof", email="prof@test.com", hashed_password="x",
                role=UserRole.TEACHER, is_active=True, escola_id=esc.id)
    db.add(user); db.commit(); db.refresh(user)
    student = Student(name="Aluno", grade_level="5o", escola_id=esc.id,
                      created_by_user_id=user.id, is_active=True)
    db.add(student); db.commit(); db.refresh(student)
    return esc, user, student


def _add_peis(db, student, user, n):
    for _ in range(n):
        db.add(PEI(student_id=student.id, created_by=user.id, escola_id=user.escola_id, status="rascunho"))
    db.commit()


def test_abaixo_do_limite_nao_bloqueia(db):
    _, user, student = _seed(db, limite=2)
    _add_peis(db, student, user, 1)  # 1 < 2
    enforce_limite_peis(db, user)  # nao levanta


def test_no_limite_bloqueia_403(db):
    _, user, student = _seed(db, limite=2)
    _add_peis(db, student, user, 2)  # 2 >= 2
    with pytest.raises(HTTPException) as e:
        enforce_limite_peis(db, user)
    assert e.value.status_code == 403


def test_super_admin_bypass(db):
    _, user, student = _seed(db, limite=1)
    _add_peis(db, student, user, 5)  # bem acima
    sadm = User(name="root", email="root@test.com", hashed_password="x",
                role=UserRole.SUPER_ADMIN, is_active=True, escola_id=user.escola_id)
    db.add(sadm); db.commit(); db.refresh(sadm)
    enforce_limite_peis(db, sadm)  # super_admin nunca e limitado


def test_sem_assinatura_ativa_grandfather(db):
    # escola sem assinatura -> nao limita (nao trava usuario legado)
    _, user, student = _seed(db, limite=1, com_assinatura=False)
    _add_peis(db, student, user, 5)
    enforce_limite_peis(db, user)  # nao levanta (grandfather)
