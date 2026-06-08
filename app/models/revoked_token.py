"""
Modelo de tokens revogados (denylist de refresh tokens).

Quando o usuario faz logout, o 'jti' do refresh token e gravado aqui. O
endpoint /auth/refresh recusa qualquer refresh token cujo jti esteja nesta
tabela, garantindo revogacao server-side de fato (e nao apenas limpeza do
storage no cliente).

Os registros podem ser limpos depois que expiram (expires_at < agora).
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    # jti (JWT ID) do refresh token revogado
    jti = Column(String(64), unique=True, index=True, nullable=False)
    # Quando o token expiraria naturalmente (para permitir limpeza posterior)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Quando foi revogado
    revoked_at = Column(DateTime(timezone=True), server_default=func.now())
