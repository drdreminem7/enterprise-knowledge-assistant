import io
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from fastapi import HTTPException

from backend.app.api.endpoints import feedback as feedback_endpoint
from backend.app.api.endpoints import health as health_endpoint
from backend.app.api.endpoints import knowledge_bases as knowledge_bases_endpoint
from backend.app.api.endpoints import documents as documents_endpoint
from backend.app.models.conversation import Conversation
from backend.app.models.evaluation_question import EvaluationQuestion
from backend.app.models.knowledge_base import KnowledgeBase
from backend.app.schemas.feedback import FeedbackCreate
from backend.app.schemas.knowledge_base import KnowledgeBaseCreate
from backend.app.services.chunker import split_text_into_chunks
from backend.app.services.document_loader import extract_text_from_file
from backend.app.services.evaluator import run_evaluation_set
from backend.app.services import llm_client
from backend.app.services.rag_pipeline import (
    RetrievalPackage,
    TurnPreparation,
    answer_question_with_context,
    retrieve_context_for_question,
)
from backend.app.services.vector_search import SearchResult


class FakeSession:
    def __init__(
        self,
        records: dict[tuple[type, int], object] | None = None,
        scalar_result: object | None = None,
    ):
        self.records = records or {}
        self.added: list[object] = []
        self.commit_count = 0
        self.scalar_result = scalar_result

    def get(self, model: type, key: int):
        return self.records.get((model, key))

    def add(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", len(self.added) + 1)
        self.added.append(obj)

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, _: object) -> None:
        return

    def scalar(self, _statement):
        return self.scalar_result


def test_health_endpoint_returns_ok() -> None:
    assert health_endpoint.health() == {"status": "ok"}


def test_create_knowledge_base_rejects_duplicate_name() -> None:
    db = FakeSession(
        scalar_result=KnowledgeBase(id=8, name="HR Demo", description="existing"),
    )

    with pytest.raises(HTTPException) as error:
        knowledge_bases_endpoint.create_knowledge_base(
            payload=KnowledgeBaseCreate(name="HR Demo", description="duplicate"),
            db=db,
        )

    assert error.value.status_code == 409
    assert error.value.detail == "A knowledge base with this name already exists."


def test_submit_feedback_returns_404_for_missing_conversation() -> None:
    db = FakeSession()

    with pytest.raises(HTTPException) as error:
        feedback_endpoint.submit_feedback(
            payload=FeedbackCreate(conversation_id=999, rating="useful"),
            db=db,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Conversation not found."


def test_extract_text_from_txt_file_and_reject_unsupported_suffix(tmp_path) -> None:
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello knowledge base", encoding="utf-8")

    text, pages = extract_text_from_file(str(txt_path))

    assert text == "hello knowledge base"
    assert pages is None

    bad_path = tmp_path / "notes.csv"
    bad_path.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text_from_file(str(bad_path))


def test_generate_grounded_answer_falls_back_to_next_model(monkeypatch) -> None:
    class QuotaError(Exception):
        status_code = 429

    class FakeModels:
        def __init__(self):
            self.calls: list[str] = []

        def generate_content(self, *, model: str, contents: str):
            self.calls.append(model)
            if model == "primary-model":
                raise QuotaError("quota exceeded")
            return SimpleNamespace(text=f"Answer from {model}: {contents}")

    fake_models = FakeModels()
    fake_client = SimpleNamespace(models=fake_models)

    monkeypatch.setattr(llm_client, "settings", SimpleNamespace(
        google_api_key="key",
        gemini_model="primary-model",
        gemini_fallback_models="fallback-model,backup-model",
    ))
    monkeypatch.setattr(llm_client, "get_llm_client", lambda: fake_client)

    answer = llm_client.generate_grounded_answer("hello")

    assert answer == "Answer from fallback-model: hello"
    assert fake_models.calls == ["primary-model", "fallback-model"]


def test_split_text_into_chunks_normalizes_whitespace_and_keeps_order() -> None:
    text = "Alpha    beta\n\n gamma\t delta epsilon zeta eta theta"

    chunks = split_text_into_chunks(text=text, chunk_size=12)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert " ".join(chunk.content for chunk in chunks) == "Alpha beta gamma delta epsilon zeta eta theta"
    assert all(len(chunk.content) <= 12 for chunk in chunks)


def test_upload_document_indexes_txt_file(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(max_upload_size_mb=1, upload_dir=str(tmp_path))
    knowledge_base = KnowledgeBase(id=1, name="HR Demo", description="Policy knowledge base")
    db = FakeSession(records={(KnowledgeBase, 1): knowledge_base})

    def fake_extract_text_from_file(path: str) -> tuple[str, int]:
        captured["storage_path"] = path
        return ("Remote work policy text", 2)

    def fake_ingest_document_text(db, document, text: str) -> list[object]:
        captured["ingested_document"] = document
        captured["ingested_text"] = text
        return []

    monkeypatch.setattr(documents_endpoint, "get_settings", lambda: settings)
    monkeypatch.setattr(documents_endpoint, "extract_text_from_file", fake_extract_text_from_file)
    monkeypatch.setattr(documents_endpoint, "ingest_document_text", fake_ingest_document_text)

    upload = UploadFile(filename="policy.txt", file=io.BytesIO(b"raw policy bytes"))

    document = documents_endpoint.upload_document(
        knowledge_base_id=1,
        file=upload,
        db=db,
    )

    assert document.status == "indexed"
    assert document.file_type == "txt"
    assert document.page_count == 2
    assert document.filename == "policy.txt"
    assert captured["ingested_text"] == "Remote work policy text"
    assert tmp_path.joinpath(document.storage_path.split("/")[-1]).exists()


def test_retrieve_context_for_question_rewrites_and_scopes_search(monkeypatch) -> None:
    chunk = SimpleNamespace(document_id=7, chunk_index=0, content="Remote work is allowed with manager approval.")
    captured: dict[str, object] = {}

    def fake_rewrite_follow_up_question(question: str, history_messages):
        captured["question"] = question
        captured["history_messages"] = history_messages
        return "remote work policy manager approval"

    def fake_generate_query_embedding(query: str) -> list[float]:
        captured["embedding_query"] = query
        return [0.1, 0.2, 0.3]

    def fake_search_similar_chunks(db, query_embedding, knowledge_base_id: int, top_k: int):
        captured["query_embedding"] = query_embedding
        captured["knowledge_base_id"] = knowledge_base_id
        captured["top_k"] = top_k
        return [SearchResult(chunk=chunk, similarity_score=0.92, rank=1)]

    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.rewrite_follow_up_question",
        fake_rewrite_follow_up_question,
    )
    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.generate_query_embedding",
        fake_generate_query_embedding,
    )
    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.search_similar_chunks",
        fake_search_similar_chunks,
    )

    retrieval = retrieve_context_for_question(
        db=object(),
        knowledge_base_id=3,
        question="What about remote work?",
        history_messages=[SimpleNamespace(role="user", content="Tell me about HR rules.")],
        top_k=4,
    )

    assert retrieval.rewritten_query == "remote work policy manager approval"
    assert "Remote work is allowed with manager approval." in retrieval.context
    assert captured["embedding_query"] == "remote work policy manager approval"
    assert captured["knowledge_base_id"] == 3
    assert captured["top_k"] == 4


def test_answer_question_with_context_generates_grounded_chat_answer(monkeypatch) -> None:
    fake_chunk = SimpleNamespace(id=11, content="Employees may work remotely up to two days.")
    captured: dict[str, object] = {}
    conversation = SimpleNamespace(id=12)
    retrieval = RetrievalPackage(
        question="What is the policy?",
        rewritten_query="what is the remote work policy",
        results=[SearchResult(chunk=fake_chunk, similarity_score=0.88, rank=1)],
        context="Employees may work remotely up to two days.",
    )
    preparation = TurnPreparation(
        conversation=conversation,
        history_messages=[],
        retrieval=retrieval,
        prompt="PROMPT WITH CONTEXT",
    )

    def fake_prepare_conversation_turn(**kwargs):
        captured["prepare_kwargs"] = kwargs
        return preparation

    def fake_generate_grounded_answer(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Employees may work remotely up to two days per week."

    def fake_save_conversation_turn(**kwargs):
        captured["saved_kwargs"] = kwargs
        return conversation

    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.prepare_conversation_turn",
        fake_prepare_conversation_turn,
    )
    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.generate_grounded_answer",
        fake_generate_grounded_answer,
    )
    monkeypatch.setattr(
        "backend.app.services.rag_pipeline.save_conversation_turn",
        fake_save_conversation_turn,
    )

    answer = answer_question_with_context(
        db=object(),
        knowledge_base_id=1,
        question="What is the policy?",
        conversation_id=9,
        top_k=5,
    )

    assert answer.answer == "Employees may work remotely up to two days per week."
    assert answer.conversation_id == 12
    assert answer.chunks == [fake_chunk]
    assert captured["prompt"] == "PROMPT WITH CONTEXT"
    assert captured["saved_kwargs"]["rewritten_query"] == "what is the remote work policy"


def test_run_evaluation_set_scores_and_stores_results(monkeypatch) -> None:
    db = FakeSession()
    question = EvaluationQuestion(
        id=1,
        set_id=1,
        question="What is the remote work policy?",
        expected_answer="remote work requires manager approval",
        document_scope="HR Demo",
    )

    monkeypatch.setattr(
        "backend.app.services.evaluator.retrieve_context_for_question",
        lambda **kwargs: RetrievalPackage(
            question=question.question,
            rewritten_query=question.question,
            results=[SearchResult(chunk=SimpleNamespace(id=99), similarity_score=0.91, rank=1)],
            context="Remote work requires manager approval.",
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.evaluator.generate_grounded_answer",
        lambda prompt: "Remote work requires manager approval.",
    )

    summary = run_evaluation_set(
        db=db,
        questions=[question],
        knowledge_base_id=1,
        top_k=3,
    )

    assert summary.average_score == 1.0
    assert len(summary.results) == 1
    assert summary.results[0].generated_answer == "Remote work requires manager approval."
    assert summary.results[0].notes == "retrieved_chunks=1; scope=HR Demo"
    assert db.commit_count == 1
