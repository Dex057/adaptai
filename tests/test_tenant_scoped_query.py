"""
Testes do helper fail-closed tenant_scoped_query (Tarefa 1.1 do roteiro).

Prova que:
  - contexto sem escola_id (e nao super_admin) resulta em ERRO, nao em vazamento;
  - escola A nao enxerga dados da escola B (direto, via_student, via_user, via_pei);
  - SUPER_ADMIN continua vendo tudo (bypass explicito);
  - model tenant-scoped sem estrategia registrada falha fechado (nao consulta sem filtro).

Harness autocontido (espelha test_idor_ownership): sqlite em memoria + schema real,
chamando tenant_scoped_query diretamente (nivel de unidade, sem HTTP).
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401 - registra todos os models + resolve relationships
from app.models.user import User, UserRole
from app.models.escola import Escola
from app.models.student import Student
from app.models.prova import Prova, StatusProva
from app.models.relatorio import Relatorio
from app.models.pei import PEI, PEIObjetivo
from app.models.plano import Plano
from app.core.tenant import (
    tenant_scoped_query,
    TenantContextoSemEscola,
    TenantModelNaoRegistrado,
)


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
    """Duas escolas (A e B), cada uma com user, aluno, prova, relatorio, PEI e objetivo."""
    db = TestSession()
    try:
        escola_a = Escola(nome="Escola A", email="a@esc.test")
        escola_b = Escola(nome="Escola B", email="b@esc.test")
        db.add_all([escola_a, escola_b])
        db.commit()
        db.refresh(escola_a)
        db.refresh(escola_b)

        def montar(esc, tag):
            u = User(name=f"Prof {tag}", email=f"prof_{tag}@test.com",
                     hashed_password="x", role=UserRole.TEACHER,
                     is_active=True, escola_id=esc.id)
            db.add(u); db.commit(); db.refresh(u)
            s = Student(name=f"Aluno {tag}", grade_level="5o ano",
                        escola_id=esc.id, created_by_user_id=u.id, is_active=True)
            db.add(s); db.commit(); db.refresh(s)
            p = Prova(titulo=f"Prova {tag}", conteudo_prompt="c", materia="Mat",
                      quantidade_questoes=1, status=StatusProva.ATIVA, criado_por_id=u.id, escola_id=esc.id)
            r = Relatorio(student_id=s.id, tipo="Laudo", created_by=u.id, escola_id=esc.id)
            pei = PEI(student_id=s.id, created_by=u.id, escola_id=esc.id)
            db.add_all([p, r, pei]); db.commit()
            db.refresh(p); db.refresh(r); db.refresh(pei)
            obj = PEIObjetivo(pei_id=pei.id)
            db.add(obj); db.commit(); db.refresh(obj)
            return {"user": u, "student": s, "prova": p, "relatorio": r,
                    "pei": pei, "objetivo": obj, "escola": esc}

        a = montar(escola_a, "A")
        b = montar(escola_b, "B")

        # usuario legado SEM escola (escola_id None) - mesmo papel TEACHER
        legado = User(name="Legado", email="legado@test.com", hashed_password="x",
                      role=UserRole.TEACHER, is_active=True, escola_id=None)
        # super admin
        sadm = User(name="Root", email="root@test.com", hashed_password="x",
                    role=UserRole.SUPER_ADMIN, is_active=True, escola_id=None)
        db.add_all([legado, sadm]); db.commit(); db.refresh(legado); db.refresh(sadm)

        return {"db": db, "a": a, "b": b, "legado": legado, "sadm": sadm}
    finally:
        pass  # sessao reaproveitada pelos testes; fechada no teardown do modulo


# ---------------------------------------------------------------
# FAIL-CLOSED: sem escola_id -> erro, nunca query sem filtro
# ---------------------------------------------------------------

def test_sem_escola_levanta_erro_nao_vaza(seed):
    db = seed["db"]
    with pytest.raises(TenantContextoSemEscola) as exc:
        tenant_scoped_query(db, Student, seed["legado"]).all()
    assert exc.value.status_code == 403


def test_sem_escola_em_model_indireto_tambem_falha(seed):
    db = seed["db"]
    with pytest.raises(HTTPException):
        tenant_scoped_query(db, Relatorio, seed["legado"]).all()


# ---------------------------------------------------------------
# DIRECT (Student): A nao ve B
# ---------------------------------------------------------------

def test_direct_student_escopo_por_escola(seed):
    db = seed["db"]
    ids_a = {s.id for s in tenant_scoped_query(db, Student, seed["a"]["user"]).all()}
    assert seed["a"]["student"].id in ids_a
    assert seed["b"]["student"].id not in ids_a


# ---------------------------------------------------------------
# VIA USER (Prova): A nao ve provas criadas por user de B
# ---------------------------------------------------------------

def test_via_user_prova_escopo_por_escola(seed):
    db = seed["db"]
    ids_a = {p.id for p in tenant_scoped_query(db, Prova, seed["a"]["user"]).all()}
    assert seed["a"]["prova"].id in ids_a
    assert seed["b"]["prova"].id not in ids_a


# ---------------------------------------------------------------
# VIA STUDENT (Relatorio): A nao ve laudos de alunos de B
# ---------------------------------------------------------------

def test_via_student_relatorio_escopo_por_escola(seed):
    db = seed["db"]
    ids_a = {r.id for r in tenant_scoped_query(db, Relatorio, seed["a"]["user"]).all()}
    assert seed["a"]["relatorio"].id in ids_a
    assert seed["b"]["relatorio"].id not in ids_a


# ---------------------------------------------------------------
# VIA PEI (PEIObjetivo - neto via PEI -> Student): A nao ve objetivos de B
# ---------------------------------------------------------------

def test_via_pei_objetivo_escopo_por_escola(seed):
    db = seed["db"]
    ids_a = {o.id for o in tenant_scoped_query(db, PEIObjetivo, seed["a"]["user"]).all()}
    assert seed["a"]["objetivo"].id in ids_a
    assert seed["b"]["objetivo"].id not in ids_a


# ---------------------------------------------------------------
# SUPER_ADMIN: bypass - ve tudo
# ---------------------------------------------------------------

def test_super_admin_ve_todas_as_escolas(seed):
    db = seed["db"]
    ids = {s.id for s in tenant_scoped_query(db, Student, seed["sadm"]).all()}
    assert seed["a"]["student"].id in ids
    assert seed["b"]["student"].id in ids


# ---------------------------------------------------------------
# Model tenant-scoped sem estrategia registrada -> fail-closed
# (Plano e global/catalogo; nao deve ser consultado por escola sem registro)
# ---------------------------------------------------------------

def test_model_nao_registrado_falha_fechado(seed):
    db = seed["db"]
    with pytest.raises(TenantModelNaoRegistrado):
        tenant_scoped_query(db, Plano, seed["a"]["user"]).all()
