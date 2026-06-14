"""
============================================================
 AdaptAI - SEED DE DEMONSTRACAO  (Opcao 2: tenants isolados)
============================================================
Popula o banco com dados ficticios para APRESENTACAO.

CARACTERISTICAS DE SEGURANCA:
- Cria ESCOLAS e USUARIOS demo isolados (multi-tenant).
- TODOS os registros levam o prefixo [DEMO] no nome/titulo.
- Nomes de escolas/profissionais/alunos sao FICTICIOS (nao instituicoes reais).
- Usa a MESMA config do backend (mesmo DATABASE_URL do Railway).
- NAO altera nenhum dado existente: apenas insere.
- Modo --limpar remove SOMENTE o que este seed criou (todas as escolas demo).

USO:
    python seed_demo.py            # popula (1 escola principal + 20 escolas SEDUC)
    python seed_demo.py --limpar   # remove tudo que o seed criou
    python seed_demo.py --reset    # limpa e popula de novo
    python seed_demo.py --simples  # popula SO a escola principal (rapido)

LOGIN DEMO (apos popular):
    Email: demo@adaptai.com.br
    Senha: demo123
============================================================
"""
import sys
import random
from datetime import datetime, timedelta, timezone, date

# Garante import do pacote app/ quando rodando da raiz do backend
sys.path.insert(0, ".")

from sqlalchemy import or_
from app.database import SessionLocal
from app.core.security import get_password_hash
from app.models import (
    Escola, ConfiguracaoEscola,
    User, UserRole,
    Student,
    Prova, QuestaoGerada, ProvaAluno, RespostaAluno,
    StatusProva, DificuldadeQuestao, TipoQuestao, StatusProvaAluno,
    TemaRedacao, RedacaoAluno, StatusRedacao,
    Relatorio,
    AnaliseQualitativa,
)

PREFIXO = "[DEMO]"
# Dominio usado para identificar TODAS as escolas/usuarios demo na limpeza
DEMO_DOMINIO = "@demo.adaptai.com.br"
ESCOLA_EMAIL = "escola.demo@adaptai.com.br"   # escola principal (login demo)
USUARIO_EMAIL = "demo@adaptai.com.br"
USUARIO_SENHA = "demo123"

random.seed(42)  # reprodutivel


def agora():
    return datetime.now(timezone.utc)


# ============================================================
# DADOS FICTICIOS
# ============================================================

# Pool de nomes para gerar alunos variados (ficticios)
NOMES = [
    "Helena Martins", "Théo Albuquerque", "Laura Nogueira", "Davi Ocampo",
    "Isabela Quintas", "Miguel Rocha", "Sofia Vasquez", "Arthur Bittencourt",
    "Cecília Prado", "Benjamin Tavares", "Alice Carvalho", "Gabriel Furtado",
    "Manuela Pires", "Lucas Andrade", "Valentina Cruz", "Pedro Henrique Sá",
    "Lara Macedo", "Bernardo Lima", "Maria Clara Reis", "Enzo Barreto",
    "Antonella Dias", "Heitor Cunha", "Lívia Moraes", "Samuel Pinto",
    "Beatriz Lopes", "Gustavo Teixeira", "Yasmin Castro", "Felipe Moreira",
    "Júlia Ramos", "Caio Mendonça",
]

DIAGNOSTICOS_POOL = [
    {"tea": {"level": 1}},
    {"tea": {"level": 2}},
    {"tdah": True},
    {"dislexia": True},
    {"tdah": True, "dislexia": True},
    {"tea": {"level": 1}, "tdah": True},
    {},
    {},
]

INTERESSES_POOL = [
    ["dinossauros", "espaço"], ["futebol", "games"], ["desenho", "animais"],
    ["trens", "mapas"], ["música", "dança"], ["super-heróis", "lego"],
    ["plantas", "culinária"], ["skate", "robótica"], ["leitura", "teatro"],
    ["números", "quebra-cabeça"], ["pintura", "natureza"], ["xadrez", "ciências"],
]

SERIES = ["1º ano", "2º ano", "3º ano", "4º ano", "5º ano"]
TURMAS = ["A", "B", "C"]

# 20 ESCOLAS - nomes FICTICIOS no padrao da rede estadual, municipios reais do PA.
# NAO sao instituicoes reais: nomes inventados para demonstracao SEDUC.
ESCOLAS_SEDUC = [
    ("EEEFM Rio Guamá", "Belém"),
    ("EEEM Professora Amélia Vasconcelos", "Belém"),
    ("EEEFM Cidade Nova", "Ananindeua"),
    ("EEEM Tapajós", "Santarém"),
    ("EEEFM Carajás", "Marabá"),
    ("EEEM Vale do Tocantins", "Castanhal"),
    ("EEEFM Professor Anísio Cardoso", "Abaetetuba"),
    ("EEEM Bragança Paulista do Norte", "Bragança"),
    ("EEEFM Cametá Velho", "Cametá"),
    ("EEEM Altamira Central", "Altamira"),
    ("EEEFM Parauapebas Sul", "Parauapebas"),
    ("EEEM Itaituba Rio Tapajós", "Itaituba"),
    ("EEEFM Tucuruí Hidrelétrica", "Tucuruí"),
    ("EEEM Barcarena Industrial", "Barcarena"),
    ("EEEFM Paragominas Norte", "Paragominas"),
    ("EEEM Redenção do Araguaia", "Redenção"),
    ("EEEFM Capanema Litoral", "Capanema"),
    ("EEEM Tailândia Verde", "Tailândia"),
    ("EEEFM Breves Marajó", "Breves"),
    ("EEEM Salinópolis Atlântico", "Salinópolis"),
]

MATERIAS = ["Matemática", "Português", "Ciências", "História", "Geografia"]

QUESTOES_BANCO = {
    "Matemática": [
        ("Quanto é 7 x 8?", ["A) 54", "B) 56", "C) 63", "D) 49"], "B) 56"),
        ("Qual fração equivale a 1/2?", ["A) 2/4", "B) 1/3", "C) 3/5", "D) 2/3"], "A) 2/4"),
        ("Quanto é 144 ÷ 12?", ["A) 11", "B) 13", "C) 12", "D) 14"], "C) 12"),
        ("Qual o perímetro de um quadrado de lado 5?", ["A) 25", "B) 10", "C) 20", "D) 15"], "C) 20"),
    ],
    "Português": [
        ("Qual palavra é um substantivo?", ["A) correr", "B) bonito", "C) casa", "D) rapidamente"], "C) casa"),
        ("Qual é o plural de 'cão'?", ["A) cãos", "B) cães", "C) cãoes", "D) cans"], "B) cães"),
        ("O que é um verbo?", ["A) ação", "B) qualidade", "C) lugar", "D) objeto"], "A) ação"),
        ("Qual frase está correta?", ["A) Nós vai", "B) Eles foi", "C) Nós fomos", "D) Eu vamos"], "C) Nós fomos"),
    ],
    "Ciências": [
        ("Qual planeta é o mais próximo do Sol?", ["A) Terra", "B) Mercúrio", "C) Marte", "D) Vênus"], "B) Mercúrio"),
        ("O que as plantas produzem na fotossíntese?", ["A) Gás carbônico", "B) Oxigênio", "C) Nitrogênio", "D) Hélio"], "B) Oxigênio"),
        ("Quantos ossos tem o corpo humano adulto?", ["A) 206", "B) 180", "C) 250", "D) 150"], "A) 206"),
        ("Qual é o estado da água a 0°C?", ["A) Gasoso", "B) Líquido", "C) Sólido", "D) Plasma"], "C) Sólido"),
    ],
    "História": [
        ("Em que ano o Brasil foi 'descoberto'?", ["A) 1500", "B) 1492", "C) 1808", "D) 1822"], "A) 1500"),
        ("Quem proclamou a Independência do Brasil?", ["A) D. João VI", "B) D. Pedro I", "C) Tiradentes", "D) D. Pedro II"], "B) D. Pedro I"),
        ("Qual povo construiu as pirâmides do Egito?", ["A) Romanos", "B) Gregos", "C) Egípcios", "D) Maias"], "C) Egípcios"),
        ("Em que continente fica o Brasil?", ["A) Europa", "B) Ásia", "C) África", "D) América do Sul"], "D) América do Sul"),
    ],
    "Geografia": [
        ("Qual é a capital do Brasil?", ["A) Rio de Janeiro", "B) São Paulo", "C) Brasília", "D) Salvador"], "C) Brasília"),
        ("Qual o maior rio do Brasil?", ["A) São Francisco", "B) Amazonas", "C) Paraná", "D) Tietê"], "B) Amazonas"),
        ("Quantos estados tem o Brasil?", ["A) 26", "B) 27", "C) 25", "D) 24"], "A) 26"),
        ("Qual oceano banha o litoral brasileiro?", ["A) Pacífico", "B) Índico", "C) Atlântico", "D) Ártico"], "C) Atlântico"),
    ],
}

TEMAS_REDACAO = [
    ("O desafio da inclusão escolar no Brasil", "Educação"),
    ("Impactos da tecnologia na aprendizagem", "Tecnologia"),
    ("A importância da preservação ambiental", "Meio Ambiente"),
]

FEEDBACK_COMP = {
    1: "Bom domínio da norma culta, com poucos desvios gramaticais.",
    2: "Compreendeu a proposta e desenvolveu o tema com pertinência.",
    3: "Argumentação consistente, com repertório sociocultural produtivo.",
    4: "Uso adequado de conectivos, garantindo a coesão do texto.",
    5: "Apresentou proposta de intervenção, faltando detalhar agentes.",
}

# Relatórios FICTÍCIOS de acompanhamento (conteudo generico de demonstracao).
RELATORIOS_DEMO = [
    ("Relatório Psicopedagógico", "Psicopedagogia", "DEMO-PP",
     "Documento de demonstração. Observações gerais de acompanhamento pedagógico, "
     "com evolução positiva em atenção e organização das tarefas.", {"tdah": True}),
    ("Relatório Fonoaudiológico", "Fonoaudiologia", "DEMO-FA",
     "Documento de demonstração. Acompanhamento de linguagem e comunicação, "
     "com ganhos graduais na fala e na compreensão.", {"tea": True}),
    ("Relatório de Terapia Ocupacional", "Terapia Ocupacional", "DEMO-TO",
     "Documento de demonstração. Trabalho de habilidades motoras e sensoriais, "
     "com boa adesão às atividades propostas.", {}),
    ("Relatório Psicológico", "Psicologia", "DEMO-PS",
     "Documento de demonstração. Acompanhamento socioemocional, com avanços "
     "na autorregulação e na interação com colegas.", {"tea": True, "tdah": True}),
    ("Relatório Neurológico", "Neurologia", "DEMO-NE",
     "Documento de demonstração. Acompanhamento de rotina, sem intercorrências "
     "relevantes registradas no período.", {}),
    ("Relatório de Fisioterapia", "Fisioterapia", "DEMO-FT",
     "Documento de demonstração. Acompanhamento motor e postural, "
     "com progressos na coordenação e no equilíbrio.", {}),
    ("Relatório Nutricional", "Nutrição", "DEMO-NU",
     "Documento de demonstração. Acompanhamento alimentar, "
     "com orientações de rotina e boa adesão familiar.", {}),
    ("Relatório de Musicoterapia", "Musicoterapia", "DEMO-MU",
     "Documento de demonstração. Atividades musicais voltadas à "
     "comunicação e à expressão, com engajamento crescente.", {"tea": True}),
]

PROFISSIONAIS_DEMO = [
    "[DEMO] Dra. Marina Fonseca", "[DEMO] Dr. Rafael Lemos",
    "[DEMO] Dra. Camila Andrade", "[DEMO] Dr. Bruno Carvalho",
    "[DEMO] Dra. Patrícia Moraes", "[DEMO] Dr. Eduardo Tanaka",
    "[DEMO] Dra. Juliana Beltrão", "[DEMO] Dr. Henrique Saldanha",
]


# ============================================================
# LIMPEZA (remove TODAS as escolas demo)
# ============================================================
def limpar(db):
    # Identifica todas as escolas demo: a principal (email fixo) + as SEDUC
    # (email no dominio demo). Tambem pega usuarios/alunos por dominio/prefixo.
    escolas = db.query(Escola).filter(
        or_(Escola.email == ESCOLA_EMAIL, Escola.email.like(f"%{DEMO_DOMINIO}"))
    ).all()
    if not escolas:
        print("Nada para limpar (nenhuma escola demo encontrada).")
        return

    escola_ids = [e.id for e in escolas]
    print(f"Removendo {len(escola_ids)} escola(s) demo...")

    alunos = db.query(Student).filter(Student.escola_id.in_(escola_ids)).all()
    aluno_ids = [a.id for a in alunos]
    usuarios = db.query(User).filter(User.escola_id.in_(escola_ids)).all()
    user_ids = [u.id for u in usuarios]

    prova_ids = []
    if user_ids:
        prova_ids = [p.id for p in db.query(Prova).filter(Prova.criado_por_id.in_(user_ids)).all()]

    prova_aluno_ids = []
    if aluno_ids or prova_ids:
        filtro = []
        if aluno_ids:
            filtro.append(ProvaAluno.aluno_id.in_(aluno_ids))
        if prova_ids:
            filtro.append(ProvaAluno.prova_id.in_(prova_ids))
        prova_aluno_ids = [pa.id for pa in db.query(ProvaAluno).filter(or_(*filtro)).all()]

    questao_ids = []
    if prova_ids:
        questao_ids = [q.id for q in db.query(QuestaoGerada).filter(QuestaoGerada.prova_id.in_(prova_ids)).all()]

    tema_ids = []
    if user_ids:
        tema_ids = [t.id for t in db.query(TemaRedacao).filter(TemaRedacao.criado_por_id.in_(user_ids)).all()]

    # ----- Delecao dos FILHOS para os PAIS (evita erro de FK) -----
    def del_in(model, col, ids):
        if ids:
            db.query(model).filter(col.in_(ids)).delete(synchronize_session=False)

    del_in(RespostaAluno, RespostaAluno.prova_aluno_id, prova_aluno_ids)
    del_in(RespostaAluno, RespostaAluno.questao_id, questao_ids)
    del_in(AnaliseQualitativa, AnaliseQualitativa.prova_aluno_id, prova_aluno_ids)
    del_in(ProvaAluno, ProvaAluno.id, prova_aluno_ids)
    del_in(QuestaoGerada, QuestaoGerada.id, questao_ids)
    del_in(Prova, Prova.id, prova_ids)
    del_in(RedacaoAluno, RedacaoAluno.aluno_id, aluno_ids)
    del_in(RedacaoAluno, RedacaoAluno.tema_id, tema_ids)
    del_in(TemaRedacao, TemaRedacao.id, tema_ids)
    del_in(Relatorio, Relatorio.student_id, aluno_ids)
    del_in(Student, Student.id, aluno_ids)
    del_in(User, User.id, user_ids)
    del_in(ConfiguracaoEscola, ConfiguracaoEscola.escola_id, escola_ids)
    del_in(Escola, Escola.id, escola_ids)

    db.commit()
    print("Escolas demo removidas com sucesso.")


# ============================================================
# RELATORIOS (ficticios, por aluno)
# ============================================================
def criar_relatorios(db, alunos, professor, por_aluno=(3, 5)):
    """Cria varios relatorios ficticios por aluno, especialidades e
    profissionais distintos dentro de cada aluno."""
    total = 0
    lo, hi = por_aluno
    hi = min(hi, len(RELATORIOS_DEMO), len(PROFISSIONAIS_DEMO))
    lo = min(lo, hi)
    for aluno in alunos:
        qtd = random.randint(lo, hi)
        modelos = random.sample(RELATORIOS_DEMO, k=qtd)
        profissionais = random.sample(PROFISSIONAIS_DEMO, k=qtd)
        for (tipo, especialidade, sigla, resumo, condicoes), profissional in zip(modelos, profissionais):
            emissao = agora() - timedelta(days=random.randint(20, 300))
            db.add(Relatorio(
                student_id=aluno.id,
                tipo=f"{PREFIXO} {tipo}",
                profissional_nome=profissional,
                profissional_registro=f"{sigla}-{random.randint(1000, 9999)}",
                profissional_especialidade=especialidade,
                data_emissao=emissao,
                data_validade=emissao + timedelta(days=365),
                cid="",
                resumo=resumo,
                arquivo_nome=None, arquivo_tipo=None, arquivo_path=None,
                dados_extraidos={"origem": "seed_demo", "demonstracao": True},
                condicoes=condicoes or None,
                created_by=professor.id,
            ))
            total += 1
    db.flush()
    return total


# ============================================================
# POPULAR UMA ESCOLA (alunos + provas + redacoes + relatorios)
# ============================================================
def popular_escola(db, escola, professor, n_alunos=10, matricula_prefix="DEMO"):
    """Cria alunos, provas com resultados, redacoes e relatorios para UMA escola.
    Retorna um dict com as contagens."""
    # ---------- ALUNOS ----------
    alunos = []
    nomes = random.sample(NOMES, k=min(n_alunos, len(NOMES)))
    for i, nome in enumerate(nomes, start=1):
        serie = random.choice(SERIES)
        idade_anos = 6 + int(serie[0])
        diag = random.choice(DIAGNOSTICOS_POOL)
        aluno = Student(
            escola_id=escola.id,
            name=f"{PREFIXO} {nome}",
            grade_level=serie,
            turma=random.choice(TURMAS),
            matricula=f"{matricula_prefix}{i:04d}",
            birth_date=date.today() - timedelta(days=idade_anos * 365),
            diagnosis=diag or None,
            profile_data={"learning_style": random.choice(["visual", "auditivo", "cinestésico"]),
                          "support_level": random.choice(["baixo", "médio", "alto"]),
                          "interests": random.choice(INTERESSES_POOL)},
            notes="Aluno fictício gerado para demonstração.",
            created_by_user_id=professor.id,
            is_active=True,
        )
        db.add(aluno)
        alunos.append(aluno)
    db.flush()

    # ---------- PROVAS ----------
    for materia in MATERIAS:
        banco = QUESTOES_BANCO[materia]
        prova = Prova(
            titulo=f"{PREFIXO} Avaliação de {materia}",
            descricao=f"Prova de demonstração de {materia}.",
            conteudo_prompt=f"Gerar questões de {materia} para ensino fundamental.",
            materia=materia, serie_nivel="Ensino Fundamental",
            quantidade_questoes=len(banco),
            tipo_questao=TipoQuestao.MULTIPLA_ESCOLHA,
            dificuldade=DificuldadeQuestao.MEDIO,
            tempo_limite_minutos=40, pontuacao_total=10.0, nota_minima_aprovacao=6.0,
            status=StatusProva.ATIVA, criado_por_id=professor.id,
        )
        db.add(prova)
        db.flush()

        questoes = []
        pts = round(10.0 / len(banco), 2)
        for n, (enunciado, opcoes, correta) in enumerate(banco, start=1):
            q = QuestaoGerada(
                prova_id=prova.id, numero=n, enunciado=enunciado,
                tipo=TipoQuestao.MULTIPLA_ESCOLHA, dificuldade=DificuldadeQuestao.MEDIO,
                opcoes=opcoes, resposta_correta=correta, pontuacao=pts,
                explicacao=f"A resposta correta é {correta}.", tags=[materia.lower()],
            )
            db.add(q)
            questoes.append(q)
        db.flush()

        k = min(6, len(alunos))
        for aluno in random.sample(alunos, k=k):
            acertos = 0
            pa = ProvaAluno(
                prova_id=prova.id, aluno_id=aluno.id,
                status=StatusProvaAluno.CORRIGIDA,
                data_atribuicao=agora() - timedelta(days=random.randint(8, 30)),
                data_inicio=agora() - timedelta(days=random.randint(3, 7)),
                data_conclusao=agora() - timedelta(days=random.randint(1, 3)),
                data_correcao=agora() - timedelta(days=random.randint(0, 2)),
                pontuacao_maxima=10.0, tempo_gasto_minutos=random.randint(15, 38),
            )
            db.add(pa)
            db.flush()
            for q in questoes:
                correta = random.random() < random.uniform(0.55, 0.92)
                if correta:
                    acertos += 1
                resp = q.resposta_correta if correta else random.choice(
                    [o for o in q.opcoes if o != q.resposta_correta])
                db.add(RespostaAluno(
                    prova_aluno_id=pa.id, questao_id=q.id,
                    resposta_aluno=resp, esta_correta=correta,
                    pontuacao_obtida=q.pontuacao if correta else 0.0,
                    pontuacao_maxima=q.pontuacao,
                    tempo_resposta_segundos=random.randint(20, 120),
                ))
            nota = round(10.0 * acertos / len(questoes), 1)
            pa.pontuacao_obtida = round(nota, 2)
            pa.nota_final = nota
            pa.aprovado = nota >= 6.0
            pa.feedback_ia = ("Ótimo desempenho! Continue assim." if nota >= 8 else
                              "Bom resultado, com pontos a reforçar." if nota >= 6 else
                              "Vamos revisar os conteúdos com materiais adaptados.")
        db.flush()

    # ---------- REDACOES ----------
    for titulo, area in TEMAS_REDACAO:
        tema = TemaRedacao(
            titulo=f"{PREFIXO} {titulo}", tema=titulo,
            proposta=f"Redija um texto dissertativo-argumentativo sobre: {titulo}.",
            area_tematica=area, nivel_dificuldade="medio", ativo=True,
            criado_por_id=professor.id,
        )
        db.add(tema)
        db.flush()
        k = min(5, len(alunos))
        for aluno in random.sample(alunos, k=k):
            notas = {c: random.choice([120, 140, 160, 180, 200]) for c in range(1, 6)}
            final = sum(notas.values())
            db.add(RedacaoAluno(
                tema_id=tema.id, aluno_id=aluno.id,
                titulo_redacao=f"{PREFIXO} Reflexões sobre o tema",
                texto="Texto de demonstração da redação do aluno. " * 25,
                quantidade_linhas=random.randint(22, 30),
                quantidade_palavras=random.randint(220, 320),
                status=StatusRedacao.CORRIGIDA,
                submetido_em=agora() - timedelta(days=random.randint(3, 15)),
                corrigido_em=agora() - timedelta(days=random.randint(0, 2)),
                nota_competencia_1=notas[1], feedback_competencia_1=FEEDBACK_COMP[1],
                nota_competencia_2=notas[2], feedback_competencia_2=FEEDBACK_COMP[2],
                nota_competencia_3=notas[3], feedback_competencia_3=FEEDBACK_COMP[3],
                nota_competencia_4=notas[4], feedback_competencia_4=FEEDBACK_COMP[4],
                nota_competencia_5=notas[5], feedback_competencia_5=FEEDBACK_COMP[5],
                nota_final=final,
                feedback_geral=("Redação muito boa, próxima da nota máxima!" if final >= 800
                                else "Redação consistente, com espaço para evoluir na argumentação."),
                pontos_fortes=["Boa estrutura", "Repertório pertinente"],
                pontos_melhoria=["Detalhar proposta de intervenção"],
                sugestoes=["Ler editoriais sobre o tema", "Praticar conectivos"],
            ))
        db.flush()

    # ---------- RELATORIOS ----------
    n_rel = criar_relatorios(db, alunos, professor)

    return {"alunos": len(alunos), "provas": len(MATERIAS),
            "temas": len(TEMAS_REDACAO), "relatorios": n_rel}


# ============================================================
# POPULAR (escola principal + 20 escolas SEDUC)
# ============================================================
def popular(db, com_seduc=True):
    if db.query(Escola).filter(Escola.email == ESCOLA_EMAIL).first():
        print("Escola demo JA existe. Use --reset para recriar ou --limpar para remover.")
        return

    # ---------- ESCOLA PRINCIPAL (login demo) ----------
    print("Criando escola principal demo...")
    escola = Escola(
        nome=f"{PREFIXO} Escola Modelo Inclusiva",
        nome_fantasia=f"{PREFIXO} Escola Modelo",
        tipo="ESCOLA", segmento="Educação Especial / AEE",
        email=ESCOLA_EMAIL, cidade="Belém", estado="PA", ativa=True,
    )
    db.add(escola)
    db.flush()
    db.add(ConfiguracaoEscola(escola_id=escola.id))

    professor = User(
        escola_id=escola.id, name=f"{PREFIXO} Prof. Demonstração",
        email=USUARIO_EMAIL, hashed_password=get_password_hash(USUARIO_SENHA),
        role=UserRole.ADMIN, is_active=True,
    )
    db.add(professor)
    db.flush()

    print("  Populando escola principal (alunos, provas, redações, relatórios)...")
    res_principal = popular_escola(db, escola, professor, n_alunos=10, matricula_prefix="DEMO")
    db.commit()
    print(f"  OK: {res_principal}")

    totais = dict(res_principal)
    escolas_criadas = 1

    # ---------- 20 ESCOLAS SEDUC ----------
    if com_seduc:
        senha_hash = get_password_hash(USUARIO_SENHA)  # mesma senha demo123 para todas
        for idx, (nome_escola, cidade) in enumerate(ESCOLAS_SEDUC, start=1):
            print(f"[{idx}/{len(ESCOLAS_SEDUC)}] Criando {PREFIXO} {nome_escola} ({cidade})...")
            esc = Escola(
                nome=f"{PREFIXO} {nome_escola}",
                nome_fantasia=f"{PREFIXO} {nome_escola}",
                tipo="ESCOLA",
                segmento="Rede Pública Estadual - SEDUC/PA",
                email=f"escola{idx:02d}{DEMO_DOMINIO}",
                cidade=cidade, estado="PA", ativa=True,
            )
            db.add(esc)
            db.flush()
            db.add(ConfiguracaoEscola(escola_id=esc.id))

            prof = User(
                escola_id=esc.id,
                name=f"{PREFIXO} Coordenação {nome_escola}",
                email=f"coord{idx:02d}{DEMO_DOMINIO}",
                hashed_password=senha_hash,
                role=UserRole.ADMIN, is_active=True,
            )
            db.add(prof)
            db.flush()

            res = popular_escola(db, esc, prof, n_alunos=10,
                                 matricula_prefix=f"S{idx:02d}")
            db.commit()  # commit por escola (progresso + libera o banco)
            for kk in totais:
                totais[kk] += res[kk]
            escolas_criadas += 1
            print(f"      OK: {res}")

    print("\n" + "=" * 56)
    print(" SEED DE DEMONSTRACAO CONCLUIDO COM SUCESSO!")
    print("=" * 56)
    print(f"  Escolas criadas:   {escolas_criadas}")
    print(f"  Total de alunos:   {totais['alunos']}")
    print(f"  Total de provas:   {totais['provas']}")
    print(f"  Total de temas:    {totais['temas']}")
    print(f"  Total relatórios:  {totais['relatorios']}")
    print("-" * 56)
    print("  LOGIN PARA A APRESENTACAO (escola principal):")
    print(f"    Email: {USUARIO_EMAIL}")
    print(f"    Senha: {USUARIO_SENHA}")
    print("-" * 56)
    print("  As 20 escolas SEDUC têm login coordNN@demo.adaptai.com.br")
    print("  (NN = 01..20), todas com senha demo123.")
    print("=" * 56)
    print("  Para remover tudo depois: python seed_demo.py --limpar")
    print("=" * 56)


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    db = SessionLocal()
    try:
        if modo == "--limpar":
            limpar(db)
        elif modo == "--reset":
            limpar(db)
            popular(db, com_seduc=True)
        elif modo == "--simples":
            popular(db, com_seduc=False)
        else:
            popular(db, com_seduc=True)
    except Exception as e:
        db.rollback()
        print(f"\nERRO: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
