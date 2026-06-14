from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvaluationSetCreate(BaseModel):
    name: str
    description: str | None = None


class EvaluationSetRead(BaseModel):
    id: int
    name: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)


class EvaluationQuestionCreate(BaseModel):
    question: str
    expected_answer: str
    document_scope: str | None = None


class EvaluationQuestionRead(BaseModel):
    id: int
    set_id: int
    question: str
    expected_answer: str
    document_scope: str | None

    model_config = ConfigDict(from_attributes=True)


class EvaluationResultRead(BaseModel):
    id: int
    question_id: int
    generated_answer: str
    score: float
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunRequest(BaseModel):
    set_id: int
    knowledge_base_id: int
    top_k: int = 5


class EvaluationRunResponse(BaseModel):
    set_id: int
    knowledge_base_id: int
    result_count: int
    average_score: float | None
    results: list[EvaluationResultRead]
