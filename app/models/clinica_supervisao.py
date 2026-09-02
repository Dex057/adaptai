"""
🏥 AdaptAI - Models de supervisao & qualidade ABA (vertical CLINICA).

Espelha 025_clinica_supervisao.sql.
- FidelidadeAplicacao: checklist de fidelidade de aplicacao por sessao.
- IOARegistro: concordancia entre observadores (IOA) por sessao.
(A aprovacao/assinatura do PTI fica em colunas de PlanoTerapeutico.)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, DECIMAL, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class FidelidadeAplicacao(Base):
    __tablename__ = "fidelidade_aplicacao"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False, index=True)
    observador_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    itens = Column(Text, nullable=True)          # JSON: [{"item": "...", "ok": true}]
    total_itens = Column(Integer, nullable=False, default=0)
    itens_ok = Column(Integer, nullable=False, default=0)
    percentual = Column(DECIMAL(5, 2), nullable=False, default=0)
    observacao = Column(String(500), nullable=True)
    criado_em = Column(DateTime, default=_agora)


class IOARegistro(Base):
    __tablename__ = "ioa_registros"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False, index=True)
    objetivo_id = Column(Integer, nullable=True)
    metodo = Column(String(30), nullable=True)   # tentativa / intervalo / frequencia
    observador2_nome = Column(String(255), nullable=True)
    concordancias = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    percentual = Column(DECIMAL(5, 2), nullable=False, default=0)
    observacao = Column(String(500), nullable=True)
    registrado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
