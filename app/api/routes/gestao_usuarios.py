"""
Gestao de contas de professor/coordenador pela propria escola.

Preenche o buraco entre o onboarding (checkout cria 1 ADMIN) e o uso real: nao
havia rota para a escola criar logins individuais para seus professores, entao
na pratica todos compartilhavam uma conta. Aqui o ADMIN da escola provisiona,
edita, ativa/desativa e dispara reset de senha - sempre escopado ao proprio
escola_id.

Nao e um novo modelo de "perfil": e o CRUD que faltava sobre o User(role) +
escola_id que ja existiam. Privilegios continuam vindo de UserRole.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import ProfessorCreate, ProfessorUpdate, UserResponse
from app.api.dependencies import require_admin
from app.core.security import (
    get_password_hash,
    create_password_reset_token,
    password_reset_fingerprint,
)
from app.core.tenant import enforce_limite_professores
from app.core.config import settings
from app.services.email_service import send_password_reset_email

router = APIRouter(prefix="/escola/professores", tags=["🏫 Gestão de Professores"])


def _minha_escola_id(current_user: User) -> int:
    """A escola do admin logado. 400 se a conta nao estiver vinculada a uma."""
    if not current_user.escola_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sua conta não está vinculada a uma escola.",
        )
    return current_user.escola_id


def _professor_da_escola(db: Session, professor_id: int, escola_id: int) -> User:
    professor = db.query(User).filter(
        User.id == professor_id,
        User.escola_id == escola_id,
    ).first()
    if not professor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Professor não encontrado nesta escola",
        )
    return professor


@router.get("/", response_model=List[UserResponse])
def listar_professores(
    incluir_inativos: bool = True,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lista os usuarios (professores, coordenadores, admins) da minha escola."""
    escola_id = _minha_escola_id(current_user)
    query = db.query(User).filter(User.escola_id == escola_id)
    if not incluir_inativos:
        query = query.filter(User.is_active.isnot(False))
    return query.order_by(User.name).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def criar_professor(
    dados: ProfessorCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Cria uma conta de professor/coordenador na minha escola, com senha inicial
    definida pelo admin. O professor entra com email + senha e ja nasce vinculado
    a esta escola (herda escola_id - nunca NULL).
    """
    escola_id = _minha_escola_id(current_user)

    if db.query(User).filter(User.email == dados.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um usuário com este e-mail",
        )

    enforce_limite_professores(db, current_user)

    novo = User(
        name=dados.name,
        email=dados.email,
        hashed_password=get_password_hash(dados.password),
        role=UserRole(dados.role.value),
        escola_id=escola_id,
        is_active=True,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.patch("/{professor_id}", response_model=UserResponse)
def atualizar_professor(
    professor_id: int,
    dados: ProfessorUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Renomeia, troca role (teacher/coordinator) ou ativa/desativa um professor da escola."""
    escola_id = _minha_escola_id(current_user)
    professor = _professor_da_escola(db, professor_id, escola_id)

    # Nao deixar o admin se trancar para fora (rebaixar/desativar a propria conta).
    if professor.id == current_user.id and (dados.is_active is False or dados.role is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode alterar o próprio papel ou desativar a própria conta",
        )

    # Outra conta admin/super_admin da escola nao se mexe por esta rota.
    if professor.id != current_user.id and professor.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Não é possível editar outra conta de administrador por aqui",
        )

    if dados.name is not None:
        professor.name = dados.name
    if dados.role is not None:
        professor.role = UserRole(dados.role.value)
    if dados.is_active is not None:
        professor.is_active = dados.is_active

    db.commit()
    db.refresh(professor)
    return professor


@router.post("/{professor_id}/reset-senha")
def reset_senha_professor(
    professor_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Dispara o e-mail de redefinicao de senha para o professor (mesmo fluxo do
    'esqueci minha senha' em auth.py). Nao expoe nem define senha nova aqui.
    """
    escola_id = _minha_escola_id(current_user)
    professor = _professor_da_escola(db, professor_id, escola_id)

    fp = password_reset_fingerprint(professor.hashed_password)
    token = create_password_reset_token(professor.email, fp)
    reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/redefinir-senha?token={token}"
    enviado = send_password_reset_email(professor.email, reset_link)

    return {
        "message": (
            "E-mail de redefinição de senha enviado."
            if enviado
            else "Não foi possível enviar o e-mail agora. Tente novamente mais tarde."
        ),
        "email_enviado": enviado,
    }
