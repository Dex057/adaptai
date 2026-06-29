"""
Tarefa 1.0 - Denormalizacao de escola_id em provas/materiais/relatorios/peis.

Prova, sem depender de MySQL nem da IA:
  1. backfill: roda o MESMO SQL da migration (importado de BACKFILL_SQL) e confirma
     que escola_id e preenchido a partir do pai (user via criado_por_id; student via
     student_id);
  2. grandfather: linha cujo pai nao tem escola fica com escola_id NULL;
  3. derivacao na criacao: as expressoes que os pontos de criacao usam resolvem para
     a escola correta, e o objeto gravado persiste escola_id.

Estrategia autocontida (sqlite em memoria + create_all), nao mexe no conftest.
"""
import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401 - registra todos os models + relationships
from app.models.escola import Escola
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.prova import Prova, StatusProva
from app.models.material import Material, StatusMaterial, TipoMaterial
from app.models.relatorio import Relatorio
from app.models.pei import PEI

# Importa BACKFILL_SQL diretamente da migration => o teste roda EXATAMENTE o mesmo
# SQL que a migration aplica (zero drift entre teste e migration).
_MIG_PATH = (
    pathlib.Path(__file__).parent.parent
    / "alembic" / "versions"
    / "20260625_1430_a1f0escoladenorm_denormalize_tenant_escola_id.py"
)
_spec = importlib.util.spec_from_file_location("mig_escola_denorm", _MIG_PATH)
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)
BACKFILL_SQL = _mig.BACKFILL_SQL


@pytest.fixture()
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(eng)


def _seed(db):
    escola = Escola(nome="Escola A", email="escolaA_denorm@test.com")
    db.add(escola)
    db.commit()
    db.refresh(escola)
    prof = User(name="Prof", email="prof_denorm@test.com", hashed_password="x",
                role=UserRole.TEACHER, is_active=True, escola_id=escola.id)
    db.add(prof)
    db.commit()
    db.refresh(prof)
    aluno = Student(name="Aluno", grade_level="5o ano", created_by_user_id=prof.id,
                    escola_id=escola.id, is_active=True)
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    return escola, prof, aluno


def _run_backfill(db):
    for stmt in BACKFILL_SQL:
        db.execute(text(stmt))
    db.commit()


def test_backfill_preenche_do_pai(db):
    escola, prof, aluno = _seed(db)
    # linhas "legadas": escola_id ainda NULL
    prova = Prova(titulo="P", conteudo_prompt="c", materia="Mat", quantidade_questoes=1,
                  status=StatusProva.ATIVA, criado_por_id=prof.id, escola_id=None)
    material = Material(titulo="M", conteudo_prompt="c", tipo=TipoMaterial.VISUAL,
                        materia="Mat", status=StatusMaterial.DISPONIVEL,
                        criado_por_id=prof.id, escola_id=None)
    relatorio = Relatorio(student_id=aluno.id, tipo="Laudo", created_by=prof.id, escola_id=None)
    pei = PEI(student_id=aluno.id, created_by=prof.id, escola_id=None)
    db.add_all([prova, material, relatorio, pei])
    db.commit()

    _run_backfill(db)

    for obj in (prova, material, relatorio, pei):
        db.refresh(obj)
        assert obj.escola_id == escola.id, f"{type(obj).__name__}.escola_id nao backfillou"


def test_backfill_grandfather_pai_sem_escola_fica_null(db):
    escola, prof, aluno = _seed(db)
    prof_sem = User(name="Sem", email="sem_escola_denorm@test.com", hashed_password="x",
                    role=UserRole.TEACHER, is_active=True, escola_id=None)
    db.add(prof_sem)
    db.commit()
    db.refresh(prof_sem)
    prova = Prova(titulo="P", conteudo_prompt="c", materia="Mat", quantidade_questoes=1,
                  status=StatusProva.ATIVA, criado_por_id=prof_sem.id, escola_id=None)
    db.add(prova)
    db.commit()

    _run_backfill(db)

    db.refresh(prova)
    assert prova.escola_id is None  # pai sem escola -> grandfather NULL


def test_derivacao_escola_na_criacao(db):
    escola, prof, aluno = _seed(db)
    # provas/materiais: escola via criado_por_id -> users.escola_id
    via_user = db.query(User.escola_id).filter(User.id == prof.id).scalar()
    # relatorios/peis: escola via student_id -> students.escola_id
    via_student = db.query(Student.escola_id).filter(Student.id == aluno.id).scalar()
    assert via_user == escola.id
    assert via_student == escola.id
    # objeto criado com escola_id persiste
    p = Prova(titulo="P", conteudo_prompt="c", materia="M", quantidade_questoes=1,
              status=StatusProva.ATIVA, criado_por_id=prof.id, escola_id=via_user)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.escola_id == escola.id
