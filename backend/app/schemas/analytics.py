from pydantic import BaseModel


class TopQuestion(BaseModel):
    question: str
    count: int


class AnalyticsResponse(BaseModel):
    document_count: int
    chunk_count: int
    conversation_count: int
    average_latency_ms: float | None
    feedback_count: int
    useful_feedback_ratio: float | None
    top_questions: list[TopQuestion]

