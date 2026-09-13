from __future__ import annotations

from typing import Any, TypeVar

from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel

from config import settings

T = TypeVar("T", bound=BaseModel)

_SYSTEM = (
    "You are CatchUp, a careful technical podcast researcher. "
    "Never invent facts, numbers, benchmarks, or quotes. "
    "Only use information present in the provided source material. "
    "If sources disagree, say so. Distinguish source claims from interpretation."
)


class LLMError(RuntimeError):
    pass


def supports_temperature(model: str) -> bool:
    name = model.lower().split("/")[-1]
    return not name.startswith(("o1", "o3", "o4", "gpt-5"))


def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)


def _request_kwargs(temperature: float | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": settings.openai_model}
    if temperature is not None and supports_temperature(settings.openai_model):
        kwargs["temperature"] = temperature
    return kwargs


def _is_temperature_unsupported(exc: Exception) -> bool:
    text = str(exc).lower()
    return "temperature" in text and (
        "unsupported" in text or "only the default" in text
    )


async def complete_json(
    user_prompt: str,
    schema: type[T],
    *,
    system: str = _SYSTEM,
    temperature: float | None = 0.2,
) -> T:
    client = _client()
    kwargs = _request_kwargs(temperature)
    try:
        completion = await _parse(client, schema, system, user_prompt, kwargs)
    except BadRequestError as exc:
        if temperature is None or not _is_temperature_unsupported(exc):
            raise LLMError(f"OpenAI structured completion failed: {exc}") from exc
        kwargs.pop("temperature", None)
        try:
            completion = await _parse(client, schema, system, user_prompt, kwargs)
        except Exception as retry_exc:
            raise LLMError(f"OpenAI structured completion failed: {retry_exc}") from retry_exc
    except Exception as exc:
        raise LLMError(f"OpenAI structured completion failed: {exc}") from exc

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise LLMError("OpenAI returned no parsed structured output")
    return parsed


async def _parse(
    client: AsyncOpenAI,
    schema: type[BaseModel],
    system: str,
    user_prompt: str,
    kwargs: dict[str, Any],
):
    return await client.beta.chat.completions.parse(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        response_format=schema,
        **kwargs,
    )


async def complete_text(
    user_prompt: str,
    *,
    system: str = _SYSTEM,
    temperature: float | None = 0.4,
) -> str:
    client = _client()
    kwargs = _request_kwargs(temperature)
    try:
        completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            **kwargs,
        )
    except BadRequestError as exc:
        if temperature is None or not _is_temperature_unsupported(exc):
            raise LLMError(f"OpenAI completion failed: {exc}") from exc
        kwargs.pop("temperature", None)
        try:
            completion = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                **kwargs,
            )
        except Exception as retry_exc:
            raise LLMError(f"OpenAI completion failed: {retry_exc}") from retry_exc
    except Exception as exc:
        raise LLMError(f"OpenAI completion failed: {exc}") from exc

    text = completion.choices[0].message.content
    if not text:
        raise LLMError("OpenAI returned an empty response")
    return text
