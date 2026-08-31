"""
🎓 AdaptAI - Schemas de Prova
Schemas Pydantic para validação de dados
"""
import json

from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from datetime import datetime
from typing import Annotated, Optional, List, Dict, Any
from app.models.prova import (
    StatusProva, 
    StatusProvaAluno, 
    DificuldadeQuestao, 
    TipoQuestao
)


# ----------------------------------------------------------------------
# CORRECAO 2026-08-31 — 500 "Input should be a valid list" em prova gerada
# ----------------------------------------------------------------------
# Terceira reincidencia do mesmo defeito (ver os comentarios de 2026-08-11 em
# QuestaoGeradaResponse e QuestaoParaAluno): a IA devolve num campo de lista um
# texto corrido, provas.py grava o valor cru numa Column(JSON) — que aceita
# qualquer coisa — e o erro so aparece quando o FastAPI serializa a resposta,
# DEPOIS do db.commit() e FORA do try/except da rota. A prova fica gravada e
# ilegivel: /gerar, GET /{id} e PATCH /{id} devolvem 500 para sempre.
#
# Normalizar no schema conserta os dois lados de uma vez: as linhas ja gravadas
# tortas voltam a ser lidas, e uma lista continua passando intacta.
def _como_lista(valor):
    """Aceita o que a IA manda num campo de lista e devolve List[str].

    Lista e None passam intactos. Texto corrido vira `[texto]` — NUNCA `[]`,
    senao o criterio de correcao que o professor precisa some em silencio.
    """
    if valor is None or isinstance(valor, list):
        return valor
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        if texto.startswith("["):
            try:
                parsed = json.loads(texto)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [texto]
    return valor


ListaTexto = Annotated[Optional[List[str]], BeforeValidator(_como_lista)]


# ============= SCHEMAS DE CRIAÇÃO =============

class ProvaCreate(BaseModel):
    """Schema para criar uma nova prova"""
    titulo: str = Field(..., min_length=3, max_length=200, description="Título da prova")
    descricao: Optional[str] = Field(None, description="Descrição da prova")
    conteudo_prompt: str = Field(..., min_length=10, description="Prompt/conteúdo para IA gerar questões")
    materia: str = Field(..., min_length=2, max_length=100, description="Matéria da prova")
    serie_nivel: Optional[str] = Field(None, max_length=50, description="Série/nível escolar")
    quantidade_questoes: int = Field(20, ge=1, le=100, description="Quantidade de questões")
    tipo_questao: TipoQuestao = Field(TipoQuestao.MULTIPLA_ESCOLHA, description="Tipo das questões")
    dificuldade: DificuldadeQuestao = Field(DificuldadeQuestao.MEDIO, description="Dificuldade das questões")
    tempo_limite_minutos: Optional[int] = Field(None, ge=1, description="Tempo limite em minutos")
    pontuacao_total: float = Field(10.0, ge=0, description="Pontuação total da prova")
    nota_minima_aprovacao: float = Field(6.0, ge=0, le=10, description="Nota mínima para aprovação")


class QuestaoGeradaCreate(BaseModel):
    """Schema para criar uma questão gerada"""
    numero: int = Field(..., ge=1, description="Número da questão")
    enunciado: str = Field(..., min_length=10, description="Enunciado da questão")
    tipo: TipoQuestao = Field(..., description="Tipo da questão")
    dificuldade: Optional[DificuldadeQuestao] = Field(None, description="Dificuldade")
    opcoes: ListaTexto = Field(None, description="Opções de resposta")
    # 2026-08-11: obrigatorio impedia criar questao DISSERTATIVA por este
    # schema — ela nao tem resposta unica, e sim `criterios_avaliacao`.
    resposta_correta: Optional[str] = Field(None, description="Resposta correta (nulo em dissertativa)")
    criterios_avaliacao: ListaTexto = Field(None, description="Critérios de avaliação")
    pontuacao: float = Field(0.5, ge=0, description="Pontos da questão")
    explicacao: Optional[str] = Field(None, description="Explicação da resposta")
    tags: ListaTexto = Field(None, description="Tags/tópicos")


class ProvaAlunoCreate(BaseModel):
    """Schema para associar prova a um aluno"""
    prova_id: int = Field(..., description="ID da prova")
    aluno_id: int = Field(..., description="ID do aluno")


class RespostaAlunoCreate(BaseModel):
    """Schema para registrar resposta do aluno"""
    questao_id: int = Field(..., description="ID da questão")
    resposta_aluno: str = Field(..., description="Resposta do aluno")
    tempo_resposta_segundos: Optional[int] = Field(None, ge=0, description="Tempo de resposta")


# ============= SCHEMAS DE RESPOSTA =============

class QuestaoGeradaResponse(BaseModel):
    """Schema de resposta de questão gerada"""
    id: int
    prova_id: int
    numero: Optional[int] = None
    enunciado: str
    tipo: TipoQuestao
    dificuldade: Optional[DificuldadeQuestao] = None
    opcoes: ListaTexto = None
    # ------------------------------------------------------------------
    # CORRECAO 2026-08-11 — 500 "Internal Server Error" em prova dissertativa
    # ------------------------------------------------------------------
    # Era `resposta_correta: str` (OBRIGATORIO). Questao DISSERTATIVA nao tem
    # resposta correta unica — o proprio prompt manda a IA deixar `opcoes` como
    # null e entregar `criterios_avaliacao` no lugar. A coluna no banco e
    # nullable, entao a prova era GRAVADA com sucesso...
    #
    # ...e o erro so estourava DEPOIS, quando o FastAPI serializava a resposta
    # com `response_model=ProvaResponse`. Pydantic recusava o None e levantava
    # ValidationError FORA do try/except da rota — por isso a resposta vinha
    # como "Internal Server Error" em text/plain (21 bytes), e nao como o JSON
    # {"detail": ...} que o handler da rota produz.
    #
    # Efeito colateral: cada tentativa deixava uma prova ORFA no banco, criada
    # com sucesso mas invisivel para o professor, que via apenas o erro.
    resposta_correta: Optional[str] = None
    criterios_avaliacao: ListaTexto = None
    pontuacao: float
    explicacao: Optional[str] = None
    tags: ListaTexto = None
    criado_em: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestaoParaAluno(BaseModel):
    """Schema de questão para o aluno (SEM resposta correta)"""
    id: int
    # 2026-08-11: `numero` vinha de questao_data.get("numero") — se a IA nao
    # numerasse, ficava None e a prova QUEBRAVA na hora de o aluno abrir,
    # com o mesmo 500 text/plain da geracao. Opcional aqui, com fallback de
    # exibicao no frontend.
    numero: Optional[int] = None
    enunciado: str
    tipo: TipoQuestao
    opcoes: ListaTexto = None
    pontuacao: float

    model_config = ConfigDict(from_attributes=True)


class ProvaResponse(BaseModel):
    """Schema de resposta de prova"""
    id: int
    titulo: str
    descricao: Optional[str]
    conteudo_prompt: str
    materia: str
    serie_nivel: Optional[str]
    quantidade_questoes: int
    tipo_questao: TipoQuestao
    dificuldade: DificuldadeQuestao
    tempo_limite_minutos: Optional[int]
    pontuacao_total: float
    nota_minima_aprovacao: float
    status: StatusProva
    criado_em: datetime
    atualizado_em: datetime
    criado_por_id: int
    questoes: List[QuestaoGeradaResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ProvaParaAluno(BaseModel):
    """Schema de prova para o aluno fazer"""
    id: int
    titulo: str
    descricao: Optional[str]
    materia: str
    serie_nivel: Optional[str]
    tempo_limite_minutos: Optional[int]
    pontuacao_total: float
    questoes: List[QuestaoParaAluno] = []

    model_config = ConfigDict(from_attributes=True)


class RespostaAlunoResponse(BaseModel):
    """Schema de resposta do aluno"""
    id: int
    prova_aluno_id: int
    questao_id: int
    resposta_aluno: str
    esta_correta: Optional[bool]
    pontuacao_obtida: Optional[float]
    pontuacao_maxima: Optional[float]
    feedback: Optional[str]
    tempo_resposta_segundos: Optional[int]
    respondido_em: datetime

    model_config = ConfigDict(from_attributes=True)


class ProvaAlunoResponse(BaseModel):
    """Schema de resposta de prova do aluno"""
    id: int
    prova_id: int
    aluno_id: int
    status: StatusProvaAluno
    data_atribuicao: datetime
    data_inicio: Optional[datetime]
    data_conclusao: Optional[datetime]
    data_correcao: Optional[datetime]
    pontuacao_obtida: Optional[float]
    pontuacao_maxima: Optional[float]
    nota_final: Optional[float]
    aprovado: Optional[bool]
    tempo_gasto_minutos: Optional[int]
    analise_ia: Optional[Dict[str, Any]]
    feedback_ia: Optional[str]
    respostas: List[RespostaAlunoResponse] = []
    prova: Optional[ProvaResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ============= SCHEMAS DE ATUALIZAÇÃO =============

class ProvaUpdate(BaseModel):
    """Schema para atualizar prova"""
    titulo: Optional[str] = Field(None, min_length=3, max_length=200)
    descricao: Optional[str] = None
    status: Optional[StatusProva] = None
    tempo_limite_minutos: Optional[int] = Field(None, ge=1)
    pontuacao_total: Optional[float] = Field(None, ge=0)
    nota_minima_aprovacao: Optional[float] = Field(None, ge=0, le=10)


class ProvaAlunoUpdate(BaseModel):
    """Schema para atualizar prova do aluno"""
    status: Optional[StatusProvaAluno] = None
    data_inicio: Optional[datetime] = None
    data_conclusao: Optional[datetime] = None


# ============= SCHEMAS ESPECIAIS =============

class GerarProvaRequest(BaseModel):
    """
    Schema para solicitar geração de prova pela IA
    
    NOVO: Aceita aluno_ids e adaptacoes para criar prova contextualizada
    """
    titulo: str = Field(..., min_length=3, description="Título da prova")
    descricao: Optional[str] = None
    conteudo_prompt: str = Field(..., min_length=20, description="Descrição do conteúdo para gerar questões")
    materia: str = Field(..., description="Matéria")
    serie_nivel: Optional[str] = None
    quantidade_questoes: int = Field(20, ge=1, le=50, description="Quantidade de questões")
    tipo_questao: TipoQuestao = Field(TipoQuestao.MULTIPLA_ESCOLHA)
    dificuldade: DificuldadeQuestao = Field(DificuldadeQuestao.MEDIO)
    tempo_limite_minutos: Optional[int] = None
    pontuacao_total: float = Field(10.0, ge=0)
    nota_minima_aprovacao: float = Field(6.0, ge=0, le=10)
    # NOVO: IDs dos alunos para associar automaticamente
    aluno_ids: Optional[List[int]] = Field(default=None, description="IDs dos alunos para associar à prova")
    # NOVO: Adaptações necessárias (TEA, TDAH, etc.)
    adaptacoes: Optional[List[str]] = Field(default=None, description="Diagnósticos/adaptações dos alunos")


class IniciarProvaRequest(BaseModel):
    """Schema para aluno iniciar prova"""
    prova_aluno_id: int = Field(..., description="ID da associação prova-aluno")


class FinalizarProvaRequest(BaseModel):
    """Schema para aluno finalizar prova"""
    prova_aluno_id: int = Field(..., description="ID da associação prova-aluno")
    respostas: List[RespostaAlunoCreate] = Field(..., description="Lista de respostas")


class CorrigirProvaResponse(BaseModel):
    """Schema de resposta da correção"""
    prova_aluno_id: int
    pontuacao_obtida: float
    # TC-152: com questoes discursivas pendentes, `pontuacao_maxima` e o total JA
    # corrigido (nao o total da prova) e a nota ainda nao existe - dai
    # `nota_final`/`aprovado` nulos. Antes eram obrigatorios, o que forcava
    # inventar 0/False e reprovar o aluno por uma correcao que nem aconteceu.
    pontuacao_maxima: float
    nota_final: Optional[float] = None
    aprovado: Optional[bool] = None
    acertos: int
    erros: int
    percentual_acerto: float
    questoes_aguardando_correcao: int = 0
    nota_parcial: bool = False
    analise_ia: Dict[str, Any]
    feedback_ia: str
    respostas_detalhadas: List[RespostaAlunoResponse]

    model_config = ConfigDict(from_attributes=True)


class CorrigirQuestaoRequest(BaseModel):
    """
    TC-152: correcao manual de uma questao discursiva pelo professor.

    Questoes sem gabarito ficam com `esta_correta = None` na finalizacao e nao
    entram no calculo da nota ate passarem por aqui.
    """
    resposta_id: int = Field(..., description="ID da RespostaAluno a corrigir")
    pontuacao: float = Field(
        ..., ge=0,
        description="Pontos atribuidos (0 ate a pontuacao maxima da questao)"
    )
    feedback: Optional[str] = Field(
        None, max_length=5000, description="Comentario do professor sobre a resposta"
    )


class CorrigirQuestaoResponse(BaseModel):
    """Estado da prova do aluno depois de corrigir uma questao discursiva"""
    resposta_id: int
    pontuacao_obtida: float
    pontuacao_maxima: float
    esta_correta: Optional[bool]
    questoes_aguardando_correcao: int
    nota_final: Optional[float]
    aprovado: Optional[bool]
    status: StatusProvaAluno
    correcao_finalizada: bool


class ProvaListResponse(BaseModel):
    """Schema para listagem de provas"""
    id: int
    titulo: str
    materia: str
    quantidade_questoes: int
    status: StatusProva
    criado_em: datetime
    criado_por_id: int

    model_config = ConfigDict(from_attributes=True)


class ProvaAlunoListResponse(BaseModel):
    """Schema para listagem de provas do aluno"""
    id: int
    prova_id: int
    status: StatusProvaAluno
    data_atribuicao: datetime
    nota_final: Optional[float]
    aprovado: Optional[bool]
    prova: Optional[ProvaListResponse] = None

    model_config = ConfigDict(from_attributes=True)
