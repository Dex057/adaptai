"""
Lista contas administrativas, cria uma nova ou redefine a senha de uma existente.

Motivacao: o painel de consumo de IA (GET /api/v1/admin/ai-usage/painel) autentica
por Basic Auth contra um User com papel admin/super_admin. Quando ninguem sabe a
senha de nenhuma conta admin nao ha caminho pela aplicacao: /auth/forgot-password
depende de RESEND_API_KEY configurada, e scripts/create_admin.py so cria
admin@adaptai.com e desiste em silencio se ela ja existir.

O script opera no banco apontado por DATABASE_URL / MYSQL_* (app/core/config.py).
Para agir sobre PRODUCAO, e essa variavel que precisa apontar para la - ver o
passo a passo no fim deste docstring.

Uso (sempre da raiz do projeto):

    # ver quais contas admin existem - nao mostra nem altera senha
    python scripts/senha_admin.py --listar

    # criar uma conta admin nova  <- preferivel para uso do painel
    python scripts/senha_admin.py --criar painel@suaempresa.com

    # redefinir a senha de uma conta ja existente
    python scripts/senha_admin.py --redefinir alguem@dominio.com

A senha e sempre pedida por prompt oculto, nunca por argumento: argumento de
linha de comando fica no historico do shell e aparece na lista de processos da
maquina.

CUIDADO com --redefinir: a conta pode ser de uma pessoa real, que perde o acesso
no instante em que o comando roda. Quando o objetivo e so abrir o painel,
--criar nao derruba ninguem.

Como apontar para o banco de PRODUCAO (Railway), duas formas:

  a) Com a CLI do Railway, que injeta as variaveis do servico:
         railway run python scripts/senha_admin.py --criar painel@suaempresa.com

  b) Da sua maquina, com a URL PUBLICA do MySQL (Railway > MySQL > Connect):
         # PowerShell
         $env:DATABASE_URL="mysql+pymysql://user:senha@host.proxy.rlwy.net:PORTA/railway"
         python scripts/senha_admin.py --criar painel@suaempresa.com

Antes de gravar qualquer coisa o script mostra host e database e exige
confirmacao digitada - e a defesa contra rodar no banco errado.
"""
import argparse
import getpass
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.security import get_password_hash
from app.database import SessionLocal
from app.models.user import User, UserRole

PAPEIS_ADMIN = [UserRole.ADMIN, UserRole.SUPER_ADMIN]
MIN_SENHA = 12


def _alvo() -> str:
    """host/database do banco em uso, sem a senha. So para conferencia visual."""
    try:
        u = make_url(settings.db_url)
        return f"{u.host or '?'}:{u.port or '?'}/{u.database or '?'} (usuario {u.username})"
    except Exception:
        return "nao foi possivel interpretar a URL do banco"


def _confirmar(acao: str) -> bool:
    print(f"\n  Banco alvo : {_alvo()}")
    print(f"  Acao       : {acao}")
    print("\nConfira o host acima. Em producao ele aponta para o MySQL do Railway.")
    return input('Digite "confirmo" para prosseguir: ').strip().lower() == "confirmo"


def _pedir_senha() -> str | None:
    """Prompt oculto, com repeticao. Devolve None se o usuario desistir."""
    senha = getpass.getpass("Senha nova (nao aparece na tela): ")
    if len(senha) < MIN_SENHA:
        print(f"Senha muito curta - minimo {MIN_SENHA} caracteres. Nada foi alterado.")
        return None
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas nao conferem. Nada foi alterado.")
        return None
    return senha


def listar(db) -> int:
    contas = db.query(User).filter(User.role.in_(PAPEIS_ADMIN)).order_by(User.id).all()
    print(f"\nBanco: {_alvo()}")
    if not contas:
        print("\nNenhuma conta admin/super_admin encontrada.")
        print("Crie uma com:  python scripts/senha_admin.py --criar EMAIL")
        return 0
    print(f"\n{len(contas)} conta(s) com papel administrativo:\n")
    print(f"  {'id':>4}  {'email':<38} {'papel':<12} {'ativa':<6} escola_id")
    for u in contas:
        papel = u.role.value if u.role else "?"
        print(f"  {u.id:>4}  {u.email:<38} {papel:<12} "
              f"{('sim' if u.is_active else 'NAO'):<6} {u.escola_id or '-'}")
    print("\nSenhas nao sao exibiveis: o banco guarda hash bcrypt, que nao volta a\n"
          "ser texto. Para usar uma destas contas, redefina a senha dela.")
    return 0


def criar(db, email: str, papel: UserRole, nome: str) -> int:
    if db.query(User).filter(User.email == email).first():
        print(f"Ja existe usuario com o e-mail {email}.")
        print("Para trocar a senha dele, use --redefinir.")
        return 1
    if not _confirmar(f"CRIAR conta {papel.value} {email}"):
        print("Cancelado. Nada foi alterado.")
        return 1
    senha = _pedir_senha()
    if senha is None:
        return 1
    db.add(User(name=nome, email=email, hashed_password=get_password_hash(senha),
                role=papel, is_active=True))
    db.commit()
    print(f"\nConta criada: {email} ({papel.value})")
    print("Guarde a senha num gerenciador - ela nao pode ser recuperada do banco.")
    return 0


def redefinir(db, email: str) -> int:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        print(f"Nenhum usuario com o e-mail {email}.")
        print("Veja os existentes com --listar.")
        return 1
    papel = user.role.value if user.role else "?"
    if user.role not in PAPEIS_ADMIN:
        print(f"Atencao: {email} tem papel '{papel}', que NAO abre o painel.")
        print("A senha sera trocada mesmo assim, mas o acesso continuara negado (403).")
    if not user.is_active:
        print(f"Atencao: {email} esta inativa - o login segue bloqueado apos a troca.")
    if not _confirmar(f"REDEFINIR a senha de {email} (papel {papel}) - "
                      f"quem usa esta conta perde o acesso agora"):
        print("Cancelado. Nada foi alterado.")
        return 1
    senha = _pedir_senha()
    if senha is None:
        return 1
    user.hashed_password = get_password_hash(senha)
    db.commit()
    print(f"\nSenha de {email} redefinida.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Contas admin: listar, criar ou redefinir senha.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--listar", action="store_true",
                   help="lista contas admin/super_admin (nao altera nada)")
    g.add_argument("--criar", metavar="EMAIL", help="cria uma conta admin nova")
    g.add_argument("--redefinir", metavar="EMAIL",
                   help="troca a senha de uma conta existente")
    ap.add_argument("--papel", choices=["admin", "super_admin"], default="admin",
                    help="papel do --criar (padrao: admin, o menor que abre o painel)")
    ap.add_argument("--nome", default=None, help="nome exibido do --criar")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.listar:
            return listar(db)
        if args.criar:
            papel = UserRole.ADMIN if args.papel == "admin" else UserRole.SUPER_ADMIN
            return criar(db, args.criar, papel, args.nome or args.criar.split("@")[0])
        return redefinir(db, args.redefinir)
    except Exception as e:
        db.rollback()
        print(f"\nErro: {type(e).__name__}: {e}")
        print("Nada foi gravado.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
