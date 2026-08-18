"""
Modelos para Materiais de Estudo
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship, deferred
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


class StatusMaterial(str, Enum):
    """Status de geração do material"""
    GERANDO = "gerando"
    DISPONIVEL = "disponivel"
    ERRO = "erro"


class Material(Base):
    """Material de estudo gerado por IA"""
    __tablename__ = "materiais"
    # Indice composto para GET /materiais/ (WHERE criado_por_id ORDER BY criado_em
    # DESC). Sem ele o MySQL varre a tabela e ordena em filesort - ver
    # migrations/012_materiais_conteudo_no_banco.sql.
    __table_args__ = (
        Index("ix_materiais_criado_por_criado_em", "criado_por_id", "criado_em"),
        {'schema': None},
    )

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    conteudo_prompt = Column(Text, nullable=False)
    tipo = Column(SQLEnum(TipoMaterial), nullable=False)
    materia = Column(String(100), nullable=False)
    serie_nivel = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=True)
    
    # Caminho do arquivo no storage (LEGADO - ver `conteudo` abaixo)
    arquivo_path = Column(String(255), nullable=True)  # Ex: "123_visual.html"

    # ------------------------------------------------------------------
    # 2026-08-18 - CONTEUDO NO BANCO, NAO EM DISCO
    # ------------------------------------------------------------------
    # O HTML/JSON gerado pela IA era gravado SO em backend/storage/materiais/
    # e a linha guardava apenas `arquivo_path`. O servico web do Railway roda
    # em disco EFEMERO: a cada redeploy os arquivos somem, enquanto a linha
    # continua com status='disponivel'. Resultado pro professor: o material
    # "some" da biblioteca (na verdade a linha esta la, o conteudo e que nao
    # existe mais) e GET /materiais/{id}/conteudo devolve 404.
    #
    # Mesma causa raiz ja corrigida para `ilustracoes` na migration 011 -
    # aqui e a mesma correcao: os bytes moram NA LINHA.
    #
    # `deferred`: a coluna NAO entra em `SELECT materiais.*`. Isso importa
    # alem do trafego - com colunas grandes no SELECT, o ORDER BY da listagem
    # vira filesort de linhas enormes e o MySQL responde
    # "1038 Out of sort memory". So carrega quando alguem le
    # `material.conteudo` de fato (rota de conteudo).
    conteudo = deferred(Column(MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True))

    # Conteudo das versoes ARQUIVADAS: {"1": "<html>...", "2": "..."}.
    # Separado de `historico_versoes` (que fica so com metadados e continua
    # sendo serializado no MaterialResponse) justamente para nao inflar a
    # resposta de todas as rotas de detalhe.
    conteudo_versoes = deferred(Column(JSON, nullable=True))
    
    # Metadados
    metadados = Column(JSON, nullable=True)  # Tokens usados, tempo de geração, etc
    status = Column(SQLEnum(StatusMaterial), default=StatusMaterial.GERANDO)
    
    # Versionamento: versao atual e historico de versoes anteriores arquivadas
    versao = Column(Integer, default=1)
    historico_versoes = Column(JSON, nullable=True)  # [{versao, arquivo_path, criado_em, conteudo_prompt}]
    
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
