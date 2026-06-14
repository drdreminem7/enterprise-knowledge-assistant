from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    knowledge_base_id: int
    question: str
    top_k: int = Field(default=5, ge=1, le=20)

