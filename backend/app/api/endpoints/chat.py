from datetime import date, datetime
import json
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal, get_db
from backend.app.models.conversation import Conversation
from backend.app.models.knowledge_base import KnowledgeBase
from backend.app.models.retrieval_log import RetrievalLog
from backend.app.schemas.chat import ChatCitation, ChatDetail, ChatHistoryItem, ChatRequest, ChatResponse
from backend.app.services.llm_client import stream_grounded_answer
from backend.app.services.rag_pipeline import (
    answer_question_with_context,
    build_latest_citations_for_conversation,
    build_message_payloads,
    build_citations,
    build_grounded_prompt,
    load_conversation_history,
    prepare_conversation_turn,
    retrieve_context_for_question,
    save_conversation_turn,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    _ensure_knowledge_base_exists(db, payload.knowledge_base_id)

    try:
        result = answer_question_with_context(
            db=db,
            knowledge_base_id=payload.knowledge_base_id,
            question=payload.question,
            conversation_id=payload.conversation_id,
            top_k=payload.top_k,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return ChatResponse(
        conversation_id=result.conversation_id,
        question=payload.question,
        answer=result.answer,
        sources=build_citations(result.chunks),
    )


@router.post("/stream")
def stream_chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _ensure_knowledge_base_exists(db, payload.knowledge_base_id)

    def event_stream():
        with SessionLocal() as stream_db:
            started_at = perf_counter()
            try:
                preparation = prepare_conversation_turn(
                    db=stream_db,
                    knowledge_base_id=payload.knowledge_base_id,
                    question=payload.question,
                    conversation_id=payload.conversation_id,
                    top_k=payload.top_k,
                )
            except ValueError as error:
                yield _encode_stream_event({"type": "error", "detail": str(error)})
                return

            retrieval = preparation.retrieval
            chunks = [result.chunk for result in retrieval.results]
            sources = build_citations(chunks)

            if not retrieval.context:
                answer = "I could not find relevant information in the knowledge base for that question."
                conversation = save_conversation_turn(
                    db=stream_db,
                    conversation=preparation.conversation,
                    question=payload.question,
                    answer=answer,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    rewritten_query=retrieval.rewritten_query,
                    results=retrieval.results,
                )
                yield _encode_stream_event({"type": "chunk", "delta": answer})
                yield _encode_stream_event(
                    {
                        "type": "done",
                        "conversation": {
                            "conversation_id": conversation.id,
                            "knowledge_base_id": payload.knowledge_base_id,
                            "question": payload.question,
                            "answer": answer,
                            "created_at": conversation.created_at.isoformat(),
                            "messages": build_message_payloads(stream_db, conversation),
                            "sources": sources,
                        },
                    }
                )
                return

            answer_parts: list[str] = []
            for delta in stream_grounded_answer(preparation.prompt):
                answer_parts.append(delta)
                yield _encode_stream_event({"type": "chunk", "delta": delta})

            answer = "".join(answer_parts).strip()
            if not answer:
                answer = "The assistant did not return a grounded answer for that question."

            conversation = save_conversation_turn(
                db=stream_db,
                conversation=preparation.conversation,
                question=payload.question,
                answer=answer,
                latency_ms=int((perf_counter() - started_at) * 1000),
                rewritten_query=retrieval.rewritten_query,
                results=retrieval.results,
            )
            yield _encode_stream_event(
                {
                    "type": "done",
                    "conversation": {
                        "conversation_id": conversation.id,
                        "knowledge_base_id": payload.knowledge_base_id,
                        "question": conversation.question,
                        "answer": answer,
                        "created_at": conversation.created_at.isoformat(),
                        "messages": build_message_payloads(stream_db, conversation),
                        "sources": sources,
                    },
                },
            )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/{conversation_id}/sources", response_model=list[ChatCitation])
def get_chat_sources(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> list[ChatCitation]:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    latest_sources = build_latest_citations_for_conversation(db, conversation)
    if latest_sources:
        return latest_sources

    statement = (
        select(RetrievalLog)
        .where(RetrievalLog.conversation_id == conversation_id)
        .order_by(RetrievalLog.rank.asc())
    )
    retrieval_logs = db.scalars(statement).all()
    chunks = [retrieval_log.chunk for retrieval_log in retrieval_logs]
    return build_citations(chunks)


@router.get("/history", response_model=list[ChatHistoryItem])
def list_chat_history(
    knowledge_base_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ChatHistoryItem]:
    statement = select(Conversation).order_by(Conversation.created_at.desc(), Conversation.id.desc())
    if knowledge_base_id is not None:
        statement = statement.where(Conversation.knowledge_base_id == knowledge_base_id)

    conversations = db.scalars(statement).all()
    return [
        ChatHistoryItem(
            conversation_id=conversation.id,
            knowledge_base_id=conversation.knowledge_base_id,
            question=conversation.question,
            answer_preview=_build_answer_preview(conversation.answer),
            created_at=conversation.created_at,
        )
        for conversation in conversations
    ]


@router.get("/{conversation_id}", response_model=ChatDetail)
def get_chat_detail(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> ChatDetail:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return ChatDetail(
        conversation_id=conversation.id,
        knowledge_base_id=conversation.knowledge_base_id,
        question=conversation.question,
        answer=conversation.answer,
        created_at=conversation.created_at,
        messages=build_message_payloads(db, conversation),
        sources=get_chat_sources(conversation_id=conversation_id, db=db),
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> Response:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _build_answer_preview(answer: str, max_length: int = 120) -> str:
    preview = " ".join(answer.split())
    if len(preview) <= max_length:
        return preview
    return f"{preview[: max_length - 3].rstrip()}..."


def _encode_stream_event(payload: dict[str, object]) -> str:
    return json.dumps(payload, default=_json_default) + "\n"


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _ensure_knowledge_base_exists(db: Session, knowledge_base_id: int) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base
