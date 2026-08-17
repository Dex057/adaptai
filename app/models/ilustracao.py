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
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, LargeBinary
from sqlalchemy.dialects.mysql import MEDIUMBLOB
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

    # IA: bytes da imagem gravados NO PROPRIO BANCO (nao em disco) - o servico
    # web do Railway roda em disco efemero, sem volume persistente; um arquivo
    # em storage/ilustracoes/ sumia no proximo deploy enquanto esta linha
    # continuava dizendo status=PRONTA (ver docs/CORRECOES-2026-08-11.md).
    # MEDIUMBLOB (ate 16MB) sobra folgado para um PNG de ~150-400KB. Variante
    # SQLite (LargeBinary generico) porque testes/dev usam SQLite via
    # create_all() - sem isso, MEDIUMBLOB nao compila fora do MySQL e
    # Base.metadata.create_all() falha, derrubando toda a suite (silenciosamente,
    # via pytest.skip no conftest - achado no code review antes do commit).
    imagem_bytes = Column(MEDIUMBLOB().with_variant(LargeBinary, "sqlite"), nullable=True)
    # legado: nome do arquivo que ERA salvo em storage/ilustracoes/. Mantido
    # so para auditoria de linhas antigas (o arquivo em si ja nao existe mais
    # em produção) - nao e mais escrito por codigo novo.
    imagem_path = Column(String(500), nullable=True)
    prompt_ia = Column(Text, nullable=True)

    criado_por_id = Column(Integer, ForeignKey('users.id'))
    criado_em = Column(DateTime, default=lambda: datetime.now(timezone.utc))
