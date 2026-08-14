"""
🎨 AdaptAI - Model de Ilustração (apoio visual de conteúdo)

Ilustra materiais, questões de prova e temas de redação com duas fontes:
  - ARASAAC: pictogramas padronizados (gratuitos, licenca CC), ideais para
    apoio a compreensao de alunos com TEA/TDAH. So guardamos o id e a URL
    estatica do pictograma - a imagem mora no CDN da ARASAAC.
  - IA: ilustracao gerada por modelo de imagem (Flux via provedor). O arquivo
    e salvo em backend/storage/ilustracoes/ e servido por rota protegida.

REGRA DE PROPRIEDADE (conteudo x ponte): a ilustracao pertence ao CONTEUDO
(material/questao/tema), NUNCA ao aluno. Assim ela e gerada uma vez e
reaproveitada por toda a turma - o custo por imagem nao se multiplica por aluno.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from datetime import datetime, timezone
import enum
from app.database import Base


class ContextoIlustracao(str, enum.Enum):
    """A que tipo de conteudo a ilustracao esta vinculada."""
    MATERIAL = "material"
    QUESTAO = "questao"
    REDACAO_TEMA = "redacao_tema"


class FonteIlustracao(str, enum.Enum):
    """De onde veio a imagem."""
    ARASAAC = "arasaac"   # pictograma padronizado (CDN externo)
    IA = "ia"             # gerada por modelo de imagem


class StatusIlustracao(str, enum.Enum):
    """Ciclo de vida (relevante para IA, que gera de forma assincrona)."""
    PENDENTE = "pendente"   # solicitada, gerando
    PRONTA = "pronta"       # disponivel para exibir
    ERRO = "erro"           # falhou ao gerar


class Ilustracao(Base):
    """Uma imagem de apoio visual anexada a um conteudo.

    Referencia polimorfica "leve" (contexto_tipo + contexto_id) em vez de FKs
    separadas: o mesmo mecanismo serve material, questao e tema de redacao sem
    tres tabelas. A integridade do vinculo e garantida na camada de servico
    (checa que o conteudo existe e pertence ao professor antes de gravar).
    """
    __tablename__ = "ilustracoes"

    id = Column(Integer, primary_key=True, index=True)

    contexto_tipo = Column(SQLEnum(ContextoIlustracao), nullable=False, index=True)
    contexto_id = Column(Integer, nullable=False, index=True)

    fonte = Column(SQLEnum(FonteIlustracao), nullable=False)
    status = Column(SQLEnum(StatusIlustracao), default=StatusIlustracao.PRONTA, nullable=False)

    # Descricao curta (termo buscado no ARASAAC ou legenda da ilustracao IA).
    descricao = Column(String(500))

    # ARASAAC: id do pictograma + URL estatica no CDN.
    arasaac_id = Column(Integer, nullable=True)
    imagem_url = Column(String(1000), nullable=True)

    # IA: nome do arquivo salvo em storage/ilustracoes/ + prompt usado (auditoria).
    imagem_path = Column(String(500), nullable=True)
    prompt_ia = Column(Text, nullable=True)

    criado_por_id = Column(Integer, ForeignKey('users.id'))
    criado_em = Column(DateTime, default=lambda: datetime.now(timezone.utc))
