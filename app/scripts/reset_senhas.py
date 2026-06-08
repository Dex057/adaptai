# ============================================
# SCRIPT - Reset em massa de senhas
# ============================================
"""
Reseta senhas de usuarios e/ou alunos para uma senha padrao.

SEGURANCA:
- Por padrao roda em DRY-RUN (so lista, nao altera nada).
- Para aplicar de verdade, passar --apply.
- Possivel filtrar por tabela (users/students) e por role.
- A senha usada precisa passar por validar_senha_forte (forca minima).

EXECUTAR:
  # Preview (padrao - seguro):
  python -m app.scripts.reset_senhas

  # So tabela users:
  python -m app.scripts.reset_senhas --only users

  # So alunos (students):
  python -m app.scripts.reset_senhas --only students

  # So professores:
  python -m app.scripts.reset_senhas --only users --role teacher

  # Por email especifico:
  python -m app.scripts.reset_senhas --email admin@adaptai.com.br --apply

  # APLICAR (irreversivel):
  python -m app.scripts.reset_senhas --apply
"""

import argparse
import sys
import os

# Adicionar path do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import SessionLocal
from app.models.user import User
from app.models.student import Student
from app.core.security import get_password_hash
from app.schemas.user import validar_senha_forte


SENHA_PADRAO = "Nexus@2025"


def main():
    parser = argparse.ArgumentParser(description="Reseta senhas em massa.")
    parser.add_argument(
        "--apply", action="store_true",
        help="Aplica as mudancas. Sem esta flag, roda em dry-run (preview)."
    )
    parser.add_argument(
        "--only", choices=["users", "students", "both"], default="both",
        help="Qual tabela afetar (default: both)."
    )
    parser.add_argument(
        "--role", default=None,
        help="Filtra por role (ex: teacher, admin, coordinator, super_admin). So para users."
    )
    parser.add_argument(
        "--email", default=None,
        help="Afeta apenas o usuario/aluno com este email especifico."
    )
    parser.add_argument(
        "--senha", default=SENHA_PADRAO,
        help=f"Senha a ser usada (default: {SENHA_PADRAO})."
    )
    args = parser.parse_args()

    # 1. Validar que a senha passa na politica antes de qualquer coisa
    try:
        validar_senha_forte(args.senha)
    except ValueError as e:
        print(f"ERRO: senha fornecida nao passa na validacao de forca: {e}")
        sys.exit(1)

    print("=" * 60)
    print("RESET EM MASSA DE SENHAS" + ("  [DRY-RUN]" if not args.apply else "  [APLICANDO]"))
    print("=" * 60)
    print(f"Senha alvo:  {args.senha}")
    print(f"Escopo:      {args.only}" + (f" (role={args.role})" if args.role else ""))
    if args.email:
        print(f"Email:       {args.email}")
    print()

    db = SessionLocal()
    total_afetados = 0

    try:
        # ---------- USERS ----------
        if args.only in ("users", "both"):
            q = db.query(User)
            if args.role:
                q = q.filter(User.role == args.role)
            if args.email:
                q = q.filter(User.email == args.email)

            users = q.all()
            print(f"USERS  ({len(users)} encontrado(s)):")
            for u in users:
                role_str = u.role.value if hasattr(u.role, "value") else str(u.role)
                print(f"  - id={u.id:3d} | {role_str:15s} | {u.email}")
            total_afetados += len(users)

            if args.apply and users:
                novo_hash = get_password_hash(args.senha)
                for u in users:
                    u.hashed_password = novo_hash
                db.commit()
                print(f"  -> {len(users)} senha(s) atualizada(s) na tabela users")
            print()

        # ---------- STUDENTS ----------
        if args.only in ("students", "both"):
            # role nao se aplica a students
            q = db.query(Student)
            if args.email:
                q = q.filter(Student.email == args.email)

            students = q.all()
            print(f"STUDENTS  ({len(students)} encontrado(s)):")
            for s in students:
                print(f"  - id={s.id:3d} | {s.email}")
            total_afetados += len(students)

            if args.apply and students:
                novo_hash = get_password_hash(args.senha)
                for s in students:
                    s.hashed_password = novo_hash
                db.commit()
                print(f"  -> {len(students)} senha(s) atualizada(s) na tabela students")
            print()

        print("=" * 60)
        if args.apply:
            print(f"OK: {total_afetados} registro(s) resetado(s) para senha '{args.senha}'.")
            print("Comunique os usuarios afetados antes que tentem fazer login.")
        else:
            print(f"DRY-RUN: {total_afetados} registro(s) seriam afetados.")
            print(f"Para aplicar: rode novamente com --apply")
        print("=" * 60)

    except Exception as e:
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
