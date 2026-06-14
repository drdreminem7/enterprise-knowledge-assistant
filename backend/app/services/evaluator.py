import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.evaluation_question import EvaluationQuestion
from backend.app.models.evaluation_result import EvaluationResult
from backend.app.services.llm_client import generate_grounded_answer
from backend.app.services.rag_pipeline import build_grounded_prompt, retrieve_context_for_question


@dataclass
class EvaluationRunSummary:
    results: list[EvaluationResult]
    average_score: float | None


def run_evaluation_set(
    db: Session,
    questions: list[EvaluationQuestion],
    knowledge_base_id: int,
    top_k: int = 5,
) -> EvaluationRunSummary:
    stored_results: list[EvaluationResult] = []

    for question in questions:
        retrieval = retrieve_context_for_question(
            db=db,
            knowledge_base_id=knowledge_base_id,
            question=question.question,
            top_k=top_k,
        )

        if retrieval.context:
            prompt = build_grounded_prompt(question=question.question, context=retrieval.context)
            generated_answer = generate_grounded_answer(prompt)
        else:
            generated_answer = "I could not find relevant information in the knowledge base for that question."

        score = score_answer(
            expected_answer=question.expected_answer,
            generated_answer=generated_answer,
        )
        notes = build_evaluation_notes(retrieved_chunk_count=len(retrieval.results), document_scope=question.document_scope)

        result = EvaluationResult(
            question_id=question.id,
            generated_answer=generated_answer,
            score=score,
            notes=notes,
        )
        db.add(result)
        stored_results.append(result)

    db.commit()
    for result in stored_results:
        db.refresh(result)

    average_score = None
    if stored_results:
        average_score = sum(result.score for result in stored_results) / len(stored_results)

    return EvaluationRunSummary(results=stored_results, average_score=average_score)


def score_answer(expected_answer: str, generated_answer: str) -> float:
    expected_tokens = normalize_tokens(expected_answer)
    generated_tokens = normalize_tokens(generated_answer)

    if not expected_tokens:
        return 0.0

    overlap = expected_tokens.intersection(generated_tokens)
    return len(overlap) / len(expected_tokens)


def normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def build_evaluation_notes(retrieved_chunk_count: int, document_scope: str | None) -> str:
    scope = document_scope or "all indexed documents"
    return f"retrieved_chunks={retrieved_chunk_count}; scope={scope}"

