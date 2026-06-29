from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.question import QuestionSet, Question, DifficultyLevel
from app.models.student import Student
from app.models.application import Application, ApplicationStatus
from app.services.ai_service import AIService
from app.api.dependencies import get_current_active_user
from app.core.tenant import tenant_scoped_query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/exam", tags=["Exam Management"])

# Schemas
class ExamCreateRequest(BaseModel):
    """Request para criar uma prova com IA"""
    title: str = Field(..., description="Título da prova")
    content: str = Field(..., description="Conteúdo/tema que será usado como base (prompt para IA)")
    subject: str = Field(..., description="Disciplina (Matemática, Português, etc)")
    grade_level: str = Field(..., description="Ano escolar")
    num_questions: int = Field(..., ge=1, le=50, description="Número de questões (1-50)")
    difficulty_level: int = Field(default=2, ge=1, le=4, description="Nível de dificuldade (1-4)")
    adaptations: List[str] = Field(default=[], description="Adaptações especiais")

class ExamAssignRequest(BaseModel):
    """Request para associar prova a aluno"""
    exam_id: int = Field(..., description="ID da prova")
    student_id: int = Field(..., description="ID do aluno")
    time_limit_minutes: int = Field(default=60, description="Tempo limite em minutos")

class ExamResponse(BaseModel):
    """Response com dados da prova"""
    id: int
    title: str
    subject: str
    grade_level: str
    num_questions: int
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/create", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam_with_ai(
    request: ExamCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    🎓 CRIAR PROVA COM IA
    
    O administrador indica:
    - Título da prova
    - Conteúdo/tema (usado como prompt)
    - Disciplina e ano
    - Número de questões
    
    A IA vai gerar automaticamente todas as questões!
    """
    
    try:
        # 1. Gerar questões com IA
        ai_service = AIService()
        
        print(f"Gerando {request.num_questions} questões com IA...")
        questions_data = ai_service.generate_questions(
            content=request.content,
            subject=request.subject,
            grade_level=request.grade_level,
            difficulty_level=request.difficulty_level,
            quantity=request.num_questions,
            adaptations=request.adaptations
        )
        
        if not questions_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="IA não conseguiu gerar as questões"
            )
        
        # 2. Criar QuestionSet (conjunto de questões / prova)
        question_set = QuestionSet(
            user_id=current_user.id,
            title=request.title,
            description=f"Prova gerada por IA baseada em: {request.content[:100]}...",
            subject=request.subject,
            grade_level=request.grade_level,
            raw_content=request.content,
            config={
                "num_questions": request.num_questions,
                "difficulty_level": request.difficulty_level,
                "adaptations": request.adaptations,
                "generated_by_ai": True
            },
            tags=[request.subject, request.grade_level, "gerado_por_ia"]
        )
        
        db.add(question_set)
        db.flush()  # Para obter o ID
        
        # 3. Salvar todas as questões
        for idx, q_data in enumerate(questions_data, start=1):
            question = Question(
                question_set_id=question_set.id,
                difficulty_level=DifficultyLevel(request.difficulty_level),
                question_text=q_data.get("question_text"),
                option_a=q_data.get("option_a"),
                option_b=q_data.get("option_b"),
                option_c=q_data.get("option_c"),
                option_d=q_data.get("option_d"),
                correct_answer=q_data.get("correct_answer"),
                explanation=q_data.get("explanation"),
                skill=q_data.get("skill"),
                order_number=idx
            )
            db.add(question)
        
        db.commit()
        db.refresh(question_set)
        
        return ExamResponse(
            id=question_set.id,
            title=question_set.title,
            subject=question_set.subject,
            grade_level=question_set.grade_level,
            num_questions=len(questions_data),
            created_at=question_set.created_at
        )
        
    except Exception as e:
        db.rollback()
        print(f"Erro ao criar prova: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar prova com IA: {str(e)}"
        )

@router.post("/assign", status_code=status.HTTP_201_CREATED)
async def assign_exam_to_student(
    request: ExamAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    📝 ASSOCIAR PROVA A ALUNO
    
    O administrador associa uma prova criada a um aluno específico.
    O aluno poderá então fazer a prova.
    """
    
    # Verificar se prova existe
    question_set = tenant_scoped_query(db, QuestionSet, current_user).filter(QuestionSet.id == request.exam_id).first()
    if not question_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prova não encontrada"
        )
    
    # Verificar se aluno existe
    student = tenant_scoped_query(db, Student, current_user).filter(Student.id == request.student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Verificar se já existe aplicação pendente/em progresso
    existing = db.query(Application).filter(
        Application.question_set_id == request.exam_id,
        Application.student_id == request.student_id,
        Application.status.in_([ApplicationStatus.PENDING, ApplicationStatus.IN_PROGRESS])
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este aluno já tem esta prova associada e não finalizada"
        )
    
    # Criar aplicação (associação prova -> aluno)
    application = Application(
        question_set_id=request.exam_id,
        student_id=request.student_id,
        applied_by_user_id=current_user.id,
        applied_date=datetime.utcnow(),
        time_limit_minutes=request.time_limit_minutes,
        status=ApplicationStatus.PENDING
    )
    
    db.add(application)
    db.commit()
    db.refresh(application)
    
    return {
        "message": "Prova associada ao aluno com sucesso!",
        "application_id": application.id,
        "student": student.name,
        "exam": question_set.title,
        "status": "pending"
    }

@router.get("/list", response_model=List[ExamResponse])
async def list_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    📋 LISTAR TODAS AS PROVAS
    
    Lista todas as provas criadas (para o administrador escolher qual associar)
    """
    
    question_sets = tenant_scoped_query(db, QuestionSet, current_user).order_by(QuestionSet.created_at.desc()).all()
    
    return [
        ExamResponse(
            id=qs.id,
            title=qs.title,
            subject=qs.subject,
            grade_level=qs.grade_level,
            num_questions=len(qs.questions),
            created_at=qs.created_at
        )
        for qs in question_sets
    ]

@router.get("/student/{student_id}/available")
async def get_student_available_exams(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    📚 PROVAS DISPONÍVEIS PARA O ALUNO
    
    Lista todas as provas que foram associadas a um aluno
    """
    
    # Verificar se aluno existe
    student = tenant_scoped_query(db, Student, current_user).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado"
        )
    
    # Buscar aplicações do aluno
    applications = db.query(Application).filter(
        Application.student_id == student_id
    ).order_by(Application.applied_date.desc()).all()
    
    result = []
    for app in applications:
        result.append({
            "application_id": app.id,
            "exam_id": app.question_set_id,
            "exam_title": app.question_set.title,
            "subject": app.question_set.subject,
            "num_questions": len(app.question_set.questions),
            "status": app.status.value,
            "time_limit_minutes": app.time_limit_minutes,
            "applied_date": app.applied_date,
            "started_at": app.started_at,
            "completed_at": app.completed_at
        })
    
    return {
        "student": student.name,
        "total_exams": len(result),
        "exams": result
    }
