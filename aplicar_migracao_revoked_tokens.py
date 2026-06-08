"""
Script para criar a tabela de tokens revogados (logout server-side).

Cria a tabela `revoked_tokens`, usada para invalidar refresh tokens no logout.
Idempotente: usa CREATE TABLE IF NOT EXISTS.

Uso:
    python aplicar_migracao_revoked_tokens.py
"""
import sys
import pymysql
from app.core.config import settings


def executar_migracao():
    print("=" * 60)
    print("🔧 MIGRAÇÃO: Tokens revogados (revoked_tokens)")
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

        print("\n🔄 Criando tabela (se nao existir)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                jti VARCHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NULL,
                revoked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_revoked_tokens_jti (jti)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        connection.commit()
        print("✅ Tabela 'revoked_tokens' pronta")

        print("\n📊 Estrutura da tabela 'revoked_tokens':")
        cursor.execute("DESCRIBE revoked_tokens")
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
