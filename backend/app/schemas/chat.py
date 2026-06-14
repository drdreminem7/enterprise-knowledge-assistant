from datetime import datetime

from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    knowledge_base_id: int
    question: str
    conversation_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class ChatCitation(BaseModel):
    document_id: int
    document_name: str
    chunk_id: int
    chunk_index: int
    snippet: str


class ChatResponse(BaseModel):
    conversation_id: int
    question: str
    answer: str
    sources: list[ChatCitation]


class ChatMessage(BaseModel):
    message_id: int | None
    role: str
    content: str
    rewritten_query: str | None = None
    created_at: datetime | None


class ChatHistoryItem(BaseModel):
    conversation_id: int
    knowledge_base_id: int
    question: str
    answer_preview: str
    created_at: datetime


class ChatDetail(BaseModel):
    conversation_id: int
    knowledge_base_id: int
    question: str
    answer: str
    created_at: datetime
    messages: list[ChatMessage]
    sources: list[ChatCitation]
