"""Setup da clinica no banco de PRODUCAO (Railway).
Uso (PowerShell), com a venv ativa:
  $env:PROD_DB_URL = "mysql+pymysql://root:SENHA@HOST_PUBLICO.proxy.rlwy.net:PORTA/railway"
  python _setup_producao.py
Passe a URL PUBLICA do Railway (host .proxy.rlwy.net, NAO o .internal).
Este passo so LISTA e CRIA tabelas que faltam (aditivo). Nao altera senha nem
ativa modulo ainda — a gente faz isso depois de ver os dados reais."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # registra TODOS os models em Base.metadata
from app.database import Base
from app.models.user import User
from app.models.escola import Escola

url = os.environ.get("PROD_DB_URL")
if not url:
    print("!! Defina PROD_DB_URL com a URL PUBLICA do MySQL do Railway antes de rodar.")
    raise SystemExit(1)

eng = create_engine(url, pool_pre_ping=True)
print(">> Conectando na producao e criando tabelas que faltam (seguro/aditivo)...")
Base.metadata.create_all(bind=eng)
print(">> create_all OK.\n")

db = sessionmaker(bind=eng)()

print("=== ESCOLAS (producao) ===")
for e in db.query(Escola).all():
    print(f"  id={e.id:<4} nome={getattr(e,'nome',None)}")

print("\n=== ADMINS/COORDS (producao) ===")
for u in db.query(User).order_by(User.escola_id).all():
    r = str(getattr(u, "role", ""))
    if any(k in r.upper() for k in ("ADMIN", "COORD")):
        print(f"  email={u.email:<40} escola_id={str(u.escola_id):<6} role={r}")

print("\n=== MODULOS ja ativos (producao) ===")
from app.models.clinica_core import EscolaModulo
rows = db.query(EscolaModulo).all()
print("  (nenhum)" if not rows else "")
for r in rows:
    print(f"  escola_id={r.escola_id} modulo={r.modulo.value} ativo={r.ativo}")
db.close()
print("\nOK. Me manda ESCOLAS + ADMINS pra decidir onde ativar e qual login usar.")
