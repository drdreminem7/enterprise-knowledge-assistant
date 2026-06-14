from collections.abc import Iterator
from functools import lru_cache

from google import genai
from google.genai import errors

from backend.app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_llm_client() -> genai.Client:
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY is not configured.")
    return genai.Client(api_key=settings.google_api_key)


def _generation_models() -> list[str]:
    fallbacks = [
        item.strip()
        for item in settings.gemini_fallback_models.split(",")
        if item.strip()
    ]
    ordered = [settings.gemini_model, *fallbacks]

    unique_models: list[str] = []
    for model_name in ordered:
        if model_name not in unique_models:
            unique_models.append(model_name)
    return unique_models


def _should_try_next_model(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "code", None)

    if isinstance(error, errors.ClientError) and isinstance(status_code, int):
        return status_code == 429 or status_code >= 500

    if isinstance(status_code, int):
        return status_code == 429 or status_code >= 500

    return False


def _generate_content_with_fallback(prompt: str) -> str:
    client = get_llm_client()
    last_error: Exception | None = None

    for model_name in _generation_models():
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as error:  # pragma: no cover - narrow provider behavior varies
            last_error = error
            if not _should_try_next_model(error):
                raise
            continue

    if last_error is not None:
        raise last_error
    return ""


def generate_grounded_answer(prompt: str) -> str:
    return _generate_content_with_fallback(prompt)


def stream_grounded_answer(prompt: str) -> Iterator[str]:
    client = get_llm_client()
    last_error: Exception | None = None

    for model_name in _generation_models():
        emitted_text = False
        try:
            for chunk in client.models.generate_content_stream(
                model=model_name,
                contents=prompt,
            ):
                text = chunk.text or ""
                if text:
                    emitted_text = True
                    yield text
            return
        except Exception as error:  # pragma: no cover - narrow provider behavior varies
            last_error = error
            if emitted_text or not _should_try_next_model(error):
                raise
            continue

    if last_error is not None:
        raise last_error


def rewrite_query_for_retrieval(prompt: str) -> str:
    return _generate_content_with_fallback(prompt)
