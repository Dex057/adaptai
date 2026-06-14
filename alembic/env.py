"""
============================================================
 Alembic env.py - AdaptAI
============================================================
 Liga o Alembic ao app:
   - URL do banco vem de app.core.config.settings.db_url (mesma fonte do app,
     que le DATABASE_URL / MYSQL_* do ambiente). Nenhum segredo no alembic.ini.
   - O metadata-alvo e o app.database.Base.metadata, populado por
     `from app.models import *` (registra TODAS as tabelas para o autogenerate).
============================================================
"""
from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# ------------------------------------------------------------
# Garante que o pacote 'app' seja importavel (rodando de backend/).
# ------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings           # noqa: E402
from app.database import Base                   # noqa: E402
# IMPORTA TODOS OS MODELS -> popula Base.metadata para o autogenerate ver tudo.
from app.models import *                        # noqa: E402,F401,F403

# Config do alembic.ini
config = context.config

# Injeta a URL real do banco em runtime (a partir das settings do app).
config.set_main_option("sqlalchemy.url", settings.db_url)

# Logging conforme alembic.ini (se houver secao configurada)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata alvo para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline: gera SQL sem conectar (util para revisar/gerar script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,            # detecta mudanca de tipo de coluna
        compare_server_default=True,  # detecta mudanca de default
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: conecta no banco e aplica/gera as migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
