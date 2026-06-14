from functools import lru_cache
from math import sqrt

from google import genai
from google.genai import types

from backend.app.core.config import get_settings

settings = get_settings()


def _prepare_document_embedding_input(content: str, title: str) -> str:
    return f"title: {title or 'none'} | text: {content}"


@lru_cache
def get_embedding_client() -> genai.Client:
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY is not configured.")
    return genai.Client(api_key=settings.google_api_key)


def generate_document_embedding(content: str, title: str) -> list[float]:
    embedding_input = _prepare_document_embedding_input(content=content, title=title)
    return _generate_embedding(embedding_input=embedding_input, task_type="RETRIEVAL_DOCUMENT")


def generate_query_embedding(question: str) -> list[float]:
    return _generate_embedding(embedding_input=question, task_type="RETRIEVAL_QUERY")


def _generate_embedding(embedding_input: str, task_type: str) -> list[float]:
    client = get_embedding_client()

    result = client.models.embed_content(
        model=settings.embedding_model,
        contents=embedding_input,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.embedding_dimension,
        ),
    )
    [embedding] = result.embeddings
    values = list(embedding.values)
    return _normalize_embedding(values)


def _normalize_embedding(values: list[float]) -> list[float]:
    if settings.embedding_dimension == 3072:
        return values

    magnitude = sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return values

    return [value / magnitude for value in values]
