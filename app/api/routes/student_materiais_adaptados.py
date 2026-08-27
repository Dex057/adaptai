"""
Rotas de Materiais Adaptados para Estudantes.

TC-027/028/031/032/033/081/088/118/123/124/125 (cluster "material nao chega no aluno"):
o professor gera material pela tela "Criar com IA" (POST /materiais-adaptados/gerar),
que persiste em `materiais_adaptados_gerados` (model MaterialAdaptadoGerado, ligado a
`student_id`). O Portal do Aluno, porem, lia apenas de `materiais`/`materiais_alunos`
(GET /student/materiais/) - duas tabelas que aquele pipeline nunca popula. Resultado:
tudo que o professor gerava ficava invisivel para o aluno.

Este modulo e a ponte que faltava: expoe ao aluno logado exatamente os materiais que
ja existem gravados para ele, sem duplicar dado e sem alterar nenhum contrato
existente (`/student/materiais/` continua igual). A opcao de "copiar" cada
MaterialAdaptadoGerado para Material/MaterialAluno foi descartada por duplicar dado
e exigir backfill dos materiais ja gerados.

TC-033/123/124 (favoritar / marcar como lido / anotar): a primeira versao deste
modulo era so leitura, e esses tres casos continuavam sem efeito - as colunas
existiam apenas em `materiais_alunos`, tabela que este pipeline nunca popula.
A migration 007 trouxe `favorito`, `lido`, `lido_em` e `anotacoes_aluno` para
`materiais_adaptados_gerados`, e os endpoints de escrita abaixo fecham o caso.
Contrato identico ao de `/student/materiais/` (mesmos paths, mesmos nomes de
campo) para o front reaproveitar o componente que ja existe.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.student import Student
from app.models.material_adaptado_gerado import MaterialAdaptadoGerado
from app.api.dependencies import get_current_student

router = APIRouter(
    prefix="/student/materiais-adaptados",
    tags=["Student - Materiais Adaptados"],
)


class FavoritoRequest(BaseModel):
    """Mesmo corpo aceito por POST /student/materiais/{id}/favorito."""
    favorito: bool


class AnotacaoRequest(BaseModel):
    """Mesmo corpo aceito por POST /student/materiais/{id}/anotacoes."""
    anotacoes: str = Field(default="", max_length=20000)


def _buscar_material_do_aluno(
    db: Session, material_id: int, student_id: int
) -> MaterialAdaptadoGerado:
    """
    Carrega o material garantindo que ele pertence ao aluno do token.

    O `student_id` entra no WHERE (nao em um `if` depois da busca): material de
    outro aluno responde 404, nao 403 - nao vaza nem a existencia do registro.
    """
    material = (
        db.query(MaterialAdaptadoGerado)
        .filter(
            MaterialAdaptadoGerado.id == material_id,
            MaterialAdaptadoGerado.student_id == student_id,
        )
        .first()
    )
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado",
        )
    return material


@router.get("/")
async def listar_meus_materiais_adaptados(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Lista os materiais adaptados gerados pelo professor para o aluno logado.

    O filtro por `student_id` do proprio token e a garantia de isolamento: nao ha
    parametro de aluno na assinatura, entao nao existe superficie para IDOR.
    Retorna apenas metadados (sem `resultado_json`, que pode ser grande) - o
    conteudo completo vem no endpoint de detalhe.
    """
    # 2026-08-18: o SELECT era da entidade inteira - trazia `resultado_json`
    # (ate megabytes por linha, com as imagens base64 dos materiais
    # ilustrados) so para montar uma lista de cards. Alem do trafego, o
    # ORDER BY sobre linhas desse tamanho fazia o MySQL responder
    # "1038 Out of sort memory" e o portal do aluno abria vazio. O docstring
    # acima ja dizia "sem resultado_json" - agora o SQL cumpre.
    materiais = (
        db.query(
            MaterialAdaptadoGerado.id,
            MaterialAdaptadoGerado.disciplina,
            MaterialAdaptadoGerado.serie,
            MaterialAdaptadoGerado.conteudo,
            MaterialAdaptadoGerado.tipos_material,
            MaterialAdaptadoGerado.created_at,
            MaterialAdaptadoGerado.favorito,
            MaterialAdaptadoGerado.lido,
            MaterialAdaptadoGerado.anotacoes_aluno,
        )
        .filter(MaterialAdaptadoGerado.student_id == current_student.id)
        .order_by(
            MaterialAdaptadoGerado.created_at.desc(),
            MaterialAdaptadoGerado.id.desc(),
        )
        .all()
    )

    return [
        {
            "id": m.id,
            "disciplina": m.disciplina,
            "serie": m.serie,
            "conteudo": m.conteudo,
            "tipos_material": m.tipos_material or [],
            "created_at": m.created_at.isoformat() if m.created_at else None,
            # TC-033/123/124: o Portal precisa do estado para pintar a estrela e o
            # "ja lido" na propria listagem, sem abrir cada material.
            "favorito": bool(m.favorito),
            "lido": bool(m.lido),
            "tem_anotacoes": bool(m.anotacoes_aluno),
        }
        for m in materiais
    ]


@router.get("/{material_id}")
async def obter_meu_material_adaptado(
    material_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Abre um material adaptado especifico do aluno logado (conteudo completo).

    O `student_id` entra no proprio WHERE: um material de outro aluno responde 404,
    nao 403 - nao vaza nem a existencia do registro.
    """
    material = _buscar_material_do_aluno(db, material_id, current_student.id)

    return {
        "id": material.id,
        "disciplina": material.disciplina,
        "serie": material.serie,
        "conteudo": material.conteudo,
        "tipos_material": material.tipos_material or [],
        # Mesmo nome de chave usado por GET /materiais-adaptados/historico/{id}
        # (visao do professor), para o frontend reaproveitar o mesmo viewer.
        "resultado": material.resultado_json,
        "created_at": material.created_at.isoformat() if material.created_at else None,
        "favorito": bool(material.favorito),
        "lido": bool(material.lido),
        "lido_em": material.lido_em.isoformat() if material.lido_em else None,
        "anotacoes": material.anotacoes_aluno,
    }


@router.post("/{material_id}/favorito")
async def marcar_favorito(
    material_id: int,
    payload: FavoritoRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Marca ou desmarca o material adaptado como favorito (TC-123).

    Idempotente: enviar `favorito: true` duas vezes deixa o mesmo estado.
    """
    material = _buscar_material_do_aluno(db, material_id, current_student.id)

    material.favorito = 1 if payload.favorito else 0
    db.commit()

    return {"success": True, "favorito": bool(material.favorito)}


@router.post("/{material_id}/lido")
async def marcar_lido(
    material_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Marca o material como lido (TC-124).

    `lido_em` guarda a PRIMEIRA leitura e nao e sobrescrito em chamadas
    repetidas - o dado interessante para o professor e quando o aluno abriu,
    nao quando clicou de novo.
    """
    material = _buscar_material_do_aluno(db, material_id, current_student.id)

    if not material.lido:
        material.lido = 1
        material.lido_em = datetime.now(timezone.utc)
        db.commit()

    return {
        "success": True,
        "lido": True,
        "lido_em": material.lido_em.isoformat() if material.lido_em else None,
    }


@router.post("/{material_id}/anotacoes")
async def salvar_anotacoes(
    material_id: int,
    payload: AnotacaoRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Salva as anotacoes do aluno sobre o material adaptado (TC-033).

    Substitui o conteudo anterior (o front manda o texto completo do editor,
    mesmo contrato de POST /student/materiais/{id}/anotacoes).
    """
    material = _buscar_material_do_aluno(db, material_id, current_student.id)

    material.anotacoes_aluno = payload.anotacoes
    db.commit()

    return {"success": True, "anotacoes": material.anotacoes_aluno}
