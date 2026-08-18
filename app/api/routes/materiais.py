"""
Rotas para Materiais de Estudo (Biblioteca) - conteudo no banco + agenda.

O conteudo gerado pela IA fica em `Material.conteudo` desde 18/08/2026; o
diretorio storage/materiais/ so e lido como fallback de material antigo.
Ver app/services/material_conteudo.py para o porque.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from typing import List
from datetime import time as dt_time
import time

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.student import Student
from app.models.material import Material, MaterialAluno, TipoMaterial, StatusMaterial
from app.models.agenda import AgendaProfessor, TipoEvento, StatusEvento, Recorrencia
from app.schemas.material import (
    MaterialCreate, MaterialResponse, MaterialListResponse,
    MaterialAlunoResponse, AnotacaoRequest, FavoritoRequest,
    AtribuirAlunosRequest
)
from app.api.dependencies import get_current_active_user
from app.core.tenant import enforce_limite_materiais
from app.core.pagination import PaginationParams, build_page
from app.services import material_conteudo
from app.services.material_service import material_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/materiais", tags=["Materiais de Estudo"])

# Mesmos campos que app/api/routes/materiais_adaptados.py le do diagnostico do
# aluno (Student.diagnosis, coluna JSON -> dict em Python).
_CAMPOS_DIAGNOSTICO = [
    ("tea", "TEA"),
    ("tdah", "TDAH"),
    ("dislexia", "dislexia"),
    ("discalculia", "discalculia"),
    ("disgrafia", "disgrafia"),
    ("deficiencia_intelectual", "deficiência intelectual"),
    ("superdotacao", "superdotação"),
]


def _rotular_diagnostico(diagnostico: dict) -> str:
    """Extrai um rotulo curto e legivel (string) do diagnostico do aluno, para
    entrar no prompt de geracao como texto.

    2026-08-15: material_service.gerar_material_*(adaptacoes=[...]) espera uma
    lista de STRINGS (faz ', '.join(adaptacoes) no prompt). O chamador
    montava `adaptacoes` com o dict `diagnosis` inteiro e ainda tentava
    `set(...)` em cima disso -> "unhashable type: 'dict'", material sempre
    caia em StatusMaterial.ERRO antes de qualquer chamada a IA.
    """
    if not isinstance(diagnostico, dict):
        return ""
    rotulos = [nome for campo, nome in _CAMPOS_DIAGNOSTICO if diagnostico.get(campo)]
    return ", ".join(rotulos)


def gerar_material_background(material_id: int):
    """
    Gera o conteúdo do material em background e grava na PROPRIA LINHA.
    ESTRATÉGIA: busca dados (transação curta) -> gera sem banco aberto ->
    UPDATE curto com o conteúdo + status.
    """
    db_session = SessionLocal()
    
    try:
        # ETAPA 1: BUSCAR DADOS (transação rápida)
        material = db_session.query(Material).filter(Material.id == material_id).first()
        if not material:
            db_session.close()
            return
        
        # Guardar dados necessários
        material_titulo = material.titulo
        material_prompt = material.conteudo_prompt
        material_tipo = material.tipo
        material_materia = material.materia
        material_serie = material.serie_nivel or "Geral"
        
        # Buscar adaptações
        alunos_ids = [ma.aluno_id for ma in material.materiais_alunos]
        alunos = db_session.query(Student).filter(Student.id.in_(alunos_ids)).all()
        # 2026-08-15: era `list(set([a.diagnosis for ...]))` — a.diagnosis e um
        # dict (coluna JSON), e dict nao e hashable. set() estourava
        # "unhashable type: 'dict'" ANTES de chamar a IA, pra qualquer aluno
        # com diagnostico preenchido. Agora extrai rotulos (strings) e so
        # depois deduplica.
        adaptacoes = sorted(set(
            filter(None, (_rotular_diagnostico(a.diagnosis) for a in alunos if a.diagnosis))
        ))
        
        # FECHAR SESSÃO - vamos gerar conteúdo SEM banco aberto
        db_session.close()
        
        print(f"📝 Gerando conteúdo para material {material_id}...")
        
        # ETAPA 2: GERAR CONTEÚDO (SEM BANCO)
        #
        # 2026-08-18: o conteudo era gravado em disco AQUI (storage_service) e
        # a linha guardava so o caminho. O disco do Railway e efemero -> o
        # arquivo sumia no redeploy seguinte e o material "desaparecia" da
        # biblioteca. Agora o conteudo fica em memoria ate a ETAPA 3, que o
        # grava na propria linha. Ver app/services/material_conteudo.py.
        conteudo_gerado = None
        conteudo_erro = None
        
        if material_tipo == TipoMaterial.VISUAL:
            resultado = material_service.gerar_material_visual(
                titulo=material_titulo,
                conteudo=material_prompt,
                materia=material_materia,
                serie=material_serie,
                adaptacoes=adaptacoes
            )
            
            if resultado["success"]:
                conteudo_gerado = resultado["html"]
            else:
                conteudo_erro = resultado.get("error")
        
        elif material_tipo == TipoMaterial.MAPA_MENTAL:
            resultado = material_service.gerar_mapa_mental(
                titulo=material_titulo,
                conteudo=material_prompt,
                materia=material_materia,
                serie=material_serie,
                adaptacoes=adaptacoes
            )
            
            if resultado["success"]:
                conteudo_gerado = resultado["json"]
            else:
                conteudo_erro = resultado.get("error")
        
        elif material_tipo in (
            TipoMaterial.RESUMO,
            TipoMaterial.TEXTO_SIMPLIFICADO,
            TipoMaterial.ROTEIRO_ESTUDO,
            TipoMaterial.ATIVIDADES,
        ):
            resultado = material_service.gerar_material_texto(
                formato=material_tipo.value,
                titulo=material_titulo,
                conteudo=material_prompt,
                materia=material_materia,
                serie=material_serie,
                adaptacoes=adaptacoes
            )
            if resultado["success"]:
                conteudo_gerado = resultado["html"]
            else:
                conteudo_erro = resultado.get("error")
        
        else:
            # Tipo novo no enum sem tratamento aqui: falha explicita em vez de
            # ficar em GERANDO para sempre (era o comportamento anterior).
            conteudo_erro = f"Tipo de material '{material_tipo}' nao tem gerador implementado."
        
        print(f"✨ Conteúdo gerado! Atualizando banco...")
        
        # ETAPA 3: ATUALIZAR BANCO (transação SUPER RÁPIDA - só UPDATE status)
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Criar nova sessão apenas para UPDATE
                db_session = SessionLocal()
                
                # Buscar material novamente
                material = db_session.query(Material).filter(Material.id == material_id).first()
                
                if not material:
                    db_session.close()
                    return
                
                # UPDATE: conteudo vai para a propria linha (MEDIUMTEXT).
                if conteudo_gerado is not None:
                    material_conteudo.escrever(material, conteudo_gerado)
                    material.status = StatusMaterial.DISPONIVEL
                else:
                    material.status = StatusMaterial.ERRO
                    material.metadados = {"erro": conteudo_erro or "Erro desconhecido"}
                
                # COMMIT IMEDIATO
                db_session.commit()
                db_session.close()
                
                print(f"✅ Material {material_id} salvo com sucesso!")
                return
            
            except OperationalError as e:
                retry_count += 1
                db_session.rollback()
                db_session.close()
                
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    print(f"⚠️ Erro MySQL. Retry {retry_count}/{max_retries} em {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ Material {material_id} falhou após {max_retries} tentativas: {str(e)}")
                    
                    # Marcar como erro
                    try:
                        db_session = SessionLocal()
                        material = db_session.query(Material).filter(Material.id == material_id).first()
                        if material:
                            material.status = StatusMaterial.ERRO
                            material.metadados = {"erro": f"Timeout MySQL após {max_retries} tentativas"}
                            db_session.commit()
                        db_session.close()
                    except:
                        pass
                    return
    
    except Exception as e:
        print(f"❌ Erro ao gerar material {material_id}: {str(e)}")
        try:
            db_session = SessionLocal()
            material = db_session.query(Material).filter(Material.id == material_id).first()
            if material:
                material.status = StatusMaterial.ERRO
                material.metadados = {"erro": str(e)}
                db_session.commit()
            db_session.close()
        except:
            pass


@router.post("/", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def criar_material(
    material_data: MaterialCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cria um novo material de estudo e inicia geração em background.
    
    Se data_aplicacao for fornecida e criar_evento_agenda=True,
    um evento será criado automaticamente na agenda do professor.
    """
    # Limite de plano (soft): bloqueia se a escola atingiu o limite mensal de materiais.
    # Nao afeta usuarios sem escola/assinatura ativa (grandfather).
    enforce_limite_materiais(db, current_user)

    # Verificar se alunos pertencem ao usuário
    alunos = db.query(Student).filter(
        Student.id.in_(material_data.aluno_ids),
        Student.created_by_user_id == current_user.id
    ).all()
    
    if len(alunos) != len(material_data.aluno_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Um ou mais alunos não encontrados ou não pertencem a você"
        )
    
    # Criar material
    novo_material = Material(
        titulo=material_data.titulo,
        descricao=material_data.descricao,
        conteudo_prompt=material_data.conteudo_prompt,
        tipo=material_data.tipo,
        materia=material_data.materia,
        serie_nivel=material_data.serie_nivel,
        tags=material_data.tags or [],
        status=StatusMaterial.GERANDO,
        criado_por_id=current_user.id
    )
    
    db.add(novo_material)
    db.commit()
    db.refresh(novo_material)
    
    # Associar aos alunos
    for aluno in alunos:
        material_aluno = MaterialAluno(
            material_id=novo_material.id,
            aluno_id=aluno.id
        )
        db.add(material_aluno)
    
    db.commit()
    db.refresh(novo_material)
    
    # ============================================
    # NOVO: Criar evento na agenda se solicitado
    # ============================================
    if material_data.criar_evento_agenda and material_data.data_aplicacao:
        try:
            # Para cada aluno, criar evento na agenda
            hora_inicio = material_data.hora_aplicacao or dt_time(8, 0)  # Default 08:00
            
            for aluno in alunos:
                evento = AgendaProfessor(
                    professor_id=current_user.id,
                    titulo=f"📚 {material_data.titulo}",
                    descricao=f"Aplicação de material: {material_data.titulo}\nMatéria: {material_data.materia}",
                    tipo=TipoEvento.AULA,
                    student_id=aluno.id,
                    data=material_data.data_aplicacao,
                    hora_inicio=hora_inicio,
                    duracao_minutos=50,
                    cor="#10B981",  # Verde para materiais
                    recorrencia=Recorrencia.UNICO,
                    status=StatusEvento.AGENDADO,
                    notas_privadas=f"Material ID: {novo_material.id}"
                )
                db.add(evento)
            
            db.commit()
            print(f"📅 Evento(s) criado(s) na agenda para {len(alunos)} aluno(s)")
        except Exception as e:
            print(f"⚠️ Erro ao criar evento na agenda: {e}")
            # Não falha a criação do material se erro na agenda
    
    # Agendar geração em background
    background_tasks.add_task(gerar_material_background, novo_material.id)
    
    return novo_material


@router.get("/")
async def listar_materiais(
    tipo: TipoMaterial | None = Query(
        None, description="Filtra por tipo (visual, mapa_mental, resumo, ...)"
    ),
    materia: str | None = Query(None, description="Nome da materia"),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista materiais criados pelo professor com paginacao.
    
    Query params:
    - page: pagina (default 1)
    - size: itens por pagina (default 20, max 100)
    - tipo: 'visual' ou 'mapa_mental' (opcional)
    - materia: nome da materia (opcional)
    
    Retorna:
    {
        "items": [...materiais...],
        "meta": {"page": 1, "size": 20, "total": 150, "total_pages": 8, ...}
    }
    
    IMPORTANTE: Endpoint mudou para formato paginado. Frontend antigo que espera
    array puro precisa acessar response.items ao inves de response direto.
    """
    # 2026-08-11: antes era `Material.tipo == tipo.upper()`, comparando com
    # "VISUAL" enquanto TipoMaterial usa valores minusculos ("visual"). O
    # SQLAlchemy tentava TipoMaterial("VISUAL") e levantava LookupError -> 500.
    # Na pratica, clicar nas abas "Visuais" / "Mapas Mentais" quebrava a
    # listagem. Tipando o parametro como o proprio Enum, o FastAPI valida e
    # converte antes de chegar aqui (e o Swagger ganha um dropdown).
    filtros = [Material.criado_por_id == current_user.id]
    if tipo:
        filtros.append(Material.tipo == tipo)
    if materia:
        filtros.append(Material.materia == materia)

    # ------------------------------------------------------------------
    # 2026-08-18 - SELECT ENXUTO + FIM DO N+1
    # ------------------------------------------------------------------
    # Duas coisas quebravam esta rota conforme a biblioteca crescia:
    #
    # 1. `db.query(Material)` traz TODAS as colunas - incluindo `conteudo_prompt`,
    #    `metadados`, `historico_versoes` e (desde hoje) o `conteudo` do
    #    material. Com ORDER BY em cima disso o MySQL faz filesort carregando
    #    linhas enormes e responde "1038 Out of sort memory": a tela mostrava
    #    "Nao foi possivel carregar os materiais" logo ao abrir.
    #
    # 2. `len(material.materiais_alunos)` disparava um SELECT por material
    #    (o comentario antigo prometia eager-load, mas nao havia nenhum).
    #    Com size=100, eram 100 queries extras por abertura de tela - parte
    #    do "monte de SQL" no log do Railway.
    #
    # Agora: uma query de COUNT, uma de pagina (so as colunas da lista) e uma
    # de contagem de alunos agrupada. Tres queries, independente do tamanho.
    total = db.query(func.count(Material.id)).filter(*filtros).scalar() or 0

    materiais = (
        db.query(
            Material.id,
            Material.titulo,
            Material.descricao,
            Material.tipo,
            Material.materia,
            Material.serie_nivel,
            Material.status,
            Material.criado_em,
        )
        .filter(*filtros)
        .order_by(Material.criado_em.desc(), Material.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    ids = [m.id for m in materiais]
    alunos_por_material = {}
    if ids:
        alunos_por_material = dict(
            db.query(MaterialAluno.material_id, func.count(MaterialAluno.id))
            .filter(MaterialAluno.material_id.in_(ids))
            .group_by(MaterialAluno.material_id)
            .all()
        )

    items = [
        {
            "id": m.id,
            "titulo": m.titulo,
            "descricao": m.descricao,
            "tipo": m.tipo,
            "materia": m.materia,
            "serie_nivel": m.serie_nivel,
            "status": m.status,
            "criado_em": m.criado_em,
            "total_alunos": alunos_por_material.get(m.id, 0),
        }
        for m in materiais
    ]

    return build_page(items=items, total=total, pagination=pagination)


@router.get("/{material_id}", response_model=MaterialResponse)
async def obter_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obter detalhes de um material específico"""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()
    
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    return material


@router.get("/{material_id}/conteudo")
async def obter_conteudo_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obter o conteúdo do material.

    Vem da propria linha (Material.conteudo); material antigo cai no arquivo em
    disco, quando ele ainda existir. Retorna HTML ou JSON dependendo do tipo.
    """
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()
    
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    if material.status != StatusMaterial.DISPONIVEL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Material não está disponível. Status: {material.status}"
        )
    
    # Banco primeiro, disco so como fallback de material antigo
    # (ver app/services/material_conteudo.py). Mapa mental e JSON; o resto HTML.
    conteudo = material_conteudo.ler(material)
    if not conteudo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "O conteúdo deste material não está mais disponível. "
                "Use 'Regenerar' para criá-lo novamente."
            )
        )

    tipo_conteudo = "json" if material_conteudo.e_mapa_mental(material) else "html"
    return {"tipo": tipo_conteudo, "conteudo": conteudo}


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deletar_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deletar um material (a linha leva junto o conteudo; o arquivo legado em
    disco, se existir, tambem e removido)."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()
    
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    # Deletar arquivo do storage
    storage_service.deletar(material_id)
    
    # Deletar do banco
    db.delete(material)
    db.commit()
    
    return None


@router.get("/{material_id}/alunos", response_model=List[MaterialAlunoResponse])
async def listar_alunos_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Listar todos os alunos que têm acesso a este material"""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()
    
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )
    
    return material.materiais_alunos


@router.post("/{material_id}/atribuir", response_model=List[MaterialAlunoResponse])
async def atribuir_material_alunos(
    material_id: int,
    payload: AtribuirAlunosRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Atribui um material JA GERADO a alunos adicionais — reaproveita a mesma
    geracao (mesmo arquivo no storage) em vez de gerar de novo para cada aluno.

    2026-08-15: a UI ja prometia isso ("materiais reutilizaveis que voce pode
    atribuir a varios alunos"), mas o endpoint nunca existiu — pendencia
    documentada em docs/CORRECOES-2026-08-11.md item 4.
    """
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )

    # Mesma checagem de posse usada em criar_material — evita atribuir a
    # aluno de outro professor (IDOR).
    alunos = db.query(Student).filter(
        Student.id.in_(payload.aluno_ids),
        Student.created_by_user_id == current_user.id
    ).all()
    if len(alunos) != len(payload.aluno_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Um ou mais alunos não encontrados ou não pertencem a você"
        )

    # Ignora quem ja tem acesso — evita duplicar a linha em materiais_alunos
    # (nao ha UniqueConstraint na tabela; a checagem aqui e a unica garantia).
    ja_atribuidos = {ma.aluno_id for ma in material.materiais_alunos}
    novos = [a for a in alunos if a.id not in ja_atribuidos]

    for aluno in novos:
        db.add(MaterialAluno(material_id=material.id, aluno_id=aluno.id))

    if novos:
        db.commit()
        db.refresh(material)

    return material.materiais_alunos


@router.post("/{material_id}/regenerar", response_model=MaterialResponse)
async def regenerar_material(
    material_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Regenera o conteudo do material como uma NOVA versao.

    A versao atual e arquivada no historico (preservando o arquivo anterior) e o
    conteudo e gerado novamente em background. Nao consome cota de plano (e revisao).
    """
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )

    if material.status == StatusMaterial.GERANDO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O material ainda está sendo gerado. Aguarde a conclusão."
        )

    # Arquiva a versao atual. O conteudo vai para `conteudo_versoes` (banco);
    # `historico_versoes` fica so com metadados, que e o que as telas leem.
    versao_atual = material.versao or 1
    arquivou = material_conteudo.arquivar_versao(material, versao_atual)

    historico = list(material.historico_versoes or [])
    if arquivou:
        ref_data = material.atualizado_em or material.criado_em
        historico.append({
            "versao": versao_atual,
            "conteudo_prompt": material.conteudo_prompt,
            "criado_em": ref_data.isoformat() if ref_data else None,
        })

    material.historico_versoes = historico
    material.versao = versao_atual + 1
    material.status = StatusMaterial.GERANDO
    db.commit()
    db.refresh(material)

    # Gera o novo conteudo em background (sobrescreve o arquivo canonico)
    background_tasks.add_task(gerar_material_background, material.id)

    return material


@router.get("/{material_id}/versoes")
async def listar_versoes_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lista o historico de versoes do material (versao atual + versoes anteriores arquivadas)."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )

    versoes_anteriores = list(material.historico_versoes or [])
    return {
        "material_id": material.id,
        "versao_atual": material.versao or 1,
        "status_atual": material.status,
        "total_versoes": len(versoes_anteriores) + 1,
        "versoes_anteriores": versoes_anteriores,
    }


@router.get("/{material_id}/versao/{versao}/conteudo")
async def obter_conteudo_versao(
    material_id: int,
    versao: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Obtem o conteudo de uma versao especifica (atual ou arquivada) do material."""
    material = db.query(Material).filter(
        Material.id == material_id,
        Material.criado_por_id == current_user.id
    ).first()

    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material não encontrado"
        )

    ext = "json" if material_conteudo.e_mapa_mental(material) else "html"

    if versao == (material.versao or 1):
        conteudo = material_conteudo.ler(material)
    else:
        conteudo = material_conteudo.ler_versao(material, versao)

    if conteudo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Versão não encontrada"
        )

    return {
        "tipo": "json" if ext == "json" else "html",
        "versao": versao,
        "conteudo": conteudo,
    }
