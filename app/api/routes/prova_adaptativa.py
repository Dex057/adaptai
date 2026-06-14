"""
Rotas para Provas Adaptativas (Reforço)
Sistema de geração automática de provas focadas em pontos fracos
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict

from app.database import get_db
from app.models.user import User
from app.models.prova import ProvaAluno
from app.models.analise_qualitativa import AnaliseQualitativa
from app.api.dependencies import get_current_active_user
from app.services.prova_adaptativa_service import prova_adaptativa_service

router = APIRouter(prefix="/prova-adaptativa", tags=["🎯 Prova Adaptativa (Reforço)"])


@router.post("/gerar-reforco/{prova_aluno_id}")
def gerar_prova_reforco_manual(
    prova_aluno_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Gera manualmente uma prova de reforço para um aluno
    
    O professor pode usar este endpoint para gerar uma prova de reforço
    quando desejar, mesmo se a geração automática não ocorreu.
    """
    
    # Verificar se prova existe e se professor tem acesso
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == prova_aluno_id).first()
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova do aluno não encontrada"
        )
    
    # Verificar se professor criou a prova original
    if prova_aluno.prova.criado_por_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para gerar prova de reforço desta prova"
        )
    
    # Verificar se prova está corrigida
    if prova_aluno.status.value not in ['corrigida', 'concluida']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A prova precisa estar corrigida para gerar prova de reforço"
        )
    
    # Verificar se existe análise qualitativa
    analise = db.query(AnaliseQualitativa).filter(
        AnaliseQualitativa.prova_aluno_id == prova_aluno_id
    ).first()
    
    if not analise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Análise qualitativa não encontrada. Gere a análise primeiro."
        )
    
    # Verificar se há conteúdos para revisar
    if not analise.conteudos_revisar or len(analise.conteudos_revisar) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não há conteúdos identificados para reforço. O aluno teve ótimo desempenho!"
        )
    
    try:
        # Gerar prova de reforço
        prova_reforco = prova_adaptativa_service.gerar_prova_reforco(
            db=db,
            prova_aluno_id=prova_aluno_id,
            analise_id=analise.id
        )
        
        # Associar ao aluno
        prova_aluno_reforco = prova_adaptativa_service.associar_prova_ao_aluno(
            db=db,
            prova_id=prova_reforco.id,
            aluno_id=prova_aluno.aluno_id
        )
        
        return {
            "success": True,
            "message": "Prova de reforço gerada com sucesso!",
            "prova_reforco": {
                "id": prova_reforco.id,
                "titulo": prova_reforco.titulo,
                "descricao": prova_reforco.descricao,
                "quantidade_questoes": prova_reforco.quantidade_questoes,
                "conteudos_focados": analise.conteudos_revisar
            },
            "prova_aluno_id": prova_aluno_reforco.id,
            "aluno": {
                "id": prova_aluno.aluno.id,
                "nome": prova_aluno.aluno.name
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar prova de reforço. Tente novamente mais tarde."
        )


@router.get("/verificar-reforco/{prova_aluno_id}")
def verificar_prova_reforco_existe(
    prova_aluno_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Verifica se já existe uma prova de reforço gerada para esta prova
    """
    
    # Buscar prova original
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == prova_aluno_id).first()
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    # Verificar se professor tem acesso
    if prova_aluno.prova.criado_por_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão"
        )
    
    # Buscar análise
    analise = db.query(AnaliseQualitativa).filter(
        AnaliseQualitativa.prova_aluno_id == prova_aluno_id
    ).first()
    
    analise_existe = analise is not None
    
    # Buscar provas de reforço do aluno (com título começando com "🎯 Reforço:")
    from app.models.prova import Prova
    provas_reforco = db.query(ProvaAluno, Prova).join(
        Prova, ProvaAluno.prova_id == Prova.id
    ).filter(
        ProvaAluno.aluno_id == prova_aluno.aluno_id,
        Prova.titulo.like('🎯 Reforço:%')
    ).all()
    
    provas_reforco_lista = []
    for pa, prova in provas_reforco:
        provas_reforco_lista.append({
            "id": prova.id,
            "prova_aluno_id": pa.id,
            "titulo": prova.titulo,
            "status": pa.status.value,
            "data_atribuicao": pa.data_atribuicao.isoformat() if pa.data_atribuicao else None
        })
    
    return {
        "analise_existe": analise_existe,
        "tem_conteudos_revisar": len(analise.conteudos_revisar) > 0 if analise else False,
        "conteudos_revisar": analise.conteudos_revisar if analise else [],
        "pode_gerar_reforco": analise_existe and (len(analise.conteudos_revisar) > 0 if analise else False),
        "provas_reforco_geradas": provas_reforco_lista,
        "total_provas_reforco": len(provas_reforco_lista)
    }
