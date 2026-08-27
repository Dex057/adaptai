"""
Smoke test do vertical CLINICA: todos os models (inclusive os clínicos)
carregam, o metadata contém as tabelas esperadas e o create_all + um INSERT
básico funcionam em sqlite. Pega erros de mapper / colisão de tabela.
"""
import app.models  # noqa: F401 — dispara o registro de TODOS os models
from app.database import Base, engine, SessionLocal


TABELAS_CLINICAS = {
    "escola_modulos", "profissionais", "pacientes", "equipe_caso",
    "consentimentos", "vinculo_aluno_paciente", "auditoria_acesso",
    "planos_terapeuticos", "objetivos_terapeuticos", "sessoes",
    "registros_tentativa", "evolucoes", "pranchas", "prancha_itens",
    "agendamentos", "tarefas_casa", "tarefa_casa_check", "mensagens_familia",
    "convenios", "faturamentos",
}


def test_metadata_contem_tabelas_clinicas():
    tabelas = set(Base.metadata.tables.keys())
    faltando = TABELAS_CLINICAS - tabelas
    assert not faltando, f"tabelas clínicas ausentes no metadata: {faltando}"


def test_create_all_e_insert_paciente():
    Base.metadata.create_all(bind=engine)
    from app.models.clinica_core import Paciente, StatusPaciente

    db = SessionLocal()
    pid = None
    try:
        p = Paciente(escola_id=1, nome="Paciente Teste", status=StatusPaciente.EM_AVALIACAO)
        db.add(p)
        db.commit()
        db.refresh(p)
        pid = p.id
        assert pid is not None
        assert p.status == StatusPaciente.EM_AVALIACAO
    finally:
        if pid is not None:
            db.query(Paciente).filter(Paciente.id == pid).delete()
            db.commit()
        db.close()
