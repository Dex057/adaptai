"""Passo final na PRODUCAO (Railway): ativa CLINICA numa escola e define senha
de um admin. Usa a mesma PROD_DB_URL ja setada na sessao.
  python _ativar_prod.py
"""
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # registra models
from app.models.user import User
from app.models.clinica_core import EscolaModulo, ModuloEscola
from app.core.security import get_password_hash

ESCOLA_ID = 1                                   # Escola Inclusiva Modelo (modelo/demo)
ADMIN_EMAIL = "admin@escolainclusiva.com.br"    # admin dessa escola
NOVA_SENHA = "AdaptAI@2026"                      # senha temporaria (troque depois)

url = os.environ.get("PROD_DB_URL")
if not url:
    print("!! PROD_DB_URL nao esta setado nesta sessao.")
    raise SystemExit(1)

db = sessionmaker(bind=create_engine(url, pool_pre_ping=True))()

# 1) ativa CLINICA
row = (db.query(EscolaModulo)
       .filter(EscolaModulo.escola_id == ESCOLA_ID,
               EscolaModulo.modulo == ModuloEscola.CLINICA).first())
if row:
    row.ativo = True; row.desativado_em = None
else:
    db.add(EscolaModulo(escola_id=ESCOLA_ID, modulo=ModuloEscola.CLINICA,
                        ativo=True, ativado_em=datetime.now(timezone.utc)))

# 2) define senha do admin
u = db.query(User).filter(User.email == ADMIN_EMAIL).first()
if not u:
    print(f"!! {ADMIN_EMAIL} nao encontrado na producao.")
    raise SystemExit(1)
u.hashed_password = get_password_hash(NOVA_SENHA)
u.is_active = True

db.commit()

print(f"OK produção: CLINICA ativo na escola {ESCOLA_ID}; senha de {ADMIN_EMAIL} = {NOVA_SENHA}")
print("Modulos da escola agora:")
for r in db.query(EscolaModulo).filter(EscolaModulo.escola_id == ESCOLA_ID).all():
    print(f"  {r.modulo.value:12} -> {'ATIVO' if r.ativo else 'inativo'}")
db.close()
