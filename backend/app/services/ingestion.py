from sqlalchemy.orm import Session

from backend.app.models.chunk import Chunk
from backend.app.models.document import Document
from backend.app.services.chunker import split_text_into_chunks
from backend.app.services.embeddings import generate_document_embedding


def ingest_document_text(db: Session, document: Document, text: str) -> list[Chunk]:
    chunk_data_items = split_text_into_chunks(text)

    chunks: list[Chunk] = []
    for item in chunk_data_items:
        chunk = Chunk(
            document_id=document.id,
            chunk_index=item.chunk_index,
            content=item.content,
            token_count=len(item.content.split()),
            embedding=generate_document_embedding(content=item.content, title=document.filename),
        )
        db.add(chunk)
        chunks.append(chunk)

    db.commit()

    for chunk in chunks:
        db.refresh(chunk)

    return chunks
