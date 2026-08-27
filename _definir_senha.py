"""Define uma senha temporaria para uma conta (para conseguir logar).
Rode com a venv ativa: python _definir_senha.py
Troque a senha depois dentro do app. Apague este arquivo em seguida."""
from app.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash

EMAIL = "admin@escolainclusiva.com.br"   # conta ADMIN da escola 1
NOVA_SENHA = "AdaptAI@2026"               # senha temporaria

db = SessionLocal()
u = db.query(User).filter(User.email == EMAIL).first()
if not u:
    print(f"Conta {EMAIL} nao encontrada.")
    raise SystemExit(1)

u.hashed_password = get_password_hash(NOVA_SENHA)
u.is_active = True
db.commit()
print(f"OK. Senha de {EMAIL} definida para: {NOVA_SENHA}")
print(f"  escola_id={u.escola_id} | role={getattr(u,'role',None)} | ativo={u.is_active}")
db.close()
