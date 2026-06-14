from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.chunk import Chunk
from backend.app.models.conversation import Conversation
from backend.app.models.conversation_message import ConversationMessage
from backend.app.models.document import Document
from backend.app.models.feedback import Feedback
from backend.app.schemas.analytics import AnalyticsResponse, TopQuestion

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
def get_analytics(db: Session = Depends(get_db)) -> AnalyticsResponse:
    document_count = db.scalar(select(func.count()).select_from(Document)) or 0
    chunk_count = db.scalar(select(func.count()).select_from(Chunk)) or 0
    conversation_count = db.scalar(select(func.count()).select_from(Conversation)) or 0
    feedback_count = db.scalar(select(func.count()).select_from(Feedback)) or 0
    average_latency_ms = db.scalar(select(func.avg(Conversation.latency_ms)))

    useful_feedback_count = db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.rating == "useful")
    ) or 0

    useful_feedback_ratio: float | None = None
    if feedback_count:
        useful_feedback_ratio = useful_feedback_count / feedback_count

    top_question_rows = db.execute(
        select(ConversationMessage.content, func.count().label("count"))
        .where(ConversationMessage.role == "user")
        .group_by(ConversationMessage.content)
        .having(func.length(func.trim(ConversationMessage.content)) > 0)
        .order_by(func.count().desc(), ConversationMessage.content.asc())
        .limit(5)
    ).all()

    top_questions = [
        TopQuestion(question=question, count=count)
        for question, count in top_question_rows
    ]

    return AnalyticsResponse(
        document_count=document_count,
        chunk_count=chunk_count,
        conversation_count=conversation_count,
        average_latency_ms=float(average_latency_ms) if average_latency_ms is not None else None,
        feedback_count=feedback_count,
        useful_feedback_ratio=useful_feedback_ratio,
        top_questions=top_questions,
    )
