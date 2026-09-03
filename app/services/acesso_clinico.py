"""
app/services/acesso_clinico.py — Guard de acesso do vertical CLINICA.

Evolucao do padrao `verificar_acesso_aluno` (dependencies.py) para o mundo
multidisciplinar: o acesso a um paciente e validado por PERTENCIMENTO A EQUIPE
DO CASO, nao por posse individual. Mantem o padrao anti-IDOR do projeto:
retorna 404 (nao 403) quando o usuario nao pode ver o paciente — nao vaza a
existencia do prontuario.

Regras (em ordem):
  - SUPER_ADMIN: acesso a tudo.
  - ADMIN / COORDINATOR (papel de sistema) da MESMA escola: acesso.
  - Profissional com papel amplo (RESPONSAVEL_TECNICO/COORDENADOR/ADMIN_CLINICA)
    na mesma escola: acesso a todos os pacientes do tenant.
  - Demais profissionais: acesso apenas aos pacientes de cuja equipe do caso
    participam (equipe_caso ativa).
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.clinica_core import (
    Paciente, Profissional, EquipeCaso, AuditoriaAcesso, AcaoAuditoria,
    PapelProfissional,
)

_PAPEIS_AMPLOS = {
    PapelProfissional.RESPONSAVEL_TECNICO,
    PapelProfissional.COORDENADOR,
    PapelProfissional.ADMIN_CLINICA,
}

_NAO_ENCONTRADO = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Paciente nao encontrado",
)


def profissional_do_usuario(db: Session, current_user: User, escola_id: int):
    """Profissional ativo correspondente ao usuario nesta escola (ou None)."""
    return (
        db.query(Profissional)
        .filter(
            Profissional.usuario_id == current_user.id,
            Profissional.escola_id == escola_id,
            Profissional.ativo.is_(True),
        )
        .first()
    )


def _autorizar(db: Session, paciente: Paciente, current_user: User) -> None:
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    if (
        current_user.role in (UserRole.ADMIN, UserRole.COORDINATOR)
        and paciente.escola_id == current_user.escola_id
    ):
        return

    prof = profissional_do_usuario(db, current_user, paciente.escola_id)
    if prof:
        if prof.papel in _PAPEIS_AMPLOS:
            return
        membro = (
            db.query(EquipeCaso)
            .filter(
                EquipeCaso.paciente_id == paciente.id,
                EquipeCaso.profissional_id == prof.id,
                EquipeCaso.ativo.is_(True),
            )
            .first()
        )
        if membro:
            return

    # anti-IDOR: 404, nunca 403
    raise _NAO_ENCONTRADO


def verificar_acesso_paciente(
    db: Session,
    paciente_id: int,
    current_user: User,
    acao: AcaoAuditoria | None = None,
    recurso: str | None = None,
    recurso_id: int | None = None,
) -> Paciente:
    """Retorna o Paciente se o usuario tem acesso; senao levanta 404.
    Se `acao` for informada, grava a trilha de auditoria (best-effort)."""
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise _NAO_ENCONTRADO
    _autorizar(db, paciente, current_user)
    if acao is not None:
        registrar_acesso(db, paciente, current_user, acao, recurso, recurso_id)
    return paciente


def registrar_acesso(
    db: Session,
    paciente: Paciente,
    current_user: User,
    acao: AcaoAuditoria,
    recurso: str | None = None,
    recurso_id: int | None = None,
) -> None:
    """Grava uma linha de auditoria de acesso ao prontuario. Best-effort:
    nunca derruba o request (a trilha e importante, mas nao pode bloquear)."""
    try:
        reg = AuditoriaAcesso(
            escola_id=paciente.escola_id,
            usuario_id=current_user.id,
            paciente_id=paciente.id,
            acao=acao,
            recurso=recurso,
            recurso_id=recurso_id,
            criado_em=datetime.now(timezone.utc),
        )
        db.add(reg)
        db.commit()
    except Exception:
        db.rollback()
