"""
Model para Materiais Adaptados Gerados
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship, deferred
from datetime import datetime, timezone
from app.database import Base


class MaterialAdaptadoGerado(Base):
    """
    Tabela para armazenar materiais adaptados gerados pela IA
    Salva o resultado completo em JSON
    """
    __tablename__ = "materiais_adaptados_gerados"
    # Indice composto para o historico (WHERE student_id ORDER BY created_at
    # DESC) - ver migrations/012_materiais_conteudo_no_banco.sql.
    __table_args__ = (
        Index("ix_mag_student_created", "student_id", "created_at"),
    )

    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    
    # Metadados da geração
    disciplina = Column(String(100), nullable=False)
    serie = Column(String(50), nullable=False)
    conteudo = Column(String(255), nullable=False)
    tipos_material = Column(JSON, nullable=False)  # Lista de tipos gerados
    
    # Resultado completo em JSON
    #
    # 2026-08-18 - `deferred`: esta coluna NAO entra mais em
    # `SELECT materiais_adaptados_gerados.*`.
    #
    # Causa raiz de "Nao foi possivel carregar os materiais" e do 500 em
    # GET /materiais-adaptados/historico/student/{id}:
    #
    #   pymysql.err.OperationalError: (1038, 'Out of sort memory, consider
    #   increasing server sort buffer size')
    #
    # A listagem fazia `db.query(MaterialAdaptadoGerado)` (todas as colunas)
    # com ORDER BY created_at DESC LIMIT 100. Desde que hq_tirinha e
    # album_figurinhas passaram a embutir imagens em base64 aqui dentro
    # (ate ~6,6MB por linha - ver ai_materiais_service._ilustrar_itens), o
    # filesort do MySQL passou a ter que carregar megabytes por linha no sort
    # buffer e estourava. Ou seja: o historico quebrava por causa do TAMANHO
    # de um campo que a listagem nem usa.
    #
    # Com deferred, o JSON so e buscado quando alguem le
    # `material.resultado_json` (rotas de detalhe, uma linha por vez).
    resultado_json = deferred(Column(JSON, nullable=False))
    
    # Informações de geração
    tempo_geracao = Column(Integer, nullable=True)  # Em segundos
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # TC-033/123/124: interacoes do aluno com o material.
    # Ate a migration 007 estas colunas nao existiam aqui - so em `materiais_alunos`
    # (model MaterialAluno), que e outro pipeline. Como o material gerado pelo
    # professor nunca passa por `materiais_alunos`, favoritar/marcar como lido/anotar
    # simplesmente nao tinha onde ser gravado para esses materiais. Mesmos nomes e
    # mesma semantica de MaterialAluno (favorito como Integer 0/1) para o front
    # reaproveitar o componente.
    favorito = Column(Integer, default=0)  # 0 = nao, 1 = sim
    lido = Column(Integer, default=0)  # 0 = nao, 1 = sim
    lido_em = Column(DateTime, nullable=True)
    anotacoes_aluno = Column(Text, nullable=True)

    # Relacionamentos
    student = relationship("Student", back_populates="materiais_adaptados_gerados")
    creator = relationship("User")
    
    def __repr__(self):
        return f"<MaterialAdaptadoGerado(id={self.id}, student_id={self.student_id}, disciplina={self.disciplina}, conteudo={self.conteudo})>"
