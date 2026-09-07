"""
📚 Servico da Biblioteca de Estrategias de Adaptacao.

Duas funcoes centrais:
  - seed(db): semeia as estrategias-base (globais) a partir das boas praticas que
    hoje estao no codigo. Idempotente.
  - diretrizes_para_diagnostico(db, diagnosis, escola_id): dado o diagnostico do
    aluno (flags de student.diagnosis), devolve o BLOCO de diretrizes curadas para
    injetar no prompt dos geradores. Deterministico (sem IA), NUNCA levanta.

Regra de override: se a escola tem estrategia propria (ativa) para um transtorno,
usa a dela; senao, usa a base global.
"""
from typing import Optional

from app.core.logging_config import get_logger
from app.models.estrategia_adaptacao import EstrategiaAdaptacao

logger = get_logger(__name__)

FONTE_BASE = (
    "Boas praticas AdaptAI (base inicial - validar/expandir com a equipe). "
    "Fundamentacao: MEC-SECADI/UFC, 'Educacao Inclusiva e Tecnologia Assistiva' "
    "(Cadernos Pedagogicos: Politica Nacional de Educacao Especial Inclusiva, v.5, "
    "2026, ISBN 978-85-7485-666-7); Lei Brasileira de Inclusao - Lei 13.146/2015; "
    "Politica Nacional de Educacao Especial Inclusiva - Decreto 12.686/2025."
)

# Chaves = flags de student.diagnosis. Ordem tambem define a prioridade de leitura.
ESTRATEGIAS_BASE = [
    ("deficiencia_intelectual", "Deficiencia intelectual", 10,
     "Use frases de no maximo 12 palavras, uma ideia por frase. "
     "Vocabulario do cotidiano; se um termo tecnico for indispensavel, explique-o "
     "na mesma frase com exemplo concreto. Prefira voz ativa e ordem direta "
     "(sujeito-verbo-objeto). Ancore cada conceito abstrato num exemplo do dia a dia "
     "(casa, escola, mercado, transporte). Repita os termos-chave em vez de trocar "
     "por sinonimos. Divida processos em passos numerados e curtos. Evite metaforas, "
     "ironia, duplas negativas e condicionais encadeadas."),
    ("tea", "TEA (Transtorno do Espectro Autista)", 20,
     "Linguagem literal e concreta: sem metaforas, ironia ou sentido figurado. "
     "Estrutura previsivel e explicita, com comeco/meio/fim sinalizados. Antecipe "
     "mudancas de assunto com uma frase de transicao. Em niveis de suporte mais altos "
     "(2 e 3): frases muito curtas, apoio visual em cada etapa e um comando por vez."),
    ("tdah", "TDAH", 30,
     "Blocos curtos, cada um com titulo proprio, para sustentar a atencao. Destaque o "
     "essencial no inicio de cada bloco (mais importante primeiro). Evite paredes de "
     "texto: no maximo 4 linhas por paragrafo. Instrucoes objetivas e diretas."),
    ("dislexia", "Dislexia", 40,
     "Frases curtas e diretas; evite palavras longas e pouco frequentes. Separe silabas "
     "de termos dificeis na primeira ocorrencia (ex: fo-tos-sin-te-se). Nao use texto "
     "em CAIXA ALTA nem blocos em italico. Prefira fonte clara e bom espacamento."),
    ("discalculia", "Discalculia", 50,
     "Apresente numeros sempre com apoio concreto e unidade explicita. Quebre calculos "
     "em etapas visiveis; evite varias operacoes na mesma frase. Use apoio visual "
     "(barras, agrupamentos) para quantidades."),
    ("disgrafia", "Disgrafia", 60,
     "Prefira atividades de marcar/ligar/escolher a atividades de escrita extensa. "
     "Quando exigir escrita, limite a respostas de ate uma frase."),
    ("superdotacao", "Altas habilidades / superdotacao", 70,
     "Inclua ao menos uma extensao de aprofundamento por secao. Proponha uma pergunta "
     "aberta que conecte o tema a outra area do conhecimento."),
]


def seed(db) -> int:
    """Insere as estrategias-base globais que ainda nao existem. Idempotente.
    Retorna quantas foram inseridas."""
    inseridas = 0
    for transtorno, titulo, ordem, diretrizes in ESTRATEGIAS_BASE:
        existe = (
            db.query(EstrategiaAdaptacao)
            .filter(EstrategiaAdaptacao.escola_id.is_(None),
                    EstrategiaAdaptacao.transtorno == transtorno)
            .first()
        )
        if existe:
            continue
        db.add(EstrategiaAdaptacao(
            escola_id=None, transtorno=transtorno, titulo=titulo,
            diretrizes=diretrizes, fonte=FONTE_BASE, ativo=True, ordem=ordem,
        ))
        inseridas += 1
    if inseridas:
        db.commit()
    return inseridas


def _flags_ativas(diagnosis) -> list:
    if not isinstance(diagnosis, dict):
        return []
    ativos = []
    for transtorno, _titulo, _ordem, _d in ESTRATEGIAS_BASE:
        if diagnosis.get(transtorno):
            ativos.append(transtorno)
    # tolera chaves extras cadastradas pela escola que nao estao na base
    for k, v in diagnosis.items():
        if v is True and k not in ativos and k not in (
            "tea_nivel", "caracteristicas", "pontos_fortes", "dificuldades", "jornada", "estrategias_kb"
        ):
            ativos.append(k)
    return ativos


def diretrizes_para_diagnostico(db, diagnosis, escola_id: Optional[int] = None) -> str:
    """Bloco de diretrizes curadas para os transtornos do aluno. "" se nao houver.
    Override: estrategia da escola tem prioridade sobre a base global."""
    try:
        transtornos = _flags_ativas(diagnosis)
        if not transtornos:
            return ""
        blocos = []
        for t in transtornos:
            q = db.query(EstrategiaAdaptacao).filter(
                EstrategiaAdaptacao.transtorno == t,
                EstrategiaAdaptacao.ativo.is_(True),
            )
            # prioridade: estrategia da escola; se nao houver, a base global
            escolares = [e for e in q.all()
                         if escola_id is not None and e.escola_id == escola_id]
            usar = escolares or [e for e in q.all() if e.escola_id is None]
            for e in sorted(usar, key=lambda x: x.ordem or 100):
                titulo = e.titulo or e.transtorno
                blocos.append("- %s: %s" % (titulo, (e.diretrizes or "").strip()))
        if not blocos:
            return ""
        return (
            "\n\n=== ESTRATEGIAS DE ADAPTACAO (biblioteca curada) ===\n"
            + "\n".join(blocos)
            + "\nAplique estas diretrizes ao conteudo, sem mencionar diagnosticos ao aluno.\n"
        )
    except Exception:
        logger.warning("diretrizes_para_diagnostico falhou (escola_id=%s)", escola_id, exc_info=True)
        return ""
