"""
🏥 AdaptAI - Model de anexo do prontuario (vertical CLINICA).

Espelha 023_clinica_anexos.sql. Metadados do arquivo; os bytes ficam no volume
(ANEXOS_DIR). Servido por endpoint autenticado — dado sensivel de saude (LGPD).
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, timezone
from app.database import Base


def _agora():
    return datetime.now(timezone.utc)


class AnexoProntuario(Base):
    __tablename__ = "anexos_prontuario"

    id = Column(Integer, primary_key=True, index=True)
    escola_id = Column(Integer, ForeignKey("escolas.id", ondelete="CASCADE"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_original = Column(String(255), nullable=False)
    mime = Column(String(120), nullable=True)
    tamanho_bytes = Column(Integer, nullable=True)
    caminho = Column(String(500), nullable=False)
    categoria = Column(String(60), nullable=True)
    descricao = Column(String(500), nullable=True)
    enviado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=_agora)
