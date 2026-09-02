from app.database import SessionLocal
from app.models.user import User
from app.core.security import verify_password

EMAIL = "admin@escolainclusiva.com.br"
SENHA = "AdaptAI@2026"

db = SessionLocal()
u = db.query(User).filter(User.email == EMAIL).first()
print("conta existe:", bool(u))
if u:
    print("email  :", repr(u.email))
    print("ativo  :", u.is_active)
    print("role   :", getattr(u, "role", None))
    print("escola :", u.escola_id)
    print("hash[:7]:", (u.hashed_password or "")[:7])
    print("SENHA CONFERE:", verify_password(SENHA, u.hashed_password))
db.close()
