from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.evaluation_question import EvaluationQuestion
from backend.app.models.knowledge_base import KnowledgeBase
from backend.app.models.evaluation_set import EvaluationSet
from backend.app.schemas.evaluation import (
    EvaluationQuestionCreate,
    EvaluationQuestionRead,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSetCreate,
    EvaluationSetRead,
)
from backend.app.services.evaluator import run_evaluation_set

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/sets", response_model=list[EvaluationSetRead])
def list_evaluation_sets(db: Session = Depends(get_db)) -> list[EvaluationSet]:
    statement = select(EvaluationSet).order_by(EvaluationSet.id.asc())
    return db.scalars(statement).all()


@router.post("/sets", response_model=EvaluationSetRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_set(
    payload: EvaluationSetCreate,
    db: Session = Depends(get_db),
) -> EvaluationSet:
    existing = db.scalar(select(EvaluationSet).where(EvaluationSet.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An evaluation set with this name already exists.",
        )

    evaluation_set = EvaluationSet(
        name=payload.name,
        description=payload.description,
    )
    db.add(evaluation_set)
    db.commit()
    db.refresh(evaluation_set)
    return evaluation_set


@router.get("/sets/{set_id}/questions", response_model=list[EvaluationQuestionRead])
def list_evaluation_questions(
    set_id: int,
    db: Session = Depends(get_db),
) -> list[EvaluationQuestion]:
    evaluation_set = db.get(EvaluationSet, set_id)
    if not evaluation_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation set not found.",
        )

    statement = (
        select(EvaluationQuestion)
        .where(EvaluationQuestion.set_id == set_id)
        .order_by(EvaluationQuestion.id.asc())
    )
    return db.scalars(statement).all()


@router.post("/sets/{set_id}/questions", response_model=EvaluationQuestionRead, status_code=status.HTTP_201_CREATED)
def create_evaluation_question(
    set_id: int,
    payload: EvaluationQuestionCreate,
    db: Session = Depends(get_db),
) -> EvaluationQuestion:
    evaluation_set = db.get(EvaluationSet, set_id)
    if not evaluation_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation set not found.",
        )

    evaluation_question = EvaluationQuestion(
        set_id=set_id,
        question=payload.question,
        expected_answer=payload.expected_answer,
        document_scope=payload.document_scope,
    )
    db.add(evaluation_question)
    db.commit()
    db.refresh(evaluation_question)
    return evaluation_question


@router.post("/run", response_model=EvaluationRunResponse)
def run_evaluation(
    payload: EvaluationRunRequest,
    db: Session = Depends(get_db),
) -> EvaluationRunResponse:
    evaluation_set = db.get(EvaluationSet, payload.set_id)
    if not evaluation_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation set not found.",
        )

    knowledge_base = db.get(KnowledgeBase, payload.knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    questions = db.scalars(
        select(EvaluationQuestion)
        .where(EvaluationQuestion.set_id == payload.set_id)
        .order_by(EvaluationQuestion.id.asc())
    ).all()

    summary = run_evaluation_set(
        db=db,
        questions=questions,
        knowledge_base_id=payload.knowledge_base_id,
        top_k=payload.top_k,
    )

    return EvaluationRunResponse(
        set_id=payload.set_id,
        knowledge_base_id=payload.knowledge_base_id,
        result_count=len(summary.results),
        average_score=summary.average_score,
        results=summary.results,
    )
