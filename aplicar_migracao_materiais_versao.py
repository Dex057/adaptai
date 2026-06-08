"""
Script para aplicar migracao de VERSIONAMENTO e NOVOS FORMATOS de materiais.

- Adiciona as colunas materiais.versao (INT) e materiais.historico_versoes (JSON).
- Estende o ENUM da coluna materiais.tipo para incluir os novos formatos
  (resumo, texto_simplificado, roteiro_estudo, atividades), de forma ADAPTATIVA:
  le a definicao atual, detecta o padrao de caixa (MAIUSCULAS x minusculas) e
  acrescenta os novos valores preservando os existentes. Se a coluna nao for um
  ENUM (por exemplo, VARCHAR), nenhuma alteracao de tipo e necessaria.

Idempotente: pode ser executado mais de uma vez sem efeitos colaterais.

Uso:
    python aplicar_migracao_materiais_versao.py
"""
import re
import sys
import pymysql
from app.core.config import settings

# Novos formatos (nomes dos membros do enum TipoMaterial no modelo).
NOVOS_FORMATOS = ["RESUMO", "TEXTO_SIMPLIFICADO", "ROTEIRO_ESTUDO", "ATIVIDADES"]


def _coluna_existe(cursor, tabela, coluna):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (settings.MYSQL_DATABASE, tabela, coluna),
    )
    return cursor.fetchone()[0] > 0


def _adicionar_colunas_versao(cursor):
    # versao
    if _coluna_existe(cursor, "materiais", "versao"):
        print("⚠️ Coluna 'versao' já existe, pulando...")
    else:
        cursor.execute(
            """
            ALTER TABLE materiais
            ADD COLUMN versao INT NOT NULL DEFAULT 1
            COMMENT 'Versao atual do material (incrementa a cada regeneracao)'
            """
        )
        print("✅ Coluna 'versao' adicionada")

    # historico_versoes
    if _coluna_existe(cursor, "materiais", "historico_versoes"):
        print("⚠️ Coluna 'historico_versoes' já existe, pulando...")
    else:
        cursor.execute(
            """
            ALTER TABLE materiais
            ADD COLUMN historico_versoes JSON DEFAULT NULL
            COMMENT 'Versoes anteriores arquivadas [{versao, arquivo_path, criado_em, conteudo_prompt}]'
            """
        )
        print("✅ Coluna 'historico_versoes' adicionada")


def _estender_enum_tipo(cursor):
    """Estende o ENUM materiais.tipo com os novos formatos, preservando os existentes."""
    cursor.execute(
        """
        SELECT COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'materiais' AND COLUMN_NAME = 'tipo'
        """,
        (settings.MYSQL_DATABASE,),
    )
    row = cursor.fetchone()
    if not row:
        print("⚠️ Coluna 'tipo' não encontrada, pulando extensão de formatos...")
        return

    column_type, is_nullable, column_default = row[0], row[1], row[2]
    ct = (column_type or "").strip()

    if not ct.lower().startswith("enum("):
        print(f"ℹ️ Coluna 'tipo' não é ENUM (é '{ct[:40]}...'); novos formatos não exigem alteração de schema.")
        return

    # Valores atuais do enum
    existentes = re.findall(r"'((?:[^']|'')*)'", ct)
    existentes = [v.replace("''", "'") for v in existentes]

    # Detecta padrao de caixa: se nao ha NENHUMA minuscula, usa MAIUSCULAS
    usar_maiuscula = not any(c.islower() for v in existentes for c in v)
    novos = [n if usar_maiuscula else n.lower() for n in NOVOS_FORMATOS]

    faltantes = [n for n in novos if n not in existentes]
    if not faltantes:
        print("⚠️ ENUM 'tipo' já contém todos os novos formatos, pulando...")
        return

    final = existentes + faltantes
    valores_sql = ", ".join("'" + v.replace("'", "''") + "'" for v in final)

    nulo = "NULL" if str(is_nullable).upper() == "YES" else "NOT NULL"
    default_clause = ""
    if column_default is not None:
        default_clause = " DEFAULT '" + str(column_default).replace("'", "''") + "'"

    sql = f"ALTER TABLE materiais MODIFY COLUMN tipo ENUM({valores_sql}) {nulo}{default_clause}"
    cursor.execute(sql)
    print(f"✅ ENUM 'tipo' estendido com: {', '.join(faltantes)}")


def executar_migracao():
    print("=" * 60)
    print("🔧 MIGRAÇÃO: Materiais - versionamento e novos formatos")
    print("=" * 60)

    try:
        print("\n📡 Conectando ao MySQL...")
        connection = pymysql.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            port=settings.MYSQL_PORT,
            charset="utf8mb4",
        )
        cursor = connection.cursor()
        print("✅ Conectado com sucesso!")

        print("\n🔄 Aplicando migração...")
        _adicionar_colunas_versao(cursor)
        _estender_enum_tipo(cursor)

        connection.commit()
        print("\n✅ Migração aplicada com sucesso!")

        print("\n📊 Estrutura relevante da tabela 'materiais':")
        cursor.execute(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'materiais'
              AND COLUMN_NAME IN ('tipo', 'versao', 'historico_versoes')
            ORDER BY ORDINAL_POSITION
            """,
            (settings.MYSQL_DATABASE,),
        )
        for coluna in cursor.fetchall():
            print(f"  - {coluna[0]}: {coluna[1]}")

        cursor.close()
        connection.close()

        print("\n" + "=" * 60)
        print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ ERRO ao aplicar migração: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    executar_migracao()
