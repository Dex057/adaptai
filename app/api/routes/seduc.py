"""
============================================================
 AdaptAI - Painel SEDUC (visao de REDE / agregado de escolas)
============================================================
Endpoints de AGREGACAO que somam dados de varias escolas para
uma visao consolidada da rede (caso de uso: SEDUC enxergar todas
as escolas estaduais).

IMPORTANTE (versao 1 / demonstracao):
- Esta versao agrega escolas pelo SEGMENTO "Rede Publica Estadual - SEDUC/PA".
  E um filtro EXPLICITO e propositadamente conservador: so entram escolas
  marcadas como dessa rede. Assim NAO vaza dados de escolas privadas/outras
  redes que porventura existam no mesmo banco.
- Esta NAO e ainda a hierarquia multi-rede definitiva (tabela de secretarias +
  vinculo escola->rede + papel SEDUC_ADMIN). Esse e o proximo passo de
  arquitetura. Ver TODO no fim do arquivo.
- Por seguranca, exige usuario ADMIN/SUPER_ADMIN autenticado.
============================================================
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.escola import Escola
from app.models.student import Student
from app.models.prova import ProvaAluno
from app.models.redacao import RedacaoAluno
from app.models.relatorio import Relatorio
from app.api.dependencies import require_admin

router = APIRouter(prefix="/seduc", tags=["Painel SEDUC"])

# Segmento que identifica as escolas da rede estadual para agregacao.
SEGMENTO_SEDUC = "Rede Pública Estadual - SEDUC/PA"


def _escolas_da_rede(db: Session):
    """Retorna as escolas que pertencem a rede SEDUC (pelo segmento)."""
    return db.query(Escola).filter(
        Escola.segmento == SEGMENTO_SEDUC,
        Escola.ativa == True,  # noqa: E712
    ).all()


def _classificar_diagnostico(diagnosis) -> list:
    """Extrai rotulos de condicao de um diagnosis (JSON) de aluno.
    Retorna lista de chaves presentes: tea, tdah, dislexia. Vazio se nenhum."""
    if not diagnosis or not isinstance(diagnosis, dict):
        return []
    labels = []
    if diagnosis.get("tea"):
        labels.append("tea")
    if diagnosis.get("tdah"):
        labels.append("tdah")
    if diagnosis.get("dislexia"):
        labels.append("dislexia")
    return labels


@router.get("/visao-geral")
def visao_geral_rede(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Indicadores AGREGADOS da rede SEDUC: totais e distribuicao por municipio.

    Retorna:
    - totais: escolas, alunos, provas_corrigidas, redacoes, relatorios
    - diagnosticos: contagem por condicao (tea/tdah/dislexia/sem_diagnostico)
    - por_municipio: lista com {municipio, escolas, alunos, media_provas,
      tea, tdah, dislexia} para alimentar o MAPA do Para.
    """
    escolas = _escolas_da_rede(db)
    escola_ids = [e.id for e in escolas]

    if not escola_ids:
        return {
            "segmento": SEGMENTO_SEDUC,
            "totais": {"escolas": 0, "alunos": 0, "provas_corrigidas": 0,
                       "redacoes": 0, "relatorios": 0},
            "diagnosticos": {"tea": 0, "tdah": 0, "dislexia": 0, "sem_diagnostico": 0},
            "por_municipio": [],
        }

    # ---- Alunos da rede (carrega 1x e agrega em memoria) ----
    alunos = db.query(Student).filter(
        Student.escola_id.in_(escola_ids),
        Student.is_active == True,  # noqa: E712
    ).all()

    aluno_ids = [a.id for a in alunos]
    escola_por_aluno = {a.id: a.escola_id for a in alunos}

    # ---- Mapa escola -> municipio ----
    municipio_por_escola = {e.id: (e.cidade or "Nao informado") for e in escolas}

    # ---- Diagnosticos agregados ----
    diag_count = {"tea": 0, "tdah": 0, "dislexia": 0, "sem_diagnostico": 0}
    # estrutura por municipio
    muni = {}
    for e in escolas:
        m = municipio_por_escola[e.id]
        muni.setdefault(m, {"municipio": m, "escolas": 0, "alunos": 0,
                            "tea": 0, "tdah": 0, "dislexia": 0,
                            "soma_notas": 0.0, "qtd_notas": 0})
        muni[m]["escolas"] += 1

    for a in alunos:
        m = municipio_por_escola.get(a.escola_id, "Nao informado")
        if m not in muni:
            muni[m] = {"municipio": m, "escolas": 0, "alunos": 0,
                       "tea": 0, "tdah": 0, "dislexia": 0,
                       "soma_notas": 0.0, "qtd_notas": 0}
        muni[m]["alunos"] += 1
        labels = _classificar_diagnostico(a.diagnosis)
        if not labels:
            diag_count["sem_diagnostico"] += 1
        for lb in labels:
            diag_count[lb] += 1
            muni[m][lb] += 1

    # ---- Provas corrigidas (contagem + media de nota por municipio) ----
    provas_corrigidas = 0
    if aluno_ids:
        pa_rows = db.query(
            ProvaAluno.aluno_id, ProvaAluno.nota_final
        ).filter(
            ProvaAluno.aluno_id.in_(aluno_ids),
            ProvaAluno.nota_final.isnot(None),
        ).all()
        provas_corrigidas = len(pa_rows)
        for aluno_id, nota in pa_rows:
            esc_id = escola_por_aluno.get(aluno_id)
            m = municipio_por_escola.get(esc_id, "Nao informado")
            if m in muni and nota is not None:
                muni[m]["soma_notas"] += float(nota)
                muni[m]["qtd_notas"] += 1

    # ---- Redacoes ----
    redacoes = 0
    if aluno_ids:
        redacoes = db.query(func.count(RedacaoAluno.id)).filter(
            RedacaoAluno.aluno_id.in_(aluno_ids)
        ).scalar() or 0

    # ---- Relatorios ----
    relatorios = 0
    if aluno_ids:
        relatorios = db.query(func.count(Relatorio.id)).filter(
            Relatorio.student_id.in_(aluno_ids)
        ).scalar() or 0

    # ---- Monta lista por municipio com media calculada ----
    por_municipio = []
    for m, d in muni.items():
        media = round(d["soma_notas"] / d["qtd_notas"], 1) if d["qtd_notas"] else None
        por_municipio.append({
            "municipio": d["municipio"],
            "escolas": d["escolas"],
            "alunos": d["alunos"],
            "tea": d["tea"],
            "tdah": d["tdah"],
            "dislexia": d["dislexia"],
            "media_provas": media,
        })
    por_municipio.sort(key=lambda x: x["alunos"], reverse=True)

    return {
        "segmento": SEGMENTO_SEDUC,
        "totais": {
            "escolas": len(escolas),
            "alunos": len(alunos),
            "provas_corrigidas": provas_corrigidas,
            "redacoes": int(redacoes),
            "relatorios": int(relatorios),
        },
        "diagnosticos": diag_count,
        "por_municipio": por_municipio,
    }


@router.get("/escolas")
def listar_escolas_rede(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Lista as escolas da rede com indicadores por escola (para tabela/ranking).
    Retorna: [{id, nome, municipio, alunos, media_provas, tea, tdah, dislexia}]
    """
    escolas = _escolas_da_rede(db)
    if not escolas:
        return {"escolas": []}

    escola_ids = [e.id for e in escolas]

    # alunos por escola + diagnosticos
    alunos = db.query(Student).filter(
        Student.escola_id.in_(escola_ids),
        Student.is_active == True,  # noqa: E712
    ).all()

    por_escola = {e.id: {
        "id": e.id, "nome": e.nome, "municipio": e.cidade or "Nao informado",
        "alunos": 0, "tea": 0, "tdah": 0, "dislexia": 0,
        "soma_notas": 0.0, "qtd_notas": 0,
    } for e in escolas}

    aluno_para_escola = {}
    for a in alunos:
        aluno_para_escola[a.id] = a.escola_id
        bucket = por_escola.get(a.escola_id)
        if not bucket:
            continue
        bucket["alunos"] += 1
        for lb in _classificar_diagnostico(a.diagnosis):
            bucket[lb] += 1

    aluno_ids = list(aluno_para_escola.keys())
    if aluno_ids:
        pa_rows = db.query(
            ProvaAluno.aluno_id, ProvaAluno.nota_final
        ).filter(
            ProvaAluno.aluno_id.in_(aluno_ids),
            ProvaAluno.nota_final.isnot(None),
        ).all()
        for aluno_id, nota in pa_rows:
            esc_id = aluno_para_escola.get(aluno_id)
            bucket = por_escola.get(esc_id)
            if bucket and nota is not None:
                bucket["soma_notas"] += float(nota)
                bucket["qtd_notas"] += 1

    saida = []
    for b in por_escola.values():
        media = round(b["soma_notas"] / b["qtd_notas"], 1) if b["qtd_notas"] else None
        saida.append({
            "id": b["id"], "nome": b["nome"], "municipio": b["municipio"],
            "alunos": b["alunos"], "tea": b["tea"], "tdah": b["tdah"],
            "dislexia": b["dislexia"], "media_provas": media,
        })
    saida.sort(key=lambda x: x["alunos"], reverse=True)
    return {"escolas": saida}


# ============================================================
# TODO (arquitetura definitiva, pos-demonstracao):
# - Criar tabela `redes` (ou `secretarias`) e campo Escola.rede_id (FK).
# - Criar papel UserRole.SEDUC_ADMIN com vinculo a uma rede.
# - Trocar o filtro por SEGMENTO_SEDUC por filtro por rede_id do usuario.
# - Assim a SEDUC ve SO as escolas da sua rede, e o sistema suporta
#   multiplas redes/secretarias + escolas privadas no mesmo banco.
# ============================================================
