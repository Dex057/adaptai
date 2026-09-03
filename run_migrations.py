"""
Runner de migrations idempotente (MySQL) — roda no deploy, antes do uvicorn.

Como funciona:
  - Garante a tabela `schema_migrations` (registro do que ja foi aplicado).
  - BASELINE: se o banco ja existe (tabela `users` presente) e nada foi registrado
    ainda, marca TODAS as migrations atuais como aplicadas (o banco ja esta nesse
    estado) — nao re-executa nada. Isso torna a adocao segura em bancos existentes.
  - Banco NOVO (sem `users`): aplica todas as migrations em ordem, do zero.
  - Deploys seguintes: aplica apenas os arquivos .sql novos (nao registrados).

Seguro para rodar a cada start: em bancos ja em dia, so faz um SELECT barato.
Em SQLite (dev/testes) nao faz nada — la o schema vem do create_all.

Falha = sai com codigo !=0, e o `&&` no start impede o uvicorn de subir com um
banco meio-migrado (o Railway mantem a versao anterior no ar).
"""
import os
import sys
import glob
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MIG_DIR = os.path.join(BASE, "migrations")


def split_statements(sql: str):
    linhas = []
    for linha in sql.splitlines():
        if linha.strip().startswith("--"):
            continue
        linhas.append(linha)
    corpo = "\n".join(linhas)
    return [s.strip() for s in corpo.split(";") if s.strip()]


def conectar_com_retry(engine, tentativas=10, espera=3):
    ult = None
    for i in range(tentativas):
        try:
            conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql("SELECT 1")
            return conn
        except Exception as e:  # noqa: BLE001
            ult = e
            print(f"[migrations] banco indisponivel ({i+1}/{tentativas}): {e}")
            time.sleep(espera)
    raise ult


def main():
    from app.database import engine  # usa a URL/engine ja configurada do app

    url = str(engine.url)
    if url.startswith("sqlite"):
        print("[migrations] SQLite (dev/testes): nada a fazer (create_all cuida).")
        return 0

    conn = conectar_com_retry(engine)
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " filename VARCHAR(255) NOT NULL PRIMARY KEY,"
        " applied_at DATETIME NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )

    aplicadas = {r[0] for r in conn.exec_driver_sql(
        "SELECT filename FROM schema_migrations").fetchall()}
    arquivos = sorted(os.path.basename(f) for f in glob.glob(os.path.join(MIG_DIR, "*.sql")))

    if not aplicadas:
        tem_users = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'users'"
        ).scalar()
        if tem_users:
            for fn in arquivos:
                conn.exec_driver_sql(
                    "INSERT INTO schema_migrations (filename, applied_at) VALUES (%s, NOW())",
                    (fn,),
                )
            print(f"[migrations] BASELINE: {len(arquivos)} migrations marcadas como "
                  "aplicadas (banco ja existente). Nada foi re-executado.")
            return 0
        print("[migrations] banco novo (sem 'users'): aplicando tudo do zero.")

    novas = 0
    for fn in arquivos:
        if fn in aplicadas:
            continue
        caminho = os.path.join(MIG_DIR, fn)
        with open(caminho, encoding="utf-8") as fh:
            sql = fh.read()
        print(f"[migrations] aplicando {fn} ...")
        for stmt in split_statements(sql):
            conn.exec_driver_sql(stmt)
        conn.exec_driver_sql(
            "INSERT INTO schema_migrations (filename, applied_at) VALUES (%s, NOW())",
            (fn,),
        )
        print(f"[migrations]   OK {fn}")
        novas += 1

    print(f"[migrations] em dia ({novas} nova(s) aplicada(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
