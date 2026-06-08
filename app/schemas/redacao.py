"""
📝 AdaptAI - Schemas de Redação ENEM
Validação de dados para redações com correção por IA
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class StatusRedacaoEnum(str, Enum):
    RASCUNHO = "rascunho"
    SUBMETIDA = "submetida"
    CORRIGIDA = "corrigida"
    ANULADA = "anulada"


# ========================================
# SCHEMAS DE REQUEST
# ========================================

class GerarTemaRequest(BaseModel):
    """Solicitar geração de tema pela IA"""
    area_tematica: Optional[str] = Field(None, description="Área: tecnologia, meio_ambiente, saude, educacao, etc.")
    nivel_dificuldade: str = Field("medio", description="facil, medio, dificil")
    aluno_ids: Optional[List[int]] = Field(None, description="IDs dos alunos para atribuir")


class TemaRedacaoCreate(BaseModel):
    """Criar tema manualmente"""
    titulo: str = Field(..., min_length=5, max_length=300)
    tema: str = Field(..., min_length=20)
    proposta: str = Field(..., min_length=50)
    texto_motivador_1: Optional[str] = None
    texto_motivador_2: Optional[str] = None
    texto_motivador_3: Optional[str] = None
    texto_motivador_4: Optional[str] = None
    area_tematica: Optional[str] = None
    nivel_dificuldade: str = Field("medio")
    aluno_ids: Optional[List[int]] = None


class IniciarRedacaoRequest(BaseModel):
    """Aluno inicia uma redação"""
    tema_id: int
    aluno_id: int


class SalvarRascunhoRequest(BaseModel):
    """Salvar rascunho da redação"""
    redacao_id: int
    titulo_redacao: Optional[str] = Field(None, max_length=200)
    texto: str


class SubmeterRedacaoRequest(BaseModel):
    """Submeter redação para correção"""
    redacao_id: int
    titulo_redacao: Optional[str] = Field(None, max_length=200)
    texto: str = Field(..., min_length=50, description="Mínimo 50 caracteres")


# ========================================
# SCHEMAS DE RESPONSE
# ========================================

class CompetenciaENEM(BaseModel):
    """Uma competência do ENEM"""
    numero: int
    nome: str
    descricao: str
    nota: int  # 0-200
    nivel: str  # "Excelente", "Bom", "Mediano", etc.
    feedback: str
    descritor_nivel: Optional[str] = None  # descritor da rubrica para o nivel da nota
    criterios: Optional[List[Dict[str, Any]]] = None  # criterios avaliados na competencia


class TemaRedacaoBase(BaseModel):
    """Base do tema de redação"""
    id: int
    titulo: str
    tema: str
    proposta: str
    texto_motivador_1: Optional[str] = None
    texto_motivador_2: Optional[str] = None
    texto_motivador_3: Optional[str] = None
    texto_motivador_4: Optional[str] = None
    area_tematica: Optional[str] = None
    palavras_chave: Optional[List[str]] = None
    nivel_dificuldade: str
    ativo: bool = True
    criado_em: datetime

    model_config = ConfigDict(from_attributes=True)


class TemaRedacaoResponse(TemaRedacaoBase):
    """Resposta completa do tema"""
    pass


class TemaListResponse(BaseModel):
    """Lista resumida de temas"""
    id: int
    titulo: str
    area_tematica: Optional[str] = None
    nivel_dificuldade: str
    criado_em: datetime
    total_redacoes: int = 0
    total_corrigidas: int = 0

    model_config = ConfigDict(from_attributes=True)


class RedacaoAlunoBase(BaseModel):
    """Base da redação do aluno"""
    id: int
    tema_id: int
    aluno_id: int
    titulo_redacao: Optional[str] = None
    texto: Optional[str] = None
    quantidade_linhas: int = 0
    quantidade_palavras: int = 0
    status: StatusRedacaoEnum
    iniciado_em: datetime
    submetido_em: Optional[datetime] = None
    corrigido_em: Optional[datetime] = None
    
    # Notas por competência
    nota_competencia_1: Optional[int] = None
    nota_competencia_2: Optional[int] = None
    nota_competencia_3: Optional[int] = None
    nota_competencia_4: Optional[int] = None
    nota_competencia_5: Optional[int] = None
    
    # Feedbacks por competência
    feedback_competencia_1: Optional[str] = None
    feedback_competencia_2: Optional[str] = None
    feedback_competencia_3: Optional[str] = None
    feedback_competencia_4: Optional[str] = None
    feedback_competencia_5: Optional[str] = None
    
    # Nota final e feedback geral
    nota_final: Optional[int] = None
    feedback_geral: Optional[str] = None
    
    # Análise
    pontos_fortes: Optional[List[str]] = None
    pontos_melhoria: Optional[List[str]] = None
    sugestoes: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class RedacaoAlunoResponse(RedacaoAlunoBase):
    """Resposta completa da redação"""
    tema: Optional[TemaRedacaoBase] = None
    aluno_nome: Optional[str] = None


class RedacaoListResponse(BaseModel):
    """Item da lista de redações"""
    id: int
    tema_titulo: str
    status: StatusRedacaoEnum
    nota_final: Optional[int] = None
    submetido_em: Optional[datetime] = None
    corrigido_em: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CorrecaoENEMResponse(BaseModel):
    """Resposta da correção completa"""
    redacao_id: int
    nota_final: int  # 0-1000
    competencias: List[CompetenciaENEM]
    feedback_geral: str
    pontos_fortes: List[str]
    pontos_melhoria: List[str]
    sugestoes: List[str]
    nivel_geral: str  # "Excelente", "Muito Bom", etc.

    model_config = ConfigDict(from_attributes=True)


class HistoricoRedacoesResponse(BaseModel):
    """Histórico completo de redações do aluno"""
    total_redacoes: int
    total_corrigidas: int
    media_geral: Optional[float] = None
    melhor_nota: Optional[int] = None
    pior_nota: Optional[int] = None
    media_por_competencia: Dict[str, float] = {}
    evolucao: List[Dict[str, Any]] = []
    redacoes: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)
