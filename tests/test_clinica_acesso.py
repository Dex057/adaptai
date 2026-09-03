"""
Testes do guard de acesso clínico (anti-IDOR). Usa um current_user "duck-typed"
(SimpleNamespace) para não depender do schema exato de User, e valida:
  - profissional na equipe do caso: acesso liberado;
  - de fora: 404 (não vaza existência);
  - ADMIN da mesma escola e SUPER_ADMIN: acesso liberado.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import Base, engine, SessionLocal
from app.models.user import UserRole
from app.models.clinica_core import (
    Paciente, Profissional, EquipeCaso, StatusPaciente, Especialidade,
)
from app.services import acesso_clinico


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def cenario(db):
    """Cria paciente + profissional na equipe do caso (escola 1)."""
    p = Paciente(escola_id=1, nome="Paciente X", status=StatusPaciente.ATIVO)
    db.add(p)
    db.commit()
    db.refresh(p)

    prof = Profissional(escola_id=1, usuario_id=10, nome="Fono",
                        especialidade=Especialidade.FONOAUDIOLOGIA, ativo=True)
    db.add(prof)
    db.commit()
    db.refresh(prof)

    db.add(EquipeCaso(escola_id=1, paciente_id=p.id, profissional_id=prof.id, ativo=True))
    db.commit()
    return {"paciente": p, "profissional": prof}


def test_profissional_da_equipe_acessa(db, cenario):
    user = SimpleNamespace(role=UserRole.TEACHER, id=10, escola_id=1)
    p = acesso_clinico.verificar_acesso_paciente(db, cenario["paciente"].id, user)
    assert p.id == cenario["paciente"].id


def test_de_fora_recebe_404(db, cenario):
    intruso = SimpleNamespace(role=UserRole.TEACHER, id=999, escola_id=1)
    with pytest.raises(HTTPException) as exc:
        acesso_clinico.verificar_acesso_paciente(db, cenario["paciente"].id, intruso)
    assert exc.value.status_code == 404


def test_admin_mesma_escola_acessa(db, cenario):
    admin = SimpleNamespace(role=UserRole.ADMIN, id=2, escola_id=1)
    p = acesso_clinico.verificar_acesso_paciente(db, cenario["paciente"].id, admin)
    assert p.id == cenario["paciente"].id


def test_super_admin_acessa(db, cenario):
    su = SimpleNamespace(role=UserRole.SUPER_ADMIN, id=1, escola_id=None)
    p = acesso_clinico.verificar_acesso_paciente(db, cenario["paciente"].id, su)
    assert p.id == cenario["paciente"].id


def test_paciente_inexistente_404(db):
    user = SimpleNamespace(role=UserRole.SUPER_ADMIN, id=1, escola_id=None)
    with pytest.raises(HTTPException) as exc:
        acesso_clinico.verificar_acesso_paciente(db, 999999, user)
    assert exc.value.status_code == 404
