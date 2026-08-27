"""
🏥 AdaptAI - Rotas de mensagens equipe<->familia (lado equipe) - vertical CLINICA.

Canal de recados por paciente. A equipe posta aqui (gated + guard de acesso);
a familia posta/le pelo portal (ver familia.py).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_mensagens import MensagemFamilia, OrigemMensagem

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Mensagens)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)


def _dict(m: MensagemFamilia) -> dict:
    return {
        "id": m.id, "origem": m.origem.value if hasattr(m.origem, "value") else m.origem,
        "texto": m.texto, "autor_id": m.autor_id,
        "criado_em": str(m.criado_em) if m.criado_em else None,
    }


class MensagemCriar(BaseModel):
    texto: str = Field(..., min_length=1)


@router.get("/pacientes/{paciente_id}/mensagens")
def listar_mensagens(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    msgs = (db.query(MensagemFamilia)
            .filter(MensagemFamilia.paciente_id == p.id)
            .order_by(MensagemFamilia.id).limit(200).all())
    return [_dict(m) for m in msgs]


@router.post("/pacientes/{paciente_id}/mensagens", status_code=status.HTTP_201_CREATED)
def enviar_mensagem(
    paciente_id: int,
    body: MensagemCriar,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    m = MensagemFamilia(
        escola_id=p.escola_id, paciente_id=p.id, origem=OrigemMensagem.EQUIPE,
        autor_id=current_user.id, texto=body.texto,
        criado_em=datetime.now(timezone.utc),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _dict(m)
