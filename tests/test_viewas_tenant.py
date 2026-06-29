"""
Tarefa 1.3 - ViewAs (impersonacao de escola para admin de rede / SEDUC).

Decisao: ViewAs liberado SO para SUPER_ADMIN (sem migracao de esquema). O header
X-View-As-Escola vira o tenant efetivo apenas para super_admin com escola valida;
para qualquer outro papel e ignorado (fail-closed - sem escalonamento).

Prova:
  - super_admin com ViewAs ativo enxerga SO a escola alvo;
  - super_admin sem ViewAs mantem bypass (ve tudo);
  - resolver seta view_as so para super_admin + escola existente/ativa;
  - usuario comum forjando o header NAO ganha acesso.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.escola import Escola
from app.models.student import Student
from app.core.tenant import tenant_scoped_query
from app.api.dependencies import _resolver_view_as, VIEW_AS_HEADER


class FakeRequest:
    """Stub minimo: so precisa de .headers.get()."""
    def __init__(self, headers=None):
        self.headers = headers or {}


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

    def aluno(esc, owner, tag):
        s = Student(name=f"Aluno {tag}", grade_level="5o", escola_id=esc.id,
                    created_by_user_id=owner.id, is_active=True)
        db.add(s); db.commit(); db.refresh(s); return s

    teacher_b = User(name="TB", email="tb@test.com", hashed_password="x",
                     role=UserRole.TEACHER, is_active=True, escola_id=eb.id)
    sadm = User(name="root", email="root@test.com", hashed_password="x",
                role=UserRole.SUPER_ADMIN, is_active=True, escola_id=None)
    db.add_all([teacher_b, sadm]); db.commit(); db.refresh(teacher_b); db.refresh(sadm)
    aluno_a = aluno(ea, sadm, "A")
    aluno_b = aluno(eb, teacher_b, "B")
    return {"db": db, "ea": ea, "eb": eb, "aluno_a": aluno_a, "aluno_b": aluno_b}


def _fresh(db, email):
    """Instancia limpa do user (sem view_as_escola_id residual de outro teste)."""
    return db.query(User).filter(User.email == email).first()


# ---- escopo efetivo ----
def test_super_admin_com_viewas_enxerga_so_a_escola_alvo(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")
    sadm.view_as_escola_id = seed["ea"].id
    ids = {s.id for s in tenant_scoped_query(db, Student, sadm).all()}
    assert seed["aluno_a"].id in ids
    assert seed["aluno_b"].id not in ids


def test_super_admin_sem_viewas_ve_tudo(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")  # sem view_as
    ids = {s.id for s in tenant_scoped_query(db, Student, sadm).all()}
    assert seed["aluno_a"].id in ids and seed["aluno_b"].id in ids


# ---- resolver (dependency) ----
def test_resolver_seta_para_super_admin_com_escola_valida(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")
    _resolver_view_as(FakeRequest({VIEW_AS_HEADER: str(seed["eb"].id)}), sadm, db)
    assert getattr(sadm, "view_as_escola_id", None) == seed["eb"].id


def test_resolver_ignora_escola_inexistente(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")
    _resolver_view_as(FakeRequest({VIEW_AS_HEADER: "99999"}), sadm, db)
    assert getattr(sadm, "view_as_escola_id", None) is None


def test_resolver_ignora_header_invalido(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")
    _resolver_view_as(FakeRequest({VIEW_AS_HEADER: "abc"}), sadm, db)
    assert getattr(sadm, "view_as_escola_id", None) is None


def test_resolver_sem_header_noop(seed):
    db = seed["db"]; sadm = _fresh(db, "root@test.com")
    _resolver_view_as(FakeRequest({}), sadm, db)
    assert getattr(sadm, "view_as_escola_id", None) is None


# ---- fail-closed: usuario comum NAO impersona ----
def test_teacher_forjando_header_nao_ganha_acesso(seed):
    db = seed["db"]; teacher = _fresh(db, "tb@test.com")  # escola B
    # tenta impersonar a escola A via header
    _resolver_view_as(FakeRequest({VIEW_AS_HEADER: str(seed["ea"].id)}), teacher, db)
    # header ignorado: nada setado
    assert getattr(teacher, "view_as_escola_id", None) is None
    # e a query continua escopada a propria escola (B), nunca A
    ids = {s.id for s in tenant_scoped_query(db, Student, teacher).all()}
    assert seed["aluno_b"].id in ids
    assert seed["aluno_a"].id not in ids
