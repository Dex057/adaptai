"""
Rotas de Materiais Adaptados para Estudantes.

TC-027/028/031/032/033/081/088/118/123/124/125 (cluster "material nao chega no aluno"):
o professor gera material pela tela "Criar com IA" (POST /materiais-adaptados/gerar),
que persiste em `materiais_adaptados_gerados` (model MaterialAdaptadoGerado, ligado a
`student_id`). O Portal do Aluno, porem, lia apenas de `materiais`/`materiais_alunos`
(GET /student/materiais/) - duas tabelas que aquele pipeline nunca popula. Resultado:
tudo que o professor gerava ficava invisivel para o aluno.

Este modulo e a ponte de LEITURA que faltava: expoe ao aluno logado exatamente os
materiais que ja existem gravados para ele, sem migration, sem duplicar dado e sem
alterar nenhum contrato existente (`/student/materiais/` continua igual). A opcao de
"copiar" cada MaterialAdaptadoGerado para Material/MaterialAluno foi descartada por
duplicar dado e exigir migration/backfill para os materiais ja gerados.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.student import Student
from app.models.material_adaptado_gerado import MaterialAdaptadoGerado
from app.api.dependencies import get_current_student

router = APIRouter(
    prefix="/student/materiais-adaptados",
    tags=["Student - Materiais Adaptados"],
)


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
    materiais = (
        db.query(MaterialAdaptadoGerado)
        .filter(MaterialAdaptadoGerado.student_id == current_student.id)
        .order_by(MaterialAdaptadoGerado.created_at.desc())
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
    material = (
        db.query(MaterialAdaptadoGerado)
        .filter(
            MaterialAdaptadoGerado.id == material_id,
            MaterialAdaptadoGerado.student_id == current_student.id,
        )
        .first()
    )

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado",
        )

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
    }
