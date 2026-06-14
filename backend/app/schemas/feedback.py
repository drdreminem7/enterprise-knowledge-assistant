from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    conversation_id: int
    rating: str = Field(pattern="^(useful|not_useful)$")
    comment: str | None = None


class FeedbackRead(BaseModel):
    id: int
    conversation_id: int
    rating: str
    comment: str | None
    created_at: datetime

