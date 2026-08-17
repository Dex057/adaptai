"""
Rotas para Geração de Materiais Adaptados
VERSÃO MEGA COMPLETA: 25+ tipos de materiais
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import time
import json

from app.database import get_db
from app.api.dependencies import get_current_active_user, verificar_acesso_aluno
from app.core.logging_config import get_logger
from app.core.rate_limit import check_rate_limit
from app.core.pagination import PaginationParams, build_page
from app.models.user import User
from app.models.student import Student
from app.models.material_adaptado_gerado import MaterialAdaptadoGerado
from app.services.ai_materiais_service import MaterialAdaptadoService

logger = get_logger(__name__)

router = APIRouter(prefix="/materiais-adaptados", tags=["Materiais Adaptados"])


class MaterialRequest(BaseModel):
    student_id: int
    disciplina: str
    serie: Optional[str] = None
    conteudo: str
    tipos_material: List[str]


# ============================================================================
# HOMOLOGACAO DE TIPOS (2026-08-11)
# ============================================================================
# Dos 37 tipos implementados, apenas os listados abaixo passaram na validacao
# de qualidade. Os demais continuam com prompt, viewer e historico intactos —
# apenas nao podem ser gerados. Isso evita entregar material ruim ao aluno sem
# perder o trabalho ja feito.
#
# PARA LIBERAR UM TIPO: adicione o id em TIPOS_HABILITADOS.
#
# !! MANTENHA EM SINCRONIA COM O FRONTEND !!
# Espelho em adaptai-frontend/src/pages/materiaisAdaptados/config.js
# (const TIPOS_HABILITADOS). Aqui e a fonte de verdade que REJEITA; la e so o
# que a UI deixa clicar.
TIPOS_HABILITADOS = {
    # 📚 Leitura (completo)
    "texto_niveis", "resumo_estruturado", "ficha_leitura",
    # 🎨 Visual
    "infografico", "tabela_comparativa", "linha_tempo", "diagrama_venn",
    # mapa_mental: nao constava na lista de homologacao, mas tem viewer
    # dedicado e esta em uso em producao — bloquea-lo seria regressao.
    "mapa_mental",
    # 2026-08-15 — geracao de imagem real (Flux/fal.ai) ligada em
    # ai_materiais_service._ilustrar_itens + viewer dedicado no front
    # (IlustradosViewers.jsx). Requer FAL_API_KEY; sem ela, degrada pro texto
    # da descricao (nunca quebra, so nao ilustra).
    "hq_tirinha",
    # 🧠 Memorizacao
    "flashcards", "jogo_memoria",
    # 2026-08-15 — mesma liberacao de hq_tirinha (ilustracao real por figurinha).
    "album_figurinhas",
    # 🎮 Jogos
    "caca_palavras", "quiz_interativo", "roleta_perguntas",
    # cruzadinha: mesma situacao do mapa_mental (viewer dedicado, em producao).
    "cruzadinha",
    # 2026-08-14 — rodada 1 de liberacao: ganharam viewer dedicado no front
    # (JogosTabuleiroViewers.jsx). Espelhar SEMPRE com TIPOS_HABILITADOS de
    # adaptai-frontend/src/pages/materiaisAdaptados/config.js.
    "arvore_decisao", "bingo", "domino", "trilha_aprendizagem",
    # 💙 TEA/TDAH
    "historia_social", "termometro_emocoes", "cartoes_comunicacao",
    "checklist_tarefas",
    # 2026-08-14 — rodada 2 de liberacao (front: TeaTdahViewers.jsx).
    # sequenciamento ja constava com viewer, mas o viewer lia campos errados
    # (titulo/descricao em vez de acao/dica/checkpoint) — corrigido junto.
    "quadro_rotina", "contrato_comportamento", "painel_primeiro_depois",
    "sequenciamento",
    # ✍️ Completar
    "verdadeiro_falso", "complete_lacunas", "ordenar_sequencia",
    # 2026-08-14 — rodada 2 (front: InterativosViewers.jsx).
    "ligue_colunas",
    # 📝 Avaliacao (qualidade dos 3 formatos ainda em validacao pedagogica)
    "avaliacao",
    # 🔬 Praticos (categoria inteira; qualidade a validar)
    "experimento", "receita_procedimento", "estudo_caso", "diario_bordo",
}


# Mapeamento de tipos para métodos do service
TIPOS_MATERIAIS = {
    # Leitura
    "texto_niveis": {"metodo": "gerar_texto_3_niveis", "nome": "Texto em 3 Níveis", "categoria": "📚 Leitura", "usa_diagnostico": True},
    "resumo_estruturado": {"metodo": "gerar_resumo_estruturado", "nome": "Resumo Estruturado", "categoria": "📚 Leitura"},
    "ficha_leitura": {"metodo": "gerar_ficha_leitura", "nome": "Ficha de Leitura", "categoria": "📚 Leitura"},
    
    # Visual
    "infografico": {"metodo": "gerar_infografico", "nome": "Infográfico", "categoria": "🎨 Visual"},
    "mapa_mental": {"metodo": "gerar_mapa_mental", "nome": "Mapa Mental", "categoria": "🎨 Visual"},
    "linha_tempo": {"metodo": "gerar_linha_tempo", "nome": "Linha do Tempo", "categoria": "🎨 Visual"},
    "hq_tirinha": {"metodo": "gerar_hq_tirinha", "nome": "HQ/Tirinha", "categoria": "🎨 Visual"},
    "diagrama_venn": {"metodo": "gerar_diagrama_venn", "nome": "Diagrama de Venn", "categoria": "🎨 Visual"},
    "tabela_comparativa": {"metodo": "gerar_tabela_comparativa", "nome": "Tabela Comparativa", "categoria": "🎨 Visual"},
    "arvore_decisao": {"metodo": "gerar_arvore_decisao", "nome": "Árvore de Decisão", "categoria": "🎨 Visual"},
    
    # Memorização
    "flashcards": {"metodo": "gerar_flashcards", "nome": "Flashcards", "categoria": "🧠 Memorização"},
    "jogo_memoria": {"metodo": "gerar_jogo_memoria", "nome": "Jogo da Memória", "categoria": "🧠 Memorização"},
    "album_figurinhas": {"metodo": "gerar_album_figurinhas", "nome": "Álbum de Figurinhas", "categoria": "🧠 Memorização"},
    
    # Jogos
    "caca_palavras": {"metodo": "gerar_caca_palavras", "nome": "Caça-Palavras", "categoria": "🎮 Jogos"},
    "cruzadinha": {"metodo": "gerar_cruzadinha", "nome": "Cruzadinha", "categoria": "🎮 Jogos"},
    "bingo": {"metodo": "gerar_bingo_educativo", "nome": "Bingo Educativo", "categoria": "🎮 Jogos"},
    "domino": {"metodo": "gerar_domino", "nome": "Dominó Educativo", "categoria": "🎮 Jogos"},
    "quiz_interativo": {"metodo": "gerar_quiz_interativo", "nome": "Quiz Interativo", "categoria": "🎮 Jogos"},
    "trilha_aprendizagem": {"metodo": "gerar_trilha_aprendizagem", "nome": "Trilha/Tabuleiro", "categoria": "🎮 Jogos"},
    "roleta_perguntas": {"metodo": "gerar_roleta_perguntas", "nome": "Roleta de Perguntas", "categoria": "🎮 Jogos"},
    
    # TEA/TDAH
    "historia_social": {"metodo": "gerar_historia_social", "nome": "História Social", "categoria": "💙 TEA/TDAH", "usa_diagnostico": True},
    "sequenciamento": {"metodo": "gerar_sequenciamento", "nome": "Sequenciamento Visual", "categoria": "💙 TEA/TDAH"},
    "quadro_rotina": {"metodo": "gerar_quadro_rotina", "nome": "Quadro de Rotina", "categoria": "💙 TEA/TDAH"},
    "cartoes_comunicacao": {"metodo": "gerar_cartoes_comunicacao", "nome": "Cartões de Comunicação", "categoria": "💙 TEA/TDAH"},
    "termometro_emocoes": {"metodo": "gerar_termometro_emocoes", "nome": "Termômetro de Emoções", "categoria": "💙 TEA/TDAH"},
    "contrato_comportamento": {"metodo": "gerar_contrato_comportamento", "nome": "Contrato de Comportamento", "categoria": "💙 TEA/TDAH"},
    "checklist_tarefas": {"metodo": "gerar_checklist_tarefas", "nome": "Checklist de Tarefas", "categoria": "💙 TEA/TDAH"},
    "painel_primeiro_depois": {"metodo": "gerar_painel_primeiro_depois", "nome": "Primeiro-Depois", "categoria": "💙 TEA/TDAH"},
    
    # Completar
    "complete_lacunas": {"metodo": "gerar_complete_lacunas", "nome": "Complete as Lacunas", "categoria": "✍️ Completar"},
    "ligue_colunas": {"metodo": "gerar_ligue_colunas", "nome": "Ligue as Colunas", "categoria": "✍️ Completar"},
    "verdadeiro_falso": {"metodo": "gerar_verdadeiro_falso", "nome": "Verdadeiro ou Falso", "categoria": "✍️ Completar"},
    "ordenar_sequencia": {"metodo": "gerar_ordenar_sequencia", "nome": "Ordenar Sequência", "categoria": "✍️ Completar"},
    
    # Avaliação
    "avaliacao": {"metodo": "gerar_avaliacao_multiformato", "nome": "Avaliação 3 Formatos", "categoria": "📝 Avaliação", "usa_diagnostico": True},
    
    # Práticos
    "experimento": {"metodo": "gerar_experimento", "nome": "Experimento", "categoria": "🔬 Práticos"},
    "receita_procedimento": {"metodo": "gerar_receita_procedimento", "nome": "Receita/Procedimento", "categoria": "🔬 Práticos"},
    "estudo_caso": {"metodo": "gerar_estudo_caso", "nome": "Estudo de Caso", "categoria": "🔬 Práticos"},
    "diario_bordo": {"metodo": "gerar_diario_bordo", "nome": "Diário de Bordo", "categoria": "🔬 Práticos"},
}


@router.post("/gerar")
async def gerar_materiais_adaptados(
    request_body: MaterialRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    🎨 GERA MATERIAIS EDUCACIONAIS ADAPTADOS
    
    25+ tipos disponiveis! A serie e obtida automaticamente do aluno.
    
    SEGURANCA: rate limited a 20 geracoes por hora por IP 
    (cada geracao pode fazer ate 25 chamadas caras a API Claude).
    """
    # SEGURANCA: limitar gastos com IA por IP
    check_rate_limit(
        request, key="gerar_material_adaptado", max_requests=20, window_seconds=3600,
        error_message="Limite de geracoes de IA atingido. Aguarde 1 hora."
    )
    
    inicio = time.time()

    # HOMOLOGACAO: recusar tipos ainda nao liberados ANTES de gastar credito de
    # IA. A UI ja bloqueia o clique, entao chegar aqui significa chamada direta
    # a API ou state antigo no browser. 422 com a lista do que foi recusado.
    nao_liberados = [
        t for t in request_body.tipos_material
        if t in TIPOS_MATERIAIS and t not in TIPOS_HABILITADOS
    ]
    if nao_liberados:
        raise HTTPException(
            status_code=422,
            detail=(
                "Os seguintes tipos ainda estao em validacao e nao podem ser "
                f"gerados: {', '.join(nao_liberados)}."
            ),
        )

    # SEGURANCA: verificar acesso ao aluno (evita IDOR entre escolas)
    student = verificar_acesso_aluno(db, request_body.student_id, current_user)
    
    # Serie: usar do aluno se nao informada
    serie = request_body.serie or student.grade_level or "Nao especificada"
    
    # Extrair diagnosticos do aluno
    diagnosticos = {}
    if student.diagnosis:
        diag = student.diagnosis
        diagnosticos = {
            "tea": diag.get("tea", False),
            "tea_nivel": diag.get("tea_nivel", ""),
            "tdah": diag.get("tdah", False),
            "dislexia": diag.get("dislexia", False),
            "discalculia": diag.get("discalculia", False),
            "disgrafia": diag.get("disgrafia", False),
            "deficiencia_intelectual": diag.get("deficiencia_intelectual", False),
            "superdotacao": diag.get("superdotacao", False),
            "caracteristicas": diag.get("caracteristicas", ""),
            "pontos_fortes": diag.get("pontos_fortes", ""),
            "dificuldades": diag.get("dificuldades", "")
        }
    
    # Inicializar service
    service = MaterialAdaptadoService()
    
    # Resposta base
    response = {
        "success": True,
        "student_name": student.name,
        "student_serie": serie,
        "disciplina": request_body.disciplina,
        "conteudo": request_body.conteudo,
        "materiais_gerados": []
    }
    
    # Gerar cada tipo de material solicitado
    erros = []
    for tipo in request_body.tipos_material:
        if tipo not in TIPOS_MATERIAIS:
            erros.append(f"Tipo '{tipo}' nao encontrado")
            continue
        
        config = TIPOS_MATERIAIS[tipo]
        metodo_nome = config["metodo"]
        
        try:
            print(f"[IA] Gerando {config['nome']}...")
            metodo = getattr(service, metodo_nome)
            
            # Chamar metodo com ou sem diagnosticos
            if config.get("usa_diagnostico"):
                resultado = metodo(request_body.disciplina, serie, request_body.conteudo, diagnosticos)
            else:
                resultado = metodo(request_body.disciplina, serie, request_body.conteudo)
            
            response[tipo] = resultado
            response["materiais_gerados"].append(tipo)
            print(f"[OK] {config['nome']} gerado!")
            
        except Exception as e:
            print(f"[ERRO] Gerar {config['nome']}: {type(e).__name__}: {e}")
            # 2026-08-11: a mensagem era sempre "erro na geracao", sem nenhuma
            # pista. Em producao apareceu "Texto em 3 Niveis: erro na geracao"
            # e nao havia como o professor (nem nos) saber a causa — que era
            # truncamento no limite de tokens.
            #
            # SEGURANCA: continuamos sem vazar stack trace ou detalhe interno.
            # Classificamos em causas acionaveis e devolvemos so isso.
            if isinstance(e, ValueError) and "limite de" in str(e):
                # Truncamento — mensagem ja e segura e orienta o professor.
                motivo = (
                    "o conteúdo pedido é longo demais e a resposta foi cortada. "
                    "Tente um tema mais específico."
                )
            elif isinstance(e, json.JSONDecodeError):
                motivo = "a IA respondeu em um formato inesperado. Tente gerar novamente."
            else:
                motivo = "erro na geração. Tente novamente em alguns instantes."
            erros.append(f"{config['nome']}: {motivo}")
    
    if erros:
        response["erros"] = erros
    
    tempo_total = time.time() - inicio
    response["tempo_geracao"] = round(tempo_total, 2)

    # ------------------------------------------------------------------
    # 2026-08-11 — NAO SALVAR GERACAO VAZIA
    # ------------------------------------------------------------------
    # Antes, o registro era gravado SEMPRE — mesmo quando todos os tipos
    # falhavam. Isso poluia o historico do aluno com materiais vazios, que
    # ainda assim contavam nas estatisticas e apareciam em /aluno/materiais
    # como cards que nao abrem nada.
    #
    # Regra: so persiste se pelo menos um tipo foi gerado. Se nada saiu,
    # devolvemos 422 com a lista de erros — o professor ve o motivo e nada
    # e gravado.
    if not response["materiais_gerados"]:
        print(f"[SKIP] Nenhum material gerado - nada sera salvo. Erros: {erros}")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Nenhum material pôde ser gerado.",
                "erros": erros or ["Falha desconhecida na geração."],
            },
        )

    # Tipos que efetivamente entraram no registro (nao os solicitados).
    # Sem isso, um material com 1 de 3 tipos gerados exibia 3 selos no card
    # do aluno, dois deles sem conteudo por tras.
    response["tipos_solicitados"] = request_body.tipos_material

    # Salvar no banco
    #
    # 2026-08-17 — NAO ENGOLIR FALHA DE SAVE EM SILENCIO
    # ------------------------------------------------------------------
    # Antes, uma excecao aqui virava so um print() e a rota devolvia 200
    # com o material inteiro no corpo mesmo sem persistir nada — o
    # professor via "Material Gerado!" na hora (o front so olha o corpo
    # da resposta, nunca confere material_id) e o material sumia na
    # proxima visita ao historico. Suspeita forte: o proprio JSON com
    # imagens embutidas em base64 (hq_tirinha/album_figurinhas, ate ~6,6MB
    # — ver docs/dashcentral.md) estourando algum limite do MySQL no
    # commit. Sem logar a excecao de verdade, essa causa nunca ficava
    # visivel — daqui pra frente fica no log, e o front recebe 500 real
    # em vez de sucesso fingido.
    try:
        material_salvo = MaterialAdaptadoGerado(
            student_id=request_body.student_id,
            disciplina=request_body.disciplina,
            serie=serie,
            conteudo=request_body.conteudo,
            tipos_material=response["materiais_gerados"],
            resultado_json=response,
            tempo_geracao=int(tempo_total),
            created_by=current_user.id
        )
        db.add(material_salvo)
        db.commit()
        db.refresh(material_salvo)
        response["material_id"] = material_salvo.id
        return response
    except Exception as e:
        db.rollback()
        tamanho_kb = len(json.dumps(response, default=str)) // 1024
        logger.exception(
            "Falha ao salvar material adaptado (student_id=%s, tipos=%s, "
            "resultado_json ~%d KB)",
            request_body.student_id, response.get("materiais_gerados"), tamanho_kb,
        )
        # A IA ja rodou e ja custou credito - por isso o erro e explicito
        # (nao um 200 mentiroso) mas nao descarta silenciosamente: quem
        # olhar o log tem tamanho do payload e tipo da excecao pra
        # diagnosticar (ex.: estouro de max_allowed_packet do MySQL).
        raise HTTPException(
            status_code=500,
            detail={
                "message": (
                    "O material foi gerado mas não foi possível salvá-lo. "
                    "Tente novamente - se persistir, avise o suporte."
                ),
                "erro_tipo": type(e).__name__,
            },
        )


@router.get("/tipos-disponiveis")
async def listar_tipos_materiais(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista os tipos de materiais por categoria.

    Cada item traz `disponivel`: False = implementado porem ainda em validacao
    de qualidade ("Em breve" na UI). O frontend usa isto para desabilitar o
    card sem precisar duplicar a regra.
    """

    # Agrupar por categoria
    por_categoria = {}
    for tipo_id, config in TIPOS_MATERIAIS.items():
        categoria = config["categoria"]
        if categoria not in por_categoria:
            por_categoria[categoria] = []

        por_categoria[categoria].append({
            "id": tipo_id,
            "nome": config["nome"],
            "usa_diagnostico": config.get("usa_diagnostico", False),
            "disponivel": tipo_id in TIPOS_HABILITADOS,
        })

    return {
        "total_tipos": len(TIPOS_MATERIAIS),
        "total_disponiveis": len(TIPOS_HABILITADOS),
        "por_categoria": por_categoria,
        "lista_completa": [
            {
                "id": k,
                "nome": v["nome"],
                "categoria": v["categoria"],
                "disponivel": k in TIPOS_HABILITADOS,
            }
            for k, v in TIPOS_MATERIAIS.items()
        ],
    }


@router.get("/historico/student/{student_id}")
async def listar_historico_student(
    student_id: int,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lista historico de materiais gerados para um aluno (paginado).
    
    Query params:
    - page: pagina (default 1)
    - size: itens por pagina (default 20, max 100)
    
    Resposta no formato {items, meta} + chaves legadas 'total'/'materiais'
    para compatibilidade com frontend existente.
    """
    
    # SEGURANCA: verificar acesso ao aluno (evita IDOR entre escolas)
    student = verificar_acesso_aluno(db, student_id, current_user)
    
    query = db.query(MaterialAdaptadoGerado)\
        .filter(MaterialAdaptadoGerado.student_id == student_id)\
        .order_by(MaterialAdaptadoGerado.created_at.desc())
    
    total = query.count()
    materiais = query.offset(pagination.offset).limit(pagination.limit).all()
    
    items = [
        {
            "id": m.id,
            "disciplina": m.disciplina,
            "serie": m.serie,
            "conteudo": m.conteudo,
            "tipos_material": m.tipos_material,
            "tempo_geracao": m.tempo_geracao,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in materiais
    ]
    
    page = build_page(items=items, total=total, pagination=pagination)
    # Compat retroativa: manter 'total' e 'materiais' no nivel raiz
    page["total"] = total
    page["materiais"] = items
    return page


@router.get("/historico/{material_id}")
async def buscar_material_por_id(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """🔍 Busca material específico por ID"""
    
    material = db.query(MaterialAdaptadoGerado)\
        .filter(MaterialAdaptadoGerado.id == material_id).first()
    
    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado")
    
    # SEGURANCA: verificar acesso ao aluno dono do material (evita IDOR)
    verificar_acesso_aluno(db, material.student_id, current_user)
    
    return {
        "id": material.id,
        "student_id": material.student_id,
        "student_name": material.student.name if material.student else "Aluno",
        "disciplina": material.disciplina,
        "serie": material.serie,
        "conteudo": material.conteudo,
        "tipos_material": material.tipos_material,
        "resultado": material.resultado_json,
        "tempo_geracao": material.tempo_geracao,
        "created_at": material.created_at.isoformat() if material.created_at else None
    }


@router.delete("/historico/{material_id}")
async def deletar_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """🗑️ Deleta material do histórico"""
    
    material = db.query(MaterialAdaptadoGerado)\
        .filter(MaterialAdaptadoGerado.id == material_id).first()
    
    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado")
    
    # SEGURANCA: verificar acesso ao aluno dono do material (evita IDOR)
    verificar_acesso_aluno(db, material.student_id, current_user)
    
    db.delete(material)
    db.commit()
    
    return {"message": "Material deletado com sucesso"}
