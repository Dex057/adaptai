"""Ativa o modulo CLINICA para uma escola especifica.
Rode com a venv ativa: python _ativar_clinica.py
Depois pode apagar este arquivo."""
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.clinica_core import EscolaModulo, ModuloEscola
from app.models.escola import Escola

ESCOLA_ID = 1  # Escola Inclusiva Modelo (troque aqui se quiser outra)

db = SessionLocal()
esc = db.query(Escola).filter(Escola.id == ESCOLA_ID).first()
nome = getattr(esc, "nome", None) if esc else None
print(f"Escola alvo: id={ESCOLA_ID} nome={nome}")

row = (db.query(EscolaModulo)
       .filter(EscolaModulo.escola_id == ESCOLA_ID,
               EscolaModulo.modulo == ModuloEscola.CLINICA)
       .first())
if row:
    row.ativo = True
    row.desativado_em = None
    acao = "reativado"
else:
    db.add(EscolaModulo(escola_id=ESCOLA_ID, modulo=ModuloEscola.CLINICA,
                        ativo=True, ativado_em=datetime.now(timezone.utc)))
    acao = "criado"
db.commit()

print(f"CLINICA {acao} para escola {ESCOLA_ID}.")
print("\nModulos ativos da escola:")
for r in (db.query(EscolaModulo).filter(EscolaModulo.escola_id == ESCOLA_ID).all()):
    print(f"  {r.modulo.value:12} -> {'ATIVO' if r.ativo else 'inativo'}")
print("\nOK. Faca login com uma conta da escola 1 e atualize (F5).")
db.close()
