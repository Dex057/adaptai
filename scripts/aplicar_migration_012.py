"""
Aplica a migration 012 (materiais.conteudo_gerado + tipo 'geometria').

POR QUE UM SCRIPT E NAO SO O .sql
---------------------------------
O .sql precisa listar TODOS os valores do ENUM `materiais.tipo` no MODIFY
COLUMN, e o case depende de como a tabela foi criada (o SQLAlchemy usa os NOMES
dos membros do Enum Python -> maiusculas; um create manual pode ter usado
minusculas). Errar isso nao da erro: reescreve o ENUM com valores diferentes
dos gravados e as linhas existentes viram string vazia. Este script LE o ENUM
atual em INFORMATION_SCHEMA e so ACRESCENTA o valor novo, preservando o resto
exatamente como esta.

USO
---
    # 1) so inspeciona e mostra o que faria (padrao, nao escreve nada)
    python scripts/aplicar_migration_012.py

    # 2) aplica de fato
    python scripts/aplicar_migration_012.py --aplicar

A conexao vem de DATABASE_URL ou das MYSQL_* (mesma regra de app/core/config.py).

IDEMPOTENTE: rodar de novo depois de aplicado nao faz nada (detecta que a
coluna ja existe e que GEOMETRIA ja esta no ENUM).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

TABELA = "materiais"
COLUNA_NOVA = "conteudo_gerado"
VALOR_NOVO = "GEOMETRIA"  # confirmado abaixo contra o case real do ENUM


def _inspecionar(conn, schema):
    """Devolve (coluna_existe, valores_do_enum_tipo)."""
    linhas = conn.execute(
        text(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = :s AND TABLE_NAME = :t"
        ),
        {"s": schema, "t": TABELA},
    ).fetchall()

    if not linhas:
        raise SystemExit(
            f"Tabela '{TABELA}' nao existe no schema '{schema}'. "
            "Confira se DATABASE_URL aponta para o banco certo."
        )

    colunas = {nome: tipo for nome, tipo in linhas}
    tipo_col = colunas.get("tipo")
    if tipo_col is None:
        raise SystemExit(f"Coluna 'tipo' nao encontrada em '{TABELA}'.")

    valores = re.findall(r"'((?:[^']|'')*)'", tipo_col)
    return COLUNA_NOVA in colunas, [v.replace("''", "'") for v in valores]


def main():
    p = argparse.ArgumentParser(description="Aplica a migration 012.")
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="executa os ALTER TABLE (sem esta flag, so mostra o plano)",
    )
    args = p.parse_args()

    url = settings.db_url
    engine = create_engine(url, pool_pre_ping=True)
    schema = engine.url.database
    # Nunca imprime a senha.
    print(f"Banco: {engine.url.render_as_string(hide_password=True)}\n")

    with engine.connect() as conn:
        tem_coluna, enum_atual = _inspecionar(conn, schema)

        print(f"ENUM atual de {TABELA}.tipo: {enum_atual}")
        print(f"Coluna {COLUNA_NOVA}: {'JA EXISTE' if tem_coluna else 'FALTA'}")

        # Case do ENUM decidido pelo que esta no banco, nao por suposicao.
        ja_maiusculo = any(v.isupper() for v in enum_atual)
        valor_novo = VALOR_NOVO if ja_maiusculo else VALOR_NOVO.lower()
        tem_valor = valor_novo in enum_atual
        print(f"Valor '{valor_novo}' no ENUM: {'JA EXISTE' if tem_valor else 'FALTA'}\n")

        comandos = []
        if not tem_coluna:
            comandos.append(
                f"ALTER TABLE {TABELA} "
                f"ADD COLUMN {COLUNA_NOVA} LONGTEXT NULL AFTER arquivo_path"
            )
        if not tem_valor:
            # Preserva a ordem e o case existentes; so acrescenta no fim.
            lista = ", ".join("'%s'" % v.replace("'", "''") for v in enum_atual + [valor_novo])
            comandos.append(
                f"ALTER TABLE {TABELA} MODIFY COLUMN tipo ENUM({lista}) NOT NULL"
            )

        if not comandos:
            print("Nada a fazer — migration 012 ja esta aplicada.")
            return

        print("Comandos:")
        for c in comandos:
            print(f"  {c};")

        if not args.aplicar:
            print("\n(dry-run) Nada foi executado. Rode com --aplicar para valer.")
            return

        print()
        for c in comandos:
            conn.execute(text(c))
            print(f"OK: {c[:60]}...")
        conn.commit()

        tem_coluna, enum_final = _inspecionar(conn, schema)
        print(f"\nConferencia -> {COLUNA_NOVA}: {tem_coluna} | ENUM: {enum_final}")


if __name__ == "__main__":
    main()
