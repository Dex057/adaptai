"""
🏥 AdaptAI - Rotas de anexos do prontuario (vertical CLINICA).

Upload/list/download/delete de documentos do paciente (laudos, exames, fotos).
Bytes no volume (ANEXOS_DIR); download por endpoint AUTENTICADO com IDOR +
auditoria (dado de saude, LGPD). Gate CLINICA.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.core.entitlements import requer_modulo, Modulo
from app.services import acesso_clinico
from app.models.clinica_core import AcaoAuditoria, Profissional
from app.models.clinica_anexo import AnexoProntuario

router = APIRouter(
    prefix="/clinica",
    tags=["🏥 Clínica (Anexos)"],
    dependencies=[Depends(requer_modulo(Modulo.CLINICA))],
)

# Volume do Railway: ANEXOS_DIR=/data/anexos. Fallback local (dev): backend/storage/anexos.
ANEXOS_DIR = Path(os.getenv("ANEXOS_DIR") or (Path(__file__).resolve().parents[3] / "storage" / "anexos"))
ANEXOS_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MIME_PERMITIDOS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def _agora():
    return datetime.now(timezone.utc)


def _dict(a: AnexoProntuario) -> dict:
    return {
        "id": a.id,
        "paciente_id": a.paciente_id,
        "nome_original": a.nome_original,
        "mime": a.mime,
        "tamanho_bytes": a.tamanho_bytes,
        "categoria": a.categoria,
        "descricao": a.descricao,
        "criado_em": a.criado_em.isoformat() if a.criado_em else None,
    }


@router.post("/pacientes/{paciente_id}/anexos", status_code=status.HTTP_201_CREATED)
async def enviar_anexo(
    paciente_id: int,
    file: UploadFile = File(...),
    categoria: Optional[str] = Form(None),
    descricao: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(
        db, paciente_id, current_user, AcaoAuditoria.CRIAR, "anexo", None
    )
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo maior que 20 MB.")
    mime = (file.content_type or "").split(";")[0].strip().lower()
    ext = MIME_PERMITIDOS.get(mime)
    if not ext:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Tipo nao permitido. Aceitos: PDF, imagem (PNG/JPG/WEBP/GIF), DOC/DOCX, TXT.",
        )
    subdir = ANEXOS_DIR / str(p.escola_id)
    subdir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    (subdir / stored).write_bytes(conteudo)
    a = AnexoProntuario(
        escola_id=p.escola_id,
        paciente_id=p.id,
        nome_original=(file.filename or stored)[:255],
        mime=mime,
        tamanho_bytes=len(conteudo),
        caminho=f"{p.escola_id}/{stored}",
        categoria=(categoria or None),
        descricao=(descricao or None),
        enviado_por_id=current_user.id,
        criado_em=_agora(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _dict(a)


@router.get("/pacientes/{paciente_id}/anexos")
def listar_anexos(
    paciente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = acesso_clinico.verificar_acesso_paciente(db, paciente_id, current_user)
    itens = (
        db.query(AnexoProntuario)
        .filter(AnexoProntuario.paciente_id == p.id)
        .order_by(AnexoProntuario.criado_em.desc())
        .all()
    )
    return [_dict(a) for a in itens]


@router.get("/anexos/{anexo_id}/arquivo")
def baixar_anexo(
    anexo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = db.query(AnexoProntuario).filter(AnexoProntuario.id == anexo_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo nao encontrado.")
    acesso_clinico.verificar_acesso_paciente(
        db, a.paciente_id, current_user, AcaoAuditoria.VISUALIZAR, "anexo", a.id
    )
    caminho = ANEXOS_DIR / a.caminho
    if not caminho.exists():
        raise HTTPException(status.HTTP_410_GONE, "Arquivo indisponivel no storage.")
    return FileResponse(str(caminho), media_type=a.mime or "application/octet-stream", filename=a.nome_original)


@router.delete("/anexos/{anexo_id}")
def excluir_anexo(
    anexo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = db.query(AnexoProntuario).filter(AnexoProntuario.id == anexo_id).first()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo nao encontrado.")
    acesso_clinico.verificar_acesso_paciente(
        db, a.paciente_id, current_user, AcaoAuditoria.EDITAR, "anexo", a.id
    )
    try:
        (ANEXOS_DIR / a.caminho).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(a)
    db.commit()
    return {"ok": True, "id": anexo_id}
