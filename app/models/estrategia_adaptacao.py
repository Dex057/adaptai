"""
📚 AdaptAI - Biblioteca de Estrategias de Adaptacao por transtorno/CID.

E a "base de informacoes" curada que associa um transtorno as diretrizes
concretas de adaptacao (linguagem, formato, apoios, avaliacao). Substitui o
improviso da IA + as regras soltas no codigo por uma base:
  - EDITAVEL pela equipe (governanca), com campo de FONTE;
  - injetada de forma deterministica nos geradores de tarefa (estrategias_service);
  - versionavel por escola (escola_id NULL = base global; preenchido = da escola).

`transtorno` casa com as flags de student.diagnosis (tea, tdah, dislexia,
discalculia, disgrafia, deficiencia_intelectual, superdotacao, ...). `cid` e
opcional, so para referencia/rastreio.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class EstrategiaAdaptacao(Base):
    __tablename__ = "estrategias_adaptacao"

    id = Column(Integer, primary_key=True, index=True)
    # NULL = estrategia base (global, vista por todos). Preenchido = so daquela escola.
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"),
                       nullable=True, index=True)

    transtorno = Column(String(60), nullable=False, index=True)   # ex: "tea", "dislexia"
    cid = Column(String(100), nullable=True)                      # opcional, referencia
    titulo = Column(String(200), nullable=True)
    diretrizes = Column(Text, nullable=False)                     # o que entra no prompt
    fonte = Column(String(500), nullable=True)                    # referencia/base

    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=100)

    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
    atualizado_em = Column(DateTime, default=_agora, onupdate=_agora)
