"""
Modelos para Materiais de Estudo
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from app.database import Base


class TipoMaterial(str, Enum):
    """Tipos de materiais disponíveis"""
    VISUAL = "visual"
    MAPA_MENTAL = "mapa_mental"
    RESUMO = "resumo"
    TEXTO_SIMPLIFICADO = "texto_simplificado"
    ROTEIRO_ESTUDO = "roteiro_estudo"
    ATIVIDADES = "atividades"
    # 2026-08-17: atividade de matematica/geometria. Diferente dos demais, o
    # conteudo gerado NAO e HTML: e um JSON com exercicios e a figura de cada
    # um em SVG (ver material_service.gerar_atividade_geometria e o viewer
    # GeometriaViewer.jsx no frontend).
    GEOMETRIA = "geometria"


class StatusMaterial(str, Enum):
    """Status de geração do material"""
    GERANDO = "gerando"
    DISPONIVEL = "disponivel"
    ERRO = "erro"


class Material(Base):
    """Material de estudo gerado por IA"""
    __tablename__ = "materiais"
    __table_args__ = {'schema': None}

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    conteudo_prompt = Column(Text, nullable=False)
    tipo = Column(SQLEnum(TipoMaterial), nullable=False)
    materia = Column(String(100), nullable=False)
    serie_nivel = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=True)
    
    # ------------------------------------------------------------------
    # 2026-08-17 — CONTEUDO NO BANCO, NAO EM DISCO
    # ------------------------------------------------------------------
    # O conteudo gerado era gravado APENAS em storage/materiais/{id}.html|json
    # e o banco guardava so o nome do arquivo (arquivo_path). O servico web do
    # Railway roda em disco EFEMERO (nao ha volume montado — ver railway.json):
    # a cada redeploy os arquivos somem enquanto a linha continua com
    # status='disponivel'. Resultado: GET /materiais/{id}/conteudo devolvia 404
    # para material que a Biblioteca jurava estar pronto.
    #
    # E exatamente o mesmo defeito que a migration 011 corrigiu para
    # `ilustracoes` (imagem_bytes); a correcao nunca tinha chegado aqui.
    #
    # `conteudo_gerado` e a fonte de verdade a partir deste deploy: HTML para
    # os tipos textuais/visuais, JSON serializado para mapa_mental e geometria.
    # LONGTEXT porque a atividade de geometria carrega varios SVGs inline
    # (TEXT, de 64KB, ficaria apertado). Variante Text no SQLite para os testes
    # (mesmo motivo do MEDIUMBLOB de Ilustracao: tipo MySQL-only quebra o
    # create_all() da suite).
    conteudo_gerado = Column(LONGTEXT().with_variant(Text, "sqlite"), nullable=True)

    # Legado: nome do arquivo no storage. Continua sendo escrito (o disco local
    # em dev/producao-com-volume ainda serve como cache), mas a LEITURA so cai
    # nele se conteudo_gerado estiver vazio — linhas anteriores a esta mudanca.
    arquivo_path = Column(String(255), nullable=True)  # Ex: "123_visual.html"
    
    # Metadados
    metadados = Column(JSON, nullable=True)  # Tokens usados, tempo de geração, etc
    status = Column(SQLEnum(StatusMaterial), default=StatusMaterial.GERANDO)
    
    # Versionamento: versao atual e historico de versoes anteriores arquivadas
    versao = Column(Integer, default=1)
    # [{versao, arquivo_path, conteudo, criado_em, conteudo_prompt}]
    # `conteudo` (2026-08-17) guarda a versao arquivada inline, pelo mesmo
    # motivo de conteudo_gerado: `arquivo_path` aponta para um arquivo que pode
    # ja nao existir.
    historico_versoes = Column(JSON, nullable=True)
    
    # Timestamps
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relacionamentos
    criado_por_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    criado_por = relationship("User", back_populates="materiais_criados")
    materiais_alunos = relationship("MaterialAluno", back_populates="material", cascade="all, delete-orphan")


class MaterialAluno(Base):
    """Associação entre material e aluno"""
    __tablename__ = "materiais_alunos"
    __table_args__ = {'schema': None}

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materiais.id"), nullable=False)
    aluno_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    
    # Datas de acesso
    data_disponibilizacao = Column(DateTime(timezone=True), server_default=func.now())
    data_primeira_visualizacao = Column(DateTime(timezone=True), nullable=True)
    data_ultima_visualizacao = Column(DateTime(timezone=True), nullable=True)
    total_visualizacoes = Column(Integer, default=0)
    
    # Interações do aluno
    favorito = Column(Integer, default=0)  # 0 = não, 1 = sim
    anotacoes_aluno = Column(Text, nullable=True)
    
    # Relacionamentos
    material = relationship("Material", back_populates="materiais_alunos")
    aluno = relationship("Student", back_populates="materiais")
