from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy import select

from sqlalchemy.orm import Session

from backend.app.models.chunk import Chunk
from backend.app.models.conversation import Conversation
from backend.app.models.conversation_message import ConversationMessage
from backend.app.models.message_retrieval_log import MessageRetrievalLog
from backend.app.models.retrieval_log import RetrievalLog
from backend.app.services.embeddings import generate_query_embedding
from backend.app.services.llm_client import generate_grounded_answer, rewrite_query_for_retrieval
from backend.app.services.vector_search import SearchResult, search_similar_chunks


@dataclass
class RetrievalPackage:
    question: str
    rewritten_query: str
    results: list[SearchResult]
    context: str


@dataclass
class AnswerPackage:
    answer: str
    chunks: list[Chunk]
    conversation_id: int


@dataclass
class HistoryMessage:
    message_id: int | None
    role: str
    content: str
    rewritten_query: str | None
    created_at: datetime | None


@dataclass
class TurnPreparation:
    conversation: Conversation
    history_messages: list[HistoryMessage]
    retrieval: RetrievalPackage
    prompt: str


def retrieve_context_for_question(
    db: Session,
    knowledge_base_id: int,
    question: str,
    history_messages: list[HistoryMessage] | None = None,
    top_k: int = 5,
) -> RetrievalPackage:
    rewritten_query = rewrite_follow_up_question(question=question, history_messages=history_messages)
    query_embedding = generate_query_embedding(rewritten_query)
    results = search_similar_chunks(
        db=db,
        query_embedding=query_embedding,
        knowledge_base_id=knowledge_base_id,
        top_k=top_k,
    )
    chunks = [result.chunk for result in results]
    context = build_context_from_chunks(chunks)
    return RetrievalPackage(
        question=question,
        rewritten_query=rewritten_query,
        results=results,
        context=context,
    )


def build_context_from_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return ""

    parts: list[str] = []
    for chunk in chunks:
        parts.append(
            f"[document_id={chunk.document_id} chunk_index={chunk.chunk_index}]\n{chunk.content}"
        )
    return "\n\n".join(parts)


def answer_question_with_context(
    db: Session,
    knowledge_base_id: int,
    question: str,
    conversation_id: int | None = None,
    top_k: int = 5,
) -> AnswerPackage:
    started_at = perf_counter()
    preparation = prepare_conversation_turn(
        db=db,
        knowledge_base_id=knowledge_base_id,
        question=question,
        conversation_id=conversation_id,
        top_k=top_k,
    )
    retrieval = preparation.retrieval

    if not retrieval.context:
        answer = "I could not find relevant information in the knowledge base for that question."
        conversation = save_conversation_turn(
            db=db,
            conversation=preparation.conversation,
            question=question,
            answer=answer,
            latency_ms=int((perf_counter() - started_at) * 1000),
            rewritten_query=retrieval.rewritten_query,
            results=retrieval.results,
        )
        return AnswerPackage(answer=answer, chunks=[], conversation_id=conversation.id)

    prompt = preparation.prompt
    answer = generate_grounded_answer(prompt)
    conversation = save_conversation_turn(
        db=db,
        conversation=preparation.conversation,
        question=question,
        answer=answer,
        latency_ms=int((perf_counter() - started_at) * 1000),
        rewritten_query=retrieval.rewritten_query,
        results=retrieval.results,
    )
    return AnswerPackage(
        answer=answer,
        chunks=[result.chunk for result in retrieval.results],
        conversation_id=conversation.id,
    )


def build_citations(chunks: list[Chunk], snippet_length: int = 220) -> list[dict[str, int | str]]:
    citations: list[dict[str, int | str]] = []
    for chunk in chunks:
        snippet = chunk.content[:snippet_length].strip()
        if len(chunk.content) > snippet_length:
            snippet += "..."

        document_name = chunk.document.filename if chunk.document else f"document-{chunk.document_id}"
        citations.append(
            {
                "document_id": chunk.document_id,
                "document_name": document_name,
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "snippet": snippet,
            }
        )
    return citations


def build_message_payloads(
    db: Session,
    conversation: Conversation,
) -> list[dict[str, Any]]:
    messages = load_conversation_history(db, conversation)
    return [
        {
            "message_id": message.message_id,
            "role": message.role,
            "content": message.content,
            "rewritten_query": message.rewritten_query,
            "created_at": message.created_at,
        }
        for message in messages
    ]


def build_latest_citations_for_conversation(
    db: Session,
    conversation: Conversation,
) -> list[dict[str, int | str]]:
    persisted_messages = _fetch_persisted_messages(db, conversation.id)
    latest_assistant = next(
        (message for message in reversed(persisted_messages) if message.role == "assistant"),
        None,
    )
    if latest_assistant and latest_assistant.retrieval_logs:
        ordered_logs = sorted(latest_assistant.retrieval_logs, key=lambda log: log.rank)
        return build_citations([log.chunk for log in ordered_logs])

    statement = (
        select(RetrievalLog)
        .where(RetrievalLog.conversation_id == conversation.id)
        .order_by(RetrievalLog.rank.asc())
    )
    retrieval_logs = db.scalars(statement).all()
    return build_citations([retrieval_log.chunk for retrieval_log in retrieval_logs])


def prepare_conversation_turn(
    db: Session,
    knowledge_base_id: int,
    question: str,
    conversation_id: int | None = None,
    top_k: int = 5,
) -> TurnPreparation:
    conversation = _resolve_conversation(
        db=db,
        knowledge_base_id=knowledge_base_id,
        question=question,
        conversation_id=conversation_id,
    )
    history_messages = load_conversation_history(db, conversation)
    retrieval = retrieve_context_for_question(
        db=db,
        knowledge_base_id=knowledge_base_id,
        question=question,
        history_messages=history_messages,
        top_k=top_k,
    )
    prompt = build_grounded_prompt(
        question=question,
        context=retrieval.context,
        history_messages=history_messages,
    )
    return TurnPreparation(
        conversation=conversation,
        history_messages=history_messages,
        retrieval=retrieval,
        prompt=prompt,
    )


def save_conversation_turn(
    db: Session,
    conversation: Conversation,
    question: str,
    answer: str,
    latency_ms: int,
    rewritten_query: str | None,
    results: list[SearchResult],
) -> Conversation:
    _persist_legacy_messages_if_needed(db, conversation)

    user_message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=question,
        rewritten_query=rewritten_query,
    )
    assistant_message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
    )
    db.add_all([user_message, assistant_message])
    db.flush()

    for result in results:
        db.add(
            MessageRetrievalLog(
                conversation_message_id=assistant_message.id,
                chunk_id=result.chunk.id,
                similarity_score=result.similarity_score,
                rank=result.rank,
            )
        )
        db.add(
            RetrievalLog(
                conversation_id=conversation.id,
                chunk_id=result.chunk.id,
                similarity_score=result.similarity_score,
                rank=result.rank,
            )
        )

    if not conversation.question:
        conversation.question = question
    conversation.answer = answer
    conversation.latency_ms = latency_ms

    db.commit()
    db.refresh(conversation)
    return conversation


def build_grounded_prompt(
    question: str,
    context: str,
    history_messages: list[HistoryMessage] | None = None,
) -> str:
    history_block = build_history_block(history_messages)
    return (
        "You are an enterprise knowledge assistant.\n"
        "Use the conversation history for continuity when the user asks a follow-up.\n"
        "Answer the user's question using only the provided context.\n"
        "If the context does not contain the answer, say that the information is not available.\n\n"
        f"{history_block}"
        f"Context:\n{context}\n\n"
        f"Question:\n{question}\n\n"
        "Answer:"
    )


def build_history_block(history_messages: list[HistoryMessage] | None, max_messages: int = 8) -> str:
    if not history_messages:
        return ""

    recent_messages = history_messages[-max_messages:]
    transcript = "\n".join(
        f"{message.role.title()}: {message.content}"
        for message in recent_messages
    )
    return f"Conversation history:\n{transcript}\n\n"


def build_retrieval_query(question: str, history_messages: list[HistoryMessage] | None) -> str:
    if not history_messages:
        return question

    recent_messages = history_messages[-6:]
    transcript = "\n".join(
        f"{message.role}: {message.content}"
        for message in recent_messages
    )
    return (
        "Use this conversation context to understand the latest question.\n"
        f"{transcript}\n\n"
        f"Latest user question: {question}"
    )


def rewrite_follow_up_question(
    question: str,
    history_messages: list[HistoryMessage] | None,
) -> str:
    if not history_messages:
        return question

    prompt = build_query_rewrite_prompt(question=question, history_messages=history_messages)
    rewritten_query = rewrite_query_for_retrieval(prompt)
    cleaned_query = " ".join(rewritten_query.split())
    return cleaned_query or question


def build_query_rewrite_prompt(
    question: str,
    history_messages: list[HistoryMessage],
    max_messages: int = 6,
) -> str:
    recent_messages = history_messages[-max_messages:]
    transcript = "\n".join(
        f"{message.role.title()}: {message.content}"
        for message in recent_messages
    )
    return (
        "Rewrite the latest user question into a standalone enterprise retrieval query.\n"
        "Use the conversation history only to resolve references such as 'that', 'it', or 'the policy'.\n"
        "If the latest question is already standalone, return it unchanged.\n"
        "Output only the rewritten query with no explanation.\n\n"
        f"Conversation history:\n{transcript}\n\n"
        f"Latest user question:\n{question}\n\n"
        "Standalone retrieval query:"
    )


def load_conversation_history(db: Session, conversation: Conversation) -> list[HistoryMessage]:
    persisted_messages = _fetch_persisted_messages(db, conversation.id)
    if persisted_messages:
        return [
            HistoryMessage(
                message_id=message.id,
                role=message.role,
                content=message.content,
                rewritten_query=message.rewritten_query,
                created_at=message.created_at,
            )
            for message in persisted_messages
        ]

    history: list[HistoryMessage] = []
    if conversation.question:
        history.append(
            HistoryMessage(
                message_id=None,
                role="user",
                content=conversation.question,
                rewritten_query=None,
                created_at=conversation.created_at,
            )
        )
    if conversation.answer:
        history.append(
            HistoryMessage(
                message_id=None,
                role="assistant",
                content=conversation.answer,
                rewritten_query=None,
                created_at=conversation.created_at,
            )
        )
    return history


def _resolve_conversation(
    db: Session,
    knowledge_base_id: int,
    question: str,
    conversation_id: int | None,
) -> Conversation:
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found.")
        if conversation.knowledge_base_id != knowledge_base_id:
            raise ValueError("Conversation does not belong to the selected knowledge base.")
        return conversation

    conversation = Conversation(
        knowledge_base_id=knowledge_base_id,
        question=question,
        answer="",
        latency_ms=None,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _persist_legacy_messages_if_needed(db: Session, conversation: Conversation) -> None:
    persisted_messages = _fetch_persisted_messages(db, conversation.id)
    if persisted_messages or not conversation.question:
        return

    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=conversation.question,
            rewritten_query=None,
            created_at=conversation.created_at,
        )
    )
    if conversation.answer:
        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=conversation.answer,
                created_at=conversation.created_at,
            )
        )
    db.flush()


def _fetch_persisted_messages(db: Session, conversation_id: int) -> list[ConversationMessage]:
    statement = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    return db.scalars(statement).all()
