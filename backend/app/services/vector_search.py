from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.models.chunk import Chunk
from backend.app.models.document import Document


@dataclass
class SearchResult:
    chunk: Chunk
    similarity_score: float
    rank: int


def search_similar_chunks(
    db: Session,
    query_embedding: list[float],
    knowledge_base_id: int,
    top_k: int = 5,
) -> list[SearchResult]:
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
    statement: Select[tuple[Chunk, float]] = (
        select(Chunk, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(top_k)
    )
    rows = db.execute(statement).all()

    results: list[SearchResult] = []
    for index, (chunk, chunk_distance) in enumerate(rows, start=1):
        similarity_score = max(0.0, 1.0 - float(chunk_distance))
        results.append(SearchResult(chunk=chunk, similarity_score=similarity_score, rank=index))
    return results
