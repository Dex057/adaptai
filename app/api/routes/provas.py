"""
🎓 AdaptAI - Rotas de Prova
Endpoints para gerenciamento de provas com IA

ATUALIZADO: Aceita aluno_ids e adaptacoes para criar provas contextualizadas
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timezone

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.student import Student
from app.models.prova import (
    Prova,
    QuestaoGerada,
    ProvaAluno,
    RespostaAluno,
    StatusProva,
    StatusProvaAluno,
    TipoQuestao
)
from app.schemas.prova import (
    ProvaCreate,
    ProvaResponse,
    ProvaListResponse,
    ProvaUpdate,
    GerarProvaRequest,
    ProvaAlunoCreate,
    ProvaAlunoResponse,
    ProvaAlunoListResponse,
    IniciarProvaRequest,
    FinalizarProvaRequest,
    RespostaAlunoCreate,
    RespostaAlunoResponse,
    CorrigirProvaResponse,
    CorrigirQuestaoRequest,
    CorrigirQuestaoResponse,
    ProvaParaAluno,
    QuestaoParaAluno
)
from app.services.prova_ai_service import prova_ai_service, ProvaIAError
from app.api.dependencies import get_current_user, oauth2_scheme, get_user_from_token, verificar_acesso_aluno
from app.core.tenant import enforce_limite_provas

router = APIRouter(prefix="/provas")


def _tipo_questao_valido(valor, padrao: TipoQuestao) -> TipoQuestao:
    """
    TC-150: converte o `tipo` que veio da IA em TipoQuestao, caindo no tipo da
    prova quando o valor nao existe no enum. Sem isso, um rotulo inventado pela
    IA viraria erro de gravacao e derrubaria a geracao inteira da prova.
    """
    if isinstance(valor, TipoQuestao):
        return valor
    if isinstance(valor, str):
        try:
            return TipoQuestao(valor.strip().lower())
        except ValueError:
            return padrao
    return padrao


def _verificar_acesso_prova(prova, current_user) -> None:
    """SEGURANCA (anti-IDOR): garante que o usuario e dono da prova (criada por
    ele) ou super_admin. Levanta 403 caso contrario. Espelha o padrao ja usado
    em professor_analytics.py e prova_adaptativa.py."""
    from app.models.user import UserRole
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    if prova.criado_por_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voce nao tem permissao para acessar esta prova"
        )


# ============= ENDPOINTS ADMIN =============

@router.post("/gerar", response_model=ProvaResponse, status_code=status.HTTP_201_CREATED)
async def gerar_prova_com_ia(
    request: GerarProvaRequest,
    token: str = Depends(oauth2_scheme)
):
    """
    Gerar prova automaticamente com IA
    
    **Fluxo:**
    1. Admin define o tema/conteudo e configuracoes
    2. IA (Claude) gera automaticamente as questoes
    3. Prova e salva no banco de dados
    4. (NOVO) Se aluno_ids fornecidos, associa automaticamente
    
    **Parâmetros novos:**
    - aluno_ids: Lista de IDs de alunos para associar à prova
    - adaptacoes: Lista de diagnósticos para adaptar questões (TEA, TDAH, etc.)
    
    **Requer:** Autenticacao de admin/professor
    """
    
    # Valida usuario e fecha conexao ANTES de chamar IA
    current_user = get_user_from_token(token)
    user_id = current_user.id

    # Limite de plano (soft): checa em sessao curta antes de gastar IA.
    _db_lim = SessionLocal()
    try:
        enforce_limite_provas(_db_lim, current_user)
    finally:
        _db_lim.close()
    
    try:
        # PASSO 1: Gera questoes com IA (SEM conexao com banco)
        # Inclui adaptações se houver alunos neurodivergentes
        print(f"[GERANDO] {request.quantidade_questoes} questoes com IA...")
        
        # Prepara prompt com adaptações se necessário
        conteudo_com_adaptacoes = request.conteudo_prompt
        if request.adaptacoes and len(request.adaptacoes) > 0:
            adaptacoes_str = ", ".join(request.adaptacoes)
            conteudo_com_adaptacoes = f"""
{request.conteudo_prompt}

IMPORTANTE - ADAPTAÇÕES NECESSÁRIAS:
Os alunos possuem os seguintes diagnósticos: {adaptacoes_str}

Por favor, adapte as questões considerando:
- Enunciados claros e objetivos
- Evitar duplas negações
- Usar linguagem simples e direta
- Para alunos com TEA: evitar metáforas e expressões figurativas
- Para alunos com TDAH: questões mais curtas e focadas
- Para alunos com dislexia: fonte clara, espaçamento adequado
"""
            print(f"[INFO] Aplicando adaptações para: {adaptacoes_str}")
        
        questoes_geradas = await prova_ai_service.gerar_questoes(
            conteudo_prompt=conteudo_com_adaptacoes,
            materia=request.materia,
            serie_nivel=request.serie_nivel or "Nao especificado",
            quantidade=request.quantidade_questoes,
            tipo_questao=request.tipo_questao,
            dificuldade=request.dificuldade
        )
        print(f"[OK] IA gerou {len(questoes_geradas)} questoes")
        
        # PASSO 2: Abre NOVA conexao e salva tudo (conexao fresca)
        db = SessionLocal()
        try:
            # Cria a prova
            nova_prova = Prova(
                titulo=request.titulo,
                descricao=request.descricao,
                conteudo_prompt=request.conteudo_prompt,
                materia=request.materia,
                serie_nivel=request.serie_nivel,
                quantidade_questoes=request.quantidade_questoes,
                tipo_questao=request.tipo_questao,
                dificuldade=request.dificuldade,
                tempo_limite_minutos=request.tempo_limite_minutos,
                pontuacao_total=request.pontuacao_total,
                nota_minima_aprovacao=request.nota_minima_aprovacao,
                status=StatusProva.ATIVA,
                criado_por_id=user_id
            )
            
            db.add(nova_prova)
            db.flush()  # Get prova.id
            
            # Adiciona as questoes geradas
            pontos_por_questao = request.pontuacao_total / request.quantidade_questoes
            
            for questao_data in questoes_geradas:
                # TC-150: a questao guarda o tipo QUE ELA TEM, nao o tipo pedido
                # na prova. Gravar `request.tipo_questao` em todas achatava
                # qualquer variacao vinda da IA - inclusive uma dissertativa
                # devolvida sem `resposta_correta`, que ficava rotulada como
                # multipla escolha e chegava ao aluno sem campo de resposta.
                # Valor invalido cai no tipo da prova (a IA as vezes inventa
                # rotulo), entao isso nunca quebra a geracao.
                tipo_questao = _tipo_questao_valido(
                    questao_data.get("tipo"), request.tipo_questao
                )
                questao = QuestaoGerada(
                    prova_id=nova_prova.id,
                    numero=questao_data.get("numero"),
                    enunciado=questao_data.get("enunciado"),
                    tipo=tipo_questao,
                    dificuldade=questao_data.get("dificuldade", request.dificuldade),
                    opcoes=questao_data.get("opcoes"),
                    resposta_correta=questao_data.get("resposta_correta"),
                    criterios_avaliacao=questao_data.get("criterios_avaliacao"),
                    pontuacao=pontos_por_questao,
                    explicacao=questao_data.get("explicacao"),
                    tags=questao_data.get("tags", [])
                )
                db.add(questao)
            
            # PASSO 3 (NOVO): Associar alunos automaticamente se fornecidos
            if request.aluno_ids and len(request.aluno_ids) > 0:
                print(f"[ASSOCIANDO] Prova a {len(request.aluno_ids)} aluno(s)...")
                
                for aluno_id in request.aluno_ids:
                    # Verifica se aluno existe
                    aluno = db.query(Student).filter(Student.id == aluno_id).first()
                    if aluno:
                        # Verifica se já não está associado
                        ja_associado = db.query(ProvaAluno).filter(
                            ProvaAluno.prova_id == nova_prova.id,
                            ProvaAluno.aluno_id == aluno_id
                        ).first()
                        
                        if not ja_associado:
                            prova_aluno = ProvaAluno(
                                prova_id=nova_prova.id,
                                aluno_id=aluno_id,
                                status=StatusProvaAluno.PENDENTE,
                                pontuacao_maxima=request.pontuacao_total
                            )
                            db.add(prova_aluno)
                            print(f"   ✓ Associado ao aluno: {aluno.name}")
            
            db.commit()
            
            # Busca a prova com questoes carregadas (eager loading)
            prova_completa = db.query(Prova).options(
                joinedload(Prova.questoes)
            ).filter(Prova.id == nova_prova.id).first()
            
            print(f"[OK] Prova '{prova_completa.titulo}' criada com sucesso! (ID: {prova_completa.id})")
            
            return prova_completa
            
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
        
    except ProvaIAError as e:
        print(f"[IA] Falha ao gerar questoes: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        print(f"[ERRO] Erro ao gerar prova: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar prova. Tente novamente mais tarde."
        )


@router.get("/", response_model=List[ProvaListResponse])
def listar_provas(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """📋 Listar as provas criadas pelo usuario (super_admin ve todas)"""
    from app.models.user import UserRole
    query = db.query(Prova)
    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.filter(Prova.criado_por_id == current_user.id)
    provas = query.offset(skip).limit(limit).all()
    return provas


@router.get("/{prova_id}", response_model=ProvaResponse)
def obter_prova(
    prova_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """📄 Obter detalhes de uma prova específica (com questões e respostas)"""
    prova = db.query(Prova).filter(Prova.id == prova_id).first()
    
    if not prova:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova, current_user)
    return prova


@router.patch("/{prova_id}", response_model=ProvaResponse)
def atualizar_prova(
    prova_id: int,
    prova_update: ProvaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """✏️ Atualizar informações da prova"""
    prova = db.query(Prova).filter(Prova.id == prova_id).first()
    
    if not prova:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova, current_user)
    
    # Atualiza campos
    for field, value in prova_update.dict(exclude_unset=True).items():
        setattr(prova, field, value)
    
    prova.atualizado_em = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(prova)
    
    return prova


@router.delete("/{prova_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_prova(
    prova_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """🗑️ Deletar uma prova"""
    prova = db.query(Prova).filter(Prova.id == prova_id).first()
    
    if not prova:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova, current_user)
    
    db.delete(prova)
    db.commit()
    
    return None


# ============= ENDPOINTS ASSOCIAÇÃO PROVA-ALUNO =============

@router.post("/associar", response_model=ProvaAlunoResponse, status_code=status.HTTP_201_CREATED)
def associar_prova_ao_aluno(
    associacao: ProvaAlunoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    👨‍🎓 Associar prova a um aluno
    
    O admin seleciona uma prova e um aluno, e o sistema libera a prova para o aluno fazer.
    """
    
    # Verifica se prova existe
    prova = db.query(Prova).filter(Prova.id == associacao.prova_id).first()
    if not prova:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    # SEGURANCA: so o dono da prova pode associa-la (evita IDOR)
    _verificar_acesso_prova(prova, current_user)
    
    # Verifica se aluno existe (e se o usuario tem acesso a ele - evita IDOR)
    aluno = verificar_acesso_aluno(db, associacao.aluno_id, current_user)
    
    # Verifica se já está associado
    ja_associado = db.query(ProvaAluno).filter(
        ProvaAluno.prova_id == associacao.prova_id,
        ProvaAluno.aluno_id == associacao.aluno_id
    ).first()
    
    if ja_associado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta prova já está associada a este aluno"
        )
    
    # Cria associação
    prova_aluno = ProvaAluno(
        prova_id=associacao.prova_id,
        aluno_id=associacao.aluno_id,
        status=StatusProvaAluno.PENDENTE,
        pontuacao_maxima=prova.pontuacao_total
    )
    
    db.add(prova_aluno)
    db.commit()
    db.refresh(prova_aluno)
    
    print(f"[OK] Prova '{prova.titulo}' associada ao aluno '{aluno.name}'")
    
    return prova_aluno


@router.get("/aluno/{aluno_id}/provas", response_model=List[ProvaAlunoListResponse])
def listar_provas_do_aluno(
    aluno_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """📚 Listar todas as provas de um aluno"""
    # SEGURANCA: valida acesso ao aluno (evita IDOR)
    verificar_acesso_aluno(db, aluno_id, current_user)
    provas_aluno = db.query(ProvaAluno).filter(
        ProvaAluno.aluno_id == aluno_id
    ).all()
    
    return provas_aluno


# ============= ENDPOINTS DO ALUNO =============

@router.get("/aluno/{prova_aluno_id}/fazer", response_model=ProvaParaAluno)
def obter_prova_para_fazer(
    prova_aluno_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    📝 Obter prova para o aluno fazer
    
    Retorna as questões SEM as respostas corretas.
    """
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == prova_aluno_id).first()
    
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova_aluno.prova, current_user)
    prova = prova_aluno.prova
    
    # Monta questões sem respostas
    questoes_para_aluno = [
        QuestaoParaAluno(
            id=q.id,
            numero=q.numero,
            enunciado=q.enunciado,
            tipo=q.tipo,
            opcoes=q.opcoes,
            pontuacao=q.pontuacao
        )
        for q in prova.questoes
    ]
    
    return ProvaParaAluno(
        id=prova.id,
        titulo=prova.titulo,
        descricao=prova.descricao,
        materia=prova.materia,
        serie_nivel=prova.serie_nivel,
        tempo_limite_minutos=prova.tempo_limite_minutos,
        pontuacao_total=prova.pontuacao_total,
        questoes=questoes_para_aluno
    )


@router.post("/aluno/iniciar")
def iniciar_prova(
    request: IniciarProvaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """▶️ Aluno inicia a prova"""
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == request.prova_aluno_id).first()
    
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova_aluno.prova, current_user)
    
    if prova_aluno.status != StatusProvaAluno.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prova já foi iniciada"
        )
    
    prova_aluno.status = StatusProvaAluno.EM_ANDAMENTO
    prova_aluno.data_inicio = datetime.now(timezone.utc)
    
    db.commit()
    
    return {"message": "Prova iniciada com sucesso", "data_inicio": prova_aluno.data_inicio}


@router.post("/aluno/finalizar", response_model=CorrigirProvaResponse)
async def finalizar_prova(
    request: FinalizarProvaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✅ Aluno finaliza a prova e sistema corrige automaticamente
    
    **Processo:**
    1. Recebe todas as respostas do aluno
    2. Salva as respostas no banco
    3. Corrige automaticamente
    4. Gera análise com IA
    5. Retorna resultado
    """
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == request.prova_aluno_id).first()
    
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova_aluno.prova, current_user)
    
    if prova_aluno.status == StatusProvaAluno.CONCLUIDA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prova já foi finalizada"
        )
    
    prova = prova_aluno.prova
    questoes = {q.id: q for q in prova.questoes}
    
    # Salva respostas e corrige
    respostas_salvas = []
    acertos = 0
    erros = 0
    pontuacao_obtida = 0.0
    
    for resposta_data in request.respostas:
        questao = questoes.get(resposta_data.questao_id)
        
        if not questao:
            continue
        
        # TC-152: questao dissertativa nao tem `resposta_correta` - o `.strip()`
        # em None estourava AttributeError e derrubava a correcao inteira em 500.
        # Sem gabarito nao ha correcao automatica: fica pendente (`esta_correta =
        # None`) ate o professor corrigir em /aluno/{id}/corrigir-questao, mesma
        # regra ja aplicada no fluxo do aluno (student_provas.py).
        if questao.resposta_correta is None:
            esta_correta = None
            pontos = 0.0
        else:
            esta_correta = (
                questao.resposta_correta.strip().lower()
                == resposta_data.resposta_aluno.strip().lower()
            )
            pontos = questao.pontuacao if esta_correta else 0.0

        if esta_correta is True:
            acertos += 1
        elif esta_correta is False:
            erros += 1

        pontuacao_obtida += pontos
        
        # Salva resposta
        resposta = RespostaAluno(
            prova_aluno_id=prova_aluno.id,
            questao_id=questao.id,
            resposta_aluno=resposta_data.resposta_aluno,
            esta_correta=esta_correta,
            pontuacao_obtida=pontos,
            pontuacao_maxima=questao.pontuacao,
            tempo_resposta_segundos=resposta_data.tempo_resposta_segundos
        )
        
        db.add(resposta)
        respostas_salvas.append(resposta)
    
    # TC-152: denominador e so o que foi efetivamente corrigido. Com as
    # discursivas pendentes no divisor, uma prova mista fechava com nota
    # artificialmente baixa (e uma 100% discursiva, sempre 0).
    pendentes = [r for r in respostas_salvas if r.esta_correta is None]
    pontuacao_corrigivel = sum(
        (r.pontuacao_maxima or 0) for r in respostas_salvas if r.esta_correta is not None
    )
    if pontuacao_corrigivel > 0:
        nota_final = (pontuacao_obtida / pontuacao_corrigivel) * 10
        aprovado = nota_final >= prova.nota_minima_aprovacao
    else:
        nota_final = None
        aprovado = None

    # Calcula tempo gasto
    tempo_gasto = int((datetime.now(timezone.utc) - prova_aluno.data_inicio).total_seconds() / 60) if prova_aluno.data_inicio else 0
    
    # Atualiza prova_aluno
    prova_aluno.status = StatusProvaAluno.CONCLUIDA
    prova_aluno.data_conclusao = datetime.now(timezone.utc)
    prova_aluno.pontuacao_obtida = pontuacao_obtida
    prova_aluno.pontuacao_maxima = pontuacao_corrigivel
    prova_aluno.nota_final = nota_final
    prova_aluno.aprovado = aprovado
    prova_aluno.tempo_gasto_minutos = tempo_gasto

    db.commit()

    # Com discursivas pendentes a analise sairia de um retrato pela metade (e
    # custaria tokens a toa). Roda quando a correcao fechar.
    if pendentes:
        db.refresh(prova_aluno)
        return CorrigirProvaResponse(
            prova_aluno_id=prova_aluno.id,
            pontuacao_obtida=pontuacao_obtida,
            pontuacao_maxima=pontuacao_corrigivel,
            nota_final=nota_final,
            aprovado=aprovado,
            acertos=acertos,
            erros=erros,
            percentual_acerto=(
                (acertos / (len(respostas_salvas) - len(pendentes)) * 100)
                if len(respostas_salvas) > len(pendentes) else 0
            ),
            questoes_aguardando_correcao=len(pendentes),
            nota_parcial=True,
            analise_ia={},
            feedback_ia=(
                f"{len(pendentes)} questão(ões) discursiva(s) aguardam correção "
                "do professor. A nota sai depois disso."
            ),
            respostas_detalhadas=[RespostaAlunoResponse.from_orm(r) for r in respostas_salvas]
        )

    # Gera análise com IA
    try:
        aluno = prova_aluno.aluno
        questoes_lista = [
            {
                "numero": q.numero,
                "enunciado": q.enunciado,
                "resposta_correta": q.resposta_correta
            }
            for q in prova.questoes
        ]
        
        respostas_lista = [
            {
                "questao_numero": questoes[r.questao_id].numero,
                "resposta_aluno": r.resposta_aluno,
                "esta_correta": r.esta_correta
            }
            for r in respostas_salvas
        ]
        
        aluno_info = {
            "nome": aluno.name,
            "serie": aluno.grade_level,
            "diagnosticos": aluno.diagnosis or {}
        }
        
        analise = await prova_ai_service.analisar_desempenho(
            questoes=questoes_lista,
            respostas=respostas_lista,
            aluno_info=aluno_info
        )
        
        feedback = await prova_ai_service.gerar_feedback_personalizado(
            questoes=questoes_lista,
            respostas=respostas_lista,
            analise=analise,
            aluno_info=aluno_info
        )
        
        prova_aluno.analise_ia = analise
        prova_aluno.feedback_ia = feedback
        prova_aluno.status = StatusProvaAluno.CORRIGIDA
        prova_aluno.data_correcao = datetime.now(timezone.utc)
        
        db.commit()
        
    except Exception as e:
        print(f"[AVISO] Erro ao gerar analise IA: {e}")
        analise = {}
        feedback = "Prova corrigida com sucesso!"
    
    # Monta resposta
    percentual = (acertos / len(request.respostas) * 100) if request.respostas else 0
    
    db.refresh(prova_aluno)
    
    return CorrigirProvaResponse(
        prova_aluno_id=prova_aluno.id,
        pontuacao_obtida=pontuacao_obtida,
        pontuacao_maxima=pontuacao_corrigivel,
        nota_final=nota_final,
        aprovado=aprovado,
        acertos=acertos,
        erros=erros,
        percentual_acerto=percentual,
        questoes_aguardando_correcao=0,
        nota_parcial=False,
        analise_ia=analise,
        feedback_ia=feedback,
        respostas_detalhadas=[RespostaAlunoResponse.from_orm(r) for r in respostas_salvas]
    )


@router.get("/aluno/{prova_aluno_id}/resultado", response_model=ProvaAlunoResponse)
def obter_resultado(
    prova_aluno_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """📊 Obter resultado da prova do aluno"""
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == prova_aluno_id).first()
    
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    _verificar_acesso_prova(prova_aluno.prova, current_user)
    
    if prova_aluno.status not in [StatusProvaAluno.CONCLUIDA, StatusProvaAluno.CORRIGIDA]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prova ainda não foi finalizada"
        )

    return prova_aluno


# ============================================
# CORRECAO MANUAL DE DISSERTATIVAS (TC-152)
# ============================================

def _carregar_prova_aluno_para_correcao(db: Session, prova_aluno_id: int, current_user: User) -> ProvaAluno:
    """Carrega a prova do aluno validando ownership da prova (anti-IDOR)."""
    prova_aluno = db.query(ProvaAluno).filter(ProvaAluno.id == prova_aluno_id).first()
    if not prova_aluno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    _verificar_acesso_prova(prova_aluno.prova, current_user)
    return prova_aluno


@router.get("/aluno/{prova_aluno_id}/questoes-pendentes")
def listar_questoes_pendentes(
    prova_aluno_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    📝 Lista as questoes discursivas desta prova que aguardam correcao humana.

    Sao as respostas com `esta_correta = None` - questoes sem gabarito, que a
    correcao automatica nao tem como avaliar. Enquanto existirem, a prova fica
    em CONCLUIDA e a nota do aluno e parcial (TC-152).
    """
    prova_aluno = _carregar_prova_aluno_para_correcao(db, prova_aluno_id, current_user)

    pendentes = db.query(RespostaAluno).filter(
        RespostaAluno.prova_aluno_id == prova_aluno_id,
        RespostaAluno.esta_correta.is_(None)
    ).all()

    questoes = {q.id: q for q in prova_aluno.prova.questoes}

    return {
        "prova_aluno_id": prova_aluno_id,
        "aluno_id": prova_aluno.aluno_id,
        "status": prova_aluno.status.value if prova_aluno.status else None,
        "total_pendentes": len(pendentes),
        "questoes": [
            {
                "resposta_id": r.id,
                "questao_id": r.questao_id,
                "numero": questoes[r.questao_id].numero if r.questao_id in questoes else None,
                "enunciado": questoes[r.questao_id].enunciado if r.questao_id in questoes else None,
                "criterios_avaliacao": (
                    questoes[r.questao_id].criterios_avaliacao if r.questao_id in questoes else None
                ),
                "resposta_aluno": r.resposta_aluno,
                "pontuacao_maxima": r.pontuacao_maxima,
            }
            for r in pendentes
        ]
    }


@router.post("/aluno/{prova_aluno_id}/corrigir-questao", response_model=CorrigirQuestaoResponse)
def corrigir_questao_dissertativa(
    prova_aluno_id: int,
    request: CorrigirQuestaoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ✍️ Professor corrige UMA questao discursiva e a nota e recalculada.

    Era a peca que faltava no TC-152: `/responder` deixava a dissertativa com
    `esta_correta = None` e nada no backend corrigia depois - prova discursiva
    ficava sem nota para sempre. Aqui o professor atribui os pontos; quando a
    ultima pendencia cai, a prova vira CORRIGIDA e ganha nota final.

    `esta_correta` e derivado da pontuacao (>= metade do valor da questao conta
    como acerto), so para alimentar as estatisticas que ja existem - a nota vem
    da pontuacao, nao desse booleano.
    """
    prova_aluno = _carregar_prova_aluno_para_correcao(db, prova_aluno_id, current_user)

    resposta = db.query(RespostaAluno).filter(
        RespostaAluno.id == request.resposta_id,
        RespostaAluno.prova_aluno_id == prova_aluno_id
    ).first()
    if not resposta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resposta não encontrada nesta prova"
        )

    maxima = resposta.pontuacao_maxima or 0
    if request.pontuacao > maxima:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pontuação acima do máximo da questão ({maxima})"
        )

    resposta.pontuacao_obtida = request.pontuacao
    resposta.esta_correta = request.pontuacao >= (maxima / 2) if maxima > 0 else False
    if request.feedback is not None:
        resposta.feedback = request.feedback

    db.flush()

    # Recalcula os totais da prova inteira a partir das respostas ja corrigidas.
    respostas = db.query(RespostaAluno).filter(
        RespostaAluno.prova_aluno_id == prova_aluno_id
    ).all()
    pendentes = [r for r in respostas if r.esta_correta is None]
    pontuacao_obtida = sum((r.pontuacao_obtida or 0) for r in respostas)
    pontuacao_corrigivel = sum(
        (r.pontuacao_maxima or 0) for r in respostas if r.esta_correta is not None
    )

    nota_minima = prova_aluno.prova.nota_minima_aprovacao or 6.0
    if pontuacao_corrigivel > 0:
        nota_final = (pontuacao_obtida / pontuacao_corrigivel) * 10
    else:
        nota_final = None

    prova_aluno.pontuacao_obtida = pontuacao_obtida
    prova_aluno.pontuacao_maxima = pontuacao_corrigivel
    prova_aluno.nota_final = nota_final

    if pendentes:
        # Ainda incompleta: aprovacao so quando nao houver mais pontos em aberto.
        prova_aluno.aprovado = None
    else:
        prova_aluno.aprovado = (nota_final or 0) >= nota_minima
        prova_aluno.status = StatusProvaAluno.CORRIGIDA
        prova_aluno.data_correcao = datetime.now(timezone.utc)

    db.commit()
    db.refresh(prova_aluno)
    db.refresh(resposta)

    return CorrigirQuestaoResponse(
        resposta_id=resposta.id,
        pontuacao_obtida=resposta.pontuacao_obtida or 0,
        pontuacao_maxima=maxima,
        esta_correta=resposta.esta_correta,
        questoes_aguardando_correcao=len(pendentes),
        nota_final=round(nota_final, 2) if nota_final is not None else None,
        aprovado=prova_aluno.aprovado,
        status=prova_aluno.status,
        correcao_finalizada=not pendentes
    )
