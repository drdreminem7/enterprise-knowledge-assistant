from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.chunk import Chunk
from backend.app.models.document import Document
from backend.app.models.knowledge_base import KnowledgeBase
from backend.app.schemas.chunk import ChunkRead
from backend.app.schemas.document import DocumentRead
from backend.app.schemas.retrieval import RetrievalRequest
from backend.app.services.document_loader import extract_text_from_file
from backend.app.services.embeddings import generate_query_embedding
from backend.app.services.ingestion import ingest_document_text
from backend.app.services.vector_search import search_similar_chunks

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    statement = select(Document).order_by(Document.id.asc())
    return db.scalars(statement).all()


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return document


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    knowledge_base_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    settings = get_settings()
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".pdf", ".docx"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use PDF, DOCX, or TXT.",
        )

    contents = file.file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB limit.",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "uploaded-file").name
    stored_name = f"{knowledge_base_id}_{uuid4().hex}_{safe_name}"
    storage_path = upload_dir / stored_name
    storage_path.write_bytes(contents)

    document = Document(
        knowledge_base_id=knowledge_base_id,
        filename=safe_name,
        file_type=suffix.lstrip("."),
        status="processing",
        storage_path=str(storage_path),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        extracted_text, page_count = extract_text_from_file(str(storage_path))
        document.page_count = page_count
        ingest_document_text(db=db, document=document, text=extracted_text)
        document.status = "indexed"
        db.commit()
        db.refresh(document)
    except Exception:
        document.status = "failed"
        db.commit()
        raise

    return document


@router.get("/{document_id}/chunks", response_model=list[ChunkRead])
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[Chunk]:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    statement = (
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index.asc())
    )
    return db.scalars(statement).all()


@router.post("/search", response_model=list[ChunkRead])
def search_chunks(
    payload: RetrievalRequest,
    db: Session = Depends(get_db),
) -> list[Chunk]:
    knowledge_base = db.get(KnowledgeBase, payload.knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    query_embedding = generate_query_embedding(payload.question)
    results = search_similar_chunks(
        db=db,
        query_embedding=query_embedding,
        knowledge_base_id=payload.knowledge_base_id,
        top_k=payload.top_k,
    )
    return [result.chunk for result in results]
