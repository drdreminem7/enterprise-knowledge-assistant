from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    file_type: str
    status: str
    page_count: int | None

    model_config = ConfigDict(from_attributes=True)
