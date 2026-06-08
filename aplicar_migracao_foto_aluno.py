"""
Script para aplicar migracao da FOTO DO ALUNO.
Adiciona a coluna foto_path na tabela students.

Uso:
    python aplicar_migracao_foto_aluno.py
"""
import pymysql
import sys
from app.core.config import settings


def executar_migracao():
    """Executa SQL de migracao (idempotente)."""

    print("=" * 60)
    print("🔧 MIGRAÇÃO: Foto do Aluno (students.foto_path)")
    print("=" * 60)

    try:
        print("\n📡 Conectando ao MySQL...")
        connection = pymysql.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            port=settings.MYSQL_PORT,
            charset='utf8mb4'
        )

        cursor = connection.cursor()
        print("✅ Conectado com sucesso!")

        print("\n🔄 Aplicando migração...")

        # Verificar se a coluna ja existe (idempotente)
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'students'
            AND COLUMN_NAME = 'foto_path'
        """, (settings.MYSQL_DATABASE,))

        coluna_existe = cursor.fetchone()[0] > 0

        if coluna_existe:
            print("⚠️ Coluna 'foto_path' já existe, pulando...")
        else:
            cursor.execute("""
                ALTER TABLE students
                ADD COLUMN foto_path VARCHAR(255) DEFAULT NULL
                COMMENT 'Nome do arquivo da foto em backend/storage/student_photos'
            """)
            print("✅ Coluna 'foto_path' adicionada")

        connection.commit()
        print("\n✅ Migração aplicada com sucesso!")

        print("\n📊 Estrutura da tabela 'students':")
        cursor.execute("DESCRIBE students")
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
