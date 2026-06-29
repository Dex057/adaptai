import json

from sqlalchemy import Column, Integer, String, Date, JSON, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# Condicoes que caracterizam publico-alvo do AEE (Atendimento Educacional
# Especializado), conforme a Politica Nacional de Educacao Especial / Decreto
# 7.611 e Resolucao CNE/CEB 4/2009: deficiencias, TEA/TGD e altas habilidades.
# Transtornos funcionais especificos (TDAH, dislexia, discalculia, disgrafia,
# TOD) NAO integram o publico-alvo legal do AEE e ficam de fora da contagem.
# Set centralizado para ajustar a regra num lugar so (sem cacar pelo codigo).
CONDICOES_PUBLICO_AEE = frozenset({
    "tea",
    "sindrome_down",
    "deficiencia_intelectual",
    "deficiencia_visual",
    "deficiencia_auditiva",
    "deficiencia_fisica",
    "altas_habilidades",
})


class Student(Base):
    __tablename__ = "students"
    __table_args__ = {'schema': None}

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant: vinculação com escola
    escola_id = Column(Integer, ForeignKey("escolas.id"), nullable=True, index=True)
    
    # Dados básicos
    name = Column(String(255), nullable=False)
    
    # Credenciais de acesso (opcional para alunos)
    email = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Dados escolares
    birth_date = Column(Date, nullable=True)
    grade_level = Column(String(50), nullable=False)  # "1º ano", "2º ano", etc
    turma = Column(String(50), nullable=True)  # "A", "B", "Manhã", etc
    matricula = Column(String(50), nullable=True, index=True)  # Número de matrícula
    
    # Diagnóstico e perfil em JSON
    diagnosis = Column(JSON, nullable=True)
    # Ex: {"tea": {"level": 1}, "tdah": true, "dislexia": false}
    
    profile_data = Column(JSON, nullable=True)
    # Ex: {"learning_style": "visual", "support_level": "medium", 
    #      "interests": ["dinossauros", "espaço"]}
    
    notes = Column(Text, nullable=True)  # Observações gerais
    
    # Foto do aluno (nome do arquivo em backend/storage/student_photos)
    foto_path = Column(String(255), nullable=True)
    
    # Professor responsável
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    escola = relationship("Escola", back_populates="alunos")
    teacher = relationship("User", back_populates="students")
    applications = relationship("Application", back_populates="student")
    answers = relationship("StudentAnswer", back_populates="student")
    performance_analyses = relationship("PerformanceAnalysis", back_populates="student")
    provas = relationship("ProvaAluno", back_populates="aluno")
    materiais = relationship("MaterialAluno", back_populates="aluno")
    materiais_adaptados_gerados = relationship("MaterialAdaptadoGerado", back_populates="student", cascade="all, delete-orphan")
    relatorios = relationship("Relatorio", back_populates="student", cascade="all, delete-orphan")
    diarios_aprendizagem = relationship("DiarioAprendizagem", back_populates="student", cascade="all, delete-orphan")
    redacoes = relationship("RedacaoAluno", back_populates="aluno", cascade="all, delete-orphan")

    @property
    def publico_aee(self) -> bool:
        """
        Marcador (derivado, sem coluna) de publico-alvo da Educacao Especial.

        Inferido do JSON `diagnosis`: True se houver ao menos uma condicao do
        publico-alvo do AEE (ver CONDICOES_PUBLICO_AEE) com valor verdadeiro.
        Read-only. Para filtro/indice em SQL nos agregados SEDUC, promover a
        coluna via migration Alembic quando a 1.0/Railway estiverem estaveis.
        """
        diag = self.diagnosis
        if not diag:
            return False
        if isinstance(diag, str):
            try:
                diag = json.loads(diag)
            except (ValueError, TypeError):
                return False
        if not isinstance(diag, dict):
            return False
        return any(bool(diag.get(cond)) for cond in CONDICOES_PUBLICO_AEE)
