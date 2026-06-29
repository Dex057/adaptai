import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def _env_int(name: str, default: int) -> int:
    """Le um inteiro de env var; cai no default se ausente/invalido.
    Mantem os knobs do engine reversiveis por env (Tarefa 3.2: sem cutover seco)."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ============================================================
# Engine recalibrado para Railway MySQL 8 (Tarefa 3.2).
# Antes (calibrado para o DBaaS antigo, "agressivo"): pool_recycle=180 e
# connect/read/write_timeout=60s. O Railway MySQL 8 nao precisa reciclar a
# conexao a cada 3 min nem de timeouts tao folgados. Todos os valores abaixo
# sao OVERRIDAVEIS por env var -> ajuste/rollback sem mudar codigo.
#   DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_RECYCLE, DB_POOL_TIMEOUT,
#   DB_CONNECT_TIMEOUT, DB_READ_TIMEOUT, DB_WRITE_TIMEOUT
# ============================================================
engine = create_engine(
    settings.db_url,
    pool_pre_ping=True,                                  # testa a conexao antes de usar (mantido)
    pool_size=_env_int("DB_POOL_SIZE", 10),
    max_overflow=_env_int("DB_MAX_OVERFLOW", 20),
    pool_recycle=_env_int("DB_POOL_RECYCLE", 1800),      # 30 min (antes 180s)
    pool_timeout=_env_int("DB_POOL_TIMEOUT", 30),        # antes 60s
    connect_args={
        "connect_timeout": _env_int("DB_CONNECT_TIMEOUT", 10),  # antes 60s
        "read_timeout": _env_int("DB_READ_TIMEOUT", 30),        # antes 60s
        "write_timeout": _env_int("DB_WRITE_TIMEOUT", 30),      # antes 60s
        "charset": "utf8mb4",                                   # UTF-8 completo (mantido)
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
