from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Engine: MySQL/DBaaS em producao; SQLite (sem pool/timeout do MySQL) em teste.
_db_url = settings.db_url

if _db_url.startswith("sqlite"):
    # SQLite (usado nos testes): os connect_args do MySQL nao valem aqui.
    engine = create_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        echo=settings.DEBUG,
    )
else:
    # MySQL/DBaaS: configuracao AGRESSIVA de pool + timeouts (inalterada).
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,  # CRITICO: Testa conexao antes de usar
        pool_size=10,        # AUMENTADO: Mais conexoes disponiveis
        max_overflow=20,     # AUMENTADO: Mais overflow
        pool_recycle=180,    # REDUZIDO: Reconecta a cada 3 minutos (DBaaS agressivo)
        pool_timeout=60,     # AUMENTADO: 1 minuto para pegar conexao
        connect_args={
            "connect_timeout": 60,   # 1 minuto para conectar
            "read_timeout": 60,      # 1 minuto de leitura
            "write_timeout": 60,     # 1 minuto de escrita
            "charset": "utf8mb4",    # Suporte completo UTF-8
            # 2026-08-11: `charset` sozinho nem sempre fixa a collation da sessao —
            # alguns proxies/DBaaS reabrem a conexao com o default do servidor. Sem
            # isto, acentos podiam ser gravados/lidos com collation divergente, o
            # que aparece na UI como "CiAancias". Ver docs/CORRECOES-2026-08-11.md.
            "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
        },
        echo=settings.DEBUG,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency para rotas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
