"""
Rotas de Materiais para Estudantes - COM STORAGE
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from typing import List

from app.database import get_db
from app.models.student import Student
from app.models.material import Material, MaterialAluno, StatusMaterial
from app.schemas.material import (
    MaterialAlunoResponse, VisualizarMaterialRequest,
    AnotacaoRequest, FavoritoRequest
)
from app.services.material_conteudo import ler_conteudo
from app.api.dependencies import get_current_student

router = APIRouter(prefix="/student/materiais", tags=["Student - Materiais"])


# NOTA: get_current_student agora vem de app.api.dependencies (C4 - centralizado).
# Antes estava duplicado aqui. Mesma assinatura e comportamento.


@router.get("/", response_model=List[MaterialAlunoResponse])
async def listar_meus_materiais(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Lista todos os materiais disponíveis para o aluno
    """
    # Buscar materiais do aluno com status DISPONIVEL
    # joinedload: a resposta embute o material (MaterialAlunoResponse.material)
    # e, sem isto, cada linha disparava um SELECT extra para carregar o
    # relacionamento (N+1). `Material.conteudo_gerado` fica de fora - e
    # deferred, e a listagem nao precisa do conteudo.
    materiais_aluno = db.query(MaterialAluno).join(Material).options(
        joinedload(MaterialAluno.material)
    ).filter(
        MaterialAluno.aluno_id == current_student.id,
        Material.status == StatusMaterial.DISPONIVEL
    ).all()
    
    return materiais_aluno


@router.get("/{material_aluno_id}/visualizar")
async def visualizar_material(
    material_aluno_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Visualiza um material e registra a visualização
    Retorna o conteúdo do storage
    """
    # Buscar MaterialAluno
    material_aluno = db.query(MaterialAluno).filter(
        MaterialAluno.id == material_aluno_id,
        MaterialAluno.aluno_id == current_student.id
    ).first()
    
    if not material_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    # Verificar se material está disponível
    if material_aluno.material.status != StatusMaterial.DISPONIVEL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Material não está disponível. Status: {material_aluno.material.status}"
        )
    
    # FIX: primeiro carregar o conteudo e so entao registrar visualizacao.
    # Antes, o codigo commitava a visualizacao ANTES de verificar se o tipo
    # era suportado, e tipos nao-VISUAL/MAPA_MENTAL caiam num return implicito
    # None (commitando inflacao do contador + resposta vazia pro aluno).
    material = material_aluno.material
    
    # 2026-08-17: a leitura passou a ser a MESMA da rota do professor
    # (services/material_conteudo.ler_conteudo): banco primeiro, storage como
    # fallback. Antes esta rota so aceitava VISUAL e MAPA_MENTAL e devolvia 501
    # para os outros quatro tipos da Biblioteca (resumo, texto_simplificado,
    # roteiro_estudo, atividades) — o professor atribuia o material e o aluno
    # batia num erro que nao dizia nada a ele. Com o helper compartilhado, todo
    # tipo que o professor consegue gerar, o aluno consegue abrir (incluindo o
    # novo 'geometria').
    conteudo_tipo, conteudo = ler_conteudo(material)

    if not conteudo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conteúdo do material não encontrado"
        )
    
    # Registrar visualização agora que sabemos que vamos entregar o conteudo
    if material_aluno.data_primeira_visualizacao is None:
        material_aluno.data_primeira_visualizacao = func.now()
    
    material_aluno.data_ultima_visualizacao = func.now()
    material_aluno.total_visualizacoes += 1
    
    db.commit()
    db.refresh(material_aluno)
    
    return {
        "material_aluno": material_aluno,
        "material": {
            "id": material.id,
            "titulo": material.titulo,
            "descricao": material.descricao,
            "tipo": material.tipo,
            "materia": material.materia,
            "serie_nivel": material.serie_nivel
        },
        "conteudo_tipo": conteudo_tipo,
        "conteudo": conteudo
    }


@router.post("/{material_aluno_id}/favorito")
async def marcar_favorito(
    material_aluno_id: int,
    favorito_data: FavoritoRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Marcar ou desmarcar material como favorito"""
    material_aluno = db.query(MaterialAluno).filter(
        MaterialAluno.id == material_aluno_id,
        MaterialAluno.aluno_id == current_student.id
    ).first()
    
    if not material_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    material_aluno.favorito = 1 if favorito_data.favorito else 0
    db.commit()
    
    return {"success": True, "favorito": bool(material_aluno.favorito)}


@router.post("/{material_aluno_id}/anotacoes")
async def salvar_anotacoes(
    material_aluno_id: int,
    anotacoes_data: AnotacaoRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Salvar anotações do aluno sobre o material"""
    material_aluno = db.query(MaterialAluno).filter(
        MaterialAluno.id == material_aluno_id,
        MaterialAluno.aluno_id == current_student.id
    ).first()
    
    if not material_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    material_aluno.anotacoes_aluno = anotacoes_data.anotacoes
    db.commit()
    
    return {"success": True, "anotacoes": material_aluno.anotacoes_aluno}
