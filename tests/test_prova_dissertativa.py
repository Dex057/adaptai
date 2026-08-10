"""
TC-152 - prova com questao dissertativa nao pode fechar nota 0 sozinha.

O que estava quebrado: `POST /student/provas/{id}/responder` grava
`esta_correta = None` e `pontuacao_obtida = 0` para questao sem gabarito (correto -
nao ha como corrigir automaticamente), mas `/finalizar` dividia a pontuacao obtida
por `prova.pontuacao_total`, que INCLUI o peso dessas questoes. Resultado: prova
100% discursiva fechava 0/10 e reprovava o aluno na hora, e nada no backend
corrigia depois - nao existia endpoint de correcao manual.

Aqui travamos as duas metades da correcao:
1. o denominador passa a ser so o que ja foi corrigido (nota parcial, nunca 0
   inventado), e a prova fica CONCLUIDA em vez de CORRIGIDA;
2. `POST /provas/aluno/{id}/corrigir-questao` fecha a pendencia e recalcula.

Estrategia identica a tests/test_student_materiais_adaptados.py: sqlite em
memoria, app minimo com os routers sob teste e override de get_db.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
import app.models  # noqa: F401 - registra todos os models no metadata
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.prova import (
    Prova, QuestaoGerada, ProvaAluno, RespostaAluno,
    StatusProva, StatusProvaAluno, TipoQuestao, DificuldadeQuestao,
)
from app.core.security import create_access_token
from app.api.routes import student_provas


@pytest.fixture(scope="function")
def db_engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(eng)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Schema nao montavel em sqlite: {e}")
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture(scope="function")
def TestSession(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


def _montar(db, tipos):
    """
    Cria prova + aluno + prova_aluno EM_ANDAMENTO com uma questao por tipo em
    `tipos`, cada uma valendo 5 pontos. Dissertativa nasce sem resposta_correta -
    e justamente isso que dispara o caminho do TC-152.
    """
    prof = User(name="Prof", email="prof_diss@test.com", hashed_password="x",
                role=UserRole.TEACHER, is_active=True)
    db.add(prof)
    db.commit()
    db.refresh(prof)

    aluno = Student(name="Aluno", grade_level="9o ano", email="aluno_diss@test.com",
                    created_by_user_id=prof.id, is_active=True)
    db.add(aluno)
    db.commit()
    db.refresh(aluno)

    prova = Prova(
        titulo="Prova teste", conteudo_prompt="x", materia="Portugues",
        quantidade_questoes=len(tipos), tipo_questao=tipos[0],
        pontuacao_total=5.0 * len(tipos), nota_minima_aprovacao=6.0,
        status=StatusProva.ATIVA, criado_por_id=prof.id,
    )
    db.add(prova)
    db.commit()
    db.refresh(prova)

    questoes = []
    for i, tipo in enumerate(tipos, start=1):
        q = QuestaoGerada(
            prova_id=prova.id, numero=i, enunciado=f"Questao {i}", tipo=tipo,
            dificuldade=DificuldadeQuestao.MEDIO, pontuacao=5.0,
            opcoes=None if tipo == TipoQuestao.DISSERTATIVA else ["A) um", "B) dois"],
            resposta_correta=None if tipo == TipoQuestao.DISSERTATIVA else "A",
        )
        db.add(q)
        questoes.append(q)
    db.commit()
    for q in questoes:
        db.refresh(q)

    prova_aluno = ProvaAluno(
        prova_id=prova.id, aluno_id=aluno.id,
        status=StatusProvaAluno.EM_ANDAMENTO, pontuacao_maxima=prova.pontuacao_total,
    )
    db.add(prova_aluno)
    db.commit()
    db.refresh(prova_aluno)

    return {
        "prova_aluno_id": prova_aluno.id,
        "questao_ids": [q.id for q in questoes],
        "token": create_access_token({"sub": f"student:{aluno.email}"}),
    }


@pytest.fixture(scope="function", autouse=True)
def sem_pos_prova(monkeypatch):
    """
    `processar_pos_prova` abre uma SessionLocal propria (banco real) e chama IA.
    Nada disso pertence a este teste - o que importa aqui e SE ela e agendada,
    coisa que os testes verificam pelo campo `processando_ia` da resposta.
    """
    monkeypatch.setattr(student_provas, "processar_pos_prova", lambda *a, **k: None)


@pytest.fixture(scope="function")
def client(TestSession):
    app = FastAPI()
    app.include_router(student_provas.router)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestProvaSoDissertativa:
    def test_nao_fecha_com_nota_zero(self, client, TestSession):
        """O bug do TC-152: prova 100% discursiva reprovava o aluno na hora."""
        db = TestSession()
        try:
            ctx = _montar(db, [TipoQuestao.DISSERTATIVA, TipoQuestao.DISSERTATIVA])
        finally:
            db.close()

        for qid in ctx["questao_ids"]:
            r = client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                            json={"questao_id": qid, "resposta": "minha resposta"},
                            headers=auth(ctx["token"]))
            assert r.status_code == 200

        r = client.post(f"/student/provas/{ctx['prova_aluno_id']}/finalizar",
                        headers=auth(ctx["token"]))
        assert r.status_code == 200
        body = r.json()

        # Sem nota inventada: None significa "ainda nao corrigida", 0 significaria
        # "o aluno errou tudo".
        assert body["nota_final"] is None
        assert body["aprovado"] is None
        assert body["questoes_aguardando_correcao"] == 2
        assert body["nota_parcial"] is True
        # Analise de IA nao roda em cima de prova nao corrigida.
        assert body["processando_ia"] is False

    def test_fica_concluida_e_nao_corrigida(self, client, TestSession):
        db = TestSession()
        try:
            ctx = _montar(db, [TipoQuestao.DISSERTATIVA])
        finally:
            db.close()

        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][0], "resposta": "resposta"},
                    headers=auth(ctx["token"]))
        client.post(f"/student/provas/{ctx['prova_aluno_id']}/finalizar",
                    headers=auth(ctx["token"]))

        db = TestSession()
        try:
            pa = db.query(ProvaAluno).filter(ProvaAluno.id == ctx["prova_aluno_id"]).first()
            assert pa.status == StatusProvaAluno.CONCLUIDA
            assert pa.data_correcao is None
            assert pa.nota_final is None
        finally:
            db.close()


class TestProvaMista:
    def test_nota_parcial_considera_so_o_que_foi_corrigido(self, client, TestSession):
        """
        1 multipla escolha (acertada, 5 pts) + 1 dissertativa pendente.
        Antes: 5 / 10 = nota 5,0 (reprovado). Agora: 5 / 5 = 10,0 parcial.
        """
        db = TestSession()
        try:
            ctx = _montar(db, [TipoQuestao.MULTIPLA_ESCOLHA, TipoQuestao.DISSERTATIVA])
        finally:
            db.close()

        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][0], "resposta": "A"},
                    headers=auth(ctx["token"]))
        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][1], "resposta": "texto"},
                    headers=auth(ctx["token"]))

        body = client.post(f"/student/provas/{ctx['prova_aluno_id']}/finalizar",
                           headers=auth(ctx["token"])).json()

        assert body["nota_final"] == 10.0
        assert body["questoes_aguardando_correcao"] == 1
        assert body["questoes_corrigidas"] == 1
        assert body["nota_parcial"] is True
        # Aprovacao com pendencia so pode ser afirmada, nunca negada.
        assert body["aprovado"] is True

    def test_percentual_nao_conta_pendente_como_erro(self, client, TestSession):
        db = TestSession()
        try:
            ctx = _montar(db, [TipoQuestao.MULTIPLA_ESCOLHA, TipoQuestao.DISSERTATIVA])
        finally:
            db.close()

        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][0], "resposta": "A"},
                    headers=auth(ctx["token"]))
        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][1], "resposta": "texto"},
                    headers=auth(ctx["token"]))

        body = client.post(f"/student/provas/{ctx['prova_aluno_id']}/finalizar",
                           headers=auth(ctx["token"])).json()
        # 1 acerto em 1 questao corrigida = 100%, nao 50%.
        assert body["percentual"] == 100.0


class TestProvaSemDissertativa:
    def test_comportamento_antigo_preservado(self, client, TestSession):
        """Prova so de multipla escolha nao pode ter mudado de comportamento."""
        db = TestSession()
        try:
            ctx = _montar(db, [TipoQuestao.MULTIPLA_ESCOLHA, TipoQuestao.MULTIPLA_ESCOLHA])
        finally:
            db.close()

        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][0], "resposta": "A"},
                    headers=auth(ctx["token"]))
        client.post(f"/student/provas/{ctx['prova_aluno_id']}/responder",
                    json={"questao_id": ctx["questao_ids"][1], "resposta": "B"},
                    headers=auth(ctx["token"]))

        body = client.post(f"/student/provas/{ctx['prova_aluno_id']}/finalizar",
                           headers=auth(ctx["token"])).json()

        assert body["nota_final"] == 5.0  # 5 de 10 pontos
        assert body["aprovado"] is False
        assert body["questoes_aguardando_correcao"] == 0
        assert body["nota_parcial"] is False

        db = TestSession()
        try:
            pa = db.query(ProvaAluno).filter(ProvaAluno.id == ctx["prova_aluno_id"]).first()
            assert pa.status == StatusProvaAluno.CORRIGIDA
            assert pa.data_correcao is not None
        finally:
            db.close()
