"""
Protege a regra de consentimento LGPD do Portal da Família:
`_tem_consentimento_vigente` só é True quando existe um consentimento do tipo
pedido e ainda não revogado. Roda em sqlite (create_all), sem IA nem rede.
"""
from datetime import datetime, timezone

import app.models  # noqa: F401 — registra todos os models
from app.database import Base, engine, SessionLocal


def _setup():
    Base.metadata.create_all(bind=engine)


def test_gate_consentimento_tratamento_dados():
    _setup()
    from app.models.clinica_core import Paciente, StatusPaciente, Consentimento, TipoConsentimento
    from app.api.routes.familia import _tem_consentimento_vigente

    db = SessionLocal()
    pid = cid = None
    try:
        p = Paciente(escola_id=1, nome="Consent Teste", status=StatusPaciente.EM_AVALIACAO)
        db.add(p)
        db.commit()
        db.refresh(p)
        pid = p.id

        # sem consentimento -> bloqueado
        assert _tem_consentimento_vigente(db, pid, TipoConsentimento.TRATAMENTO_DADOS) is False

        # com consentimento vigente -> liberado
        c = Consentimento(
            escola_id=1, paciente_id=pid,
            tipo=TipoConsentimento.TRATAMENTO_DADOS,
            versao_texto="v1", concedido_por="Responsavel",
            concedido_em=datetime.now(timezone.utc),
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        cid = c.id
        assert _tem_consentimento_vigente(db, pid, TipoConsentimento.TRATAMENTO_DADOS) is True

        # outro tipo continua bloqueado
        assert _tem_consentimento_vigente(db, pid, TipoConsentimento.USO_IMAGEM) is False

        # revogado -> volta a bloquear
        c.revogado_em = datetime.now(timezone.utc)
        db.commit()
        assert _tem_consentimento_vigente(db, pid, TipoConsentimento.TRATAMENTO_DADOS) is False
    finally:
        if cid is not None:
            db.query(Consentimento).filter(Consentimento.id == cid).delete()
        if pid is not None:
            db.query(Paciente).filter(Paciente.id == pid).delete()
        db.commit()
        db.close()
