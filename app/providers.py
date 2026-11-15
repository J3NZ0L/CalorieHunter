import asyncio
import json
import os
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError


class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...


class SystemClock:
    def today(self) -> date:
        return datetime.now().date()

    def now(self) -> datetime:
        return datetime.now()


INVALID_AI_OUTPUT_ERROR = "The AI returned an invalid result"
UNAVAILABLE_ERROR = "Nutrition service unavailable"


class InvalidAIOutputError(ValueError):
    """AI output is missing fields, malformed or macro/energy-inconsistent."""


class NutritionUnavailableError(RuntimeError):
    """The nutrition provider timed out or is unavailable."""


class NutritionEstimate(BaseModel):
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: Literal["low", "medium", "high"]


def parse_estimate(payload: Any) -> NutritionEstimate:
    """Parse a raw payload into a NutritionEstimate; raise InvalidAIOutputError if malformed."""
    if not isinstance(payload, Mapping):
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
    try:
        return NutritionEstimate.model_validate(dict(payload), strict=True)
    except ValidationError as exc:
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR) from exc


class NutritionProvider(Protocol):
    async def estimate(self, description: str) -> NutritionEstimate: ...


DEFAULT_STUB_PAYLOAD: dict[str, Any] = {
    "calories_kcal": 248,
    "protein_g": 46.5,
    "carbs_g": 0,
    "fat_g": 5.4,
    "confidence": "medium",
}

StubMode = Literal["ok", "timeout", "unavailable"]


class StubNutritionProvider:
    """Deterministic provider for tests/demo.

    `responses` maps an exact description to a raw payload; `default` is used otherwise.
    Payloads may be deliberately invalid (negative macro, missing key, inconsistent kcal).
    `mode` set to "timeout"/"unavailable" makes `estimate` raise NutritionUnavailableError.
    """

    def __init__(
        self,
        responses: Mapping[str, Mapping[str, Any]] | None = None,
        default: Mapping[str, Any] | None = None,
        mode: StubMode = "ok",
    ) -> None:
        self.responses: dict[str, Mapping[str, Any]] = dict(responses or {})
        self.default: Mapping[str, Any] = default if default is not None else DEFAULT_STUB_PAYLOAD
        self.mode: StubMode = mode
        self.calls: list[str] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def estimate(self, description: str) -> NutritionEstimate:
        self.calls.append(description)
        if self.mode == "timeout":
            raise NutritionUnavailableError(UNAVAILABLE_ERROR) from TimeoutError()
        if self.mode == "unavailable":
            raise NutritionUnavailableError(UNAVAILABLE_ERROR)
        return parse_estimate(self.responses.get(description, self.default))


GEMINI_PROMPT = (
    "Estimate the nutrition of the following food description (Hungarian or English). "
    "Respond with JSON only: calories_kcal, protein_g, carbs_g, fat_g (numbers for the "
    "whole described portion, kcal ~= 4*protein + 4*carbs + 9*fat) and confidence "
    '("low", "medium" or "high").\n\nFood: '
)


class GeminiNutritionProvider:
    """Real provider using google-genai. Configured via GEMINI_API_KEY / GEMINI_MODEL."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 15.0,
        client: Any = None,
    ) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.timeout_s = timeout_s
        if client is not None:
            self._client = client
            return
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise NutritionUnavailableError(UNAVAILABLE_ERROR)
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            api_key=key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
        )

    async def estimate(self, description: str) -> NutritionEstimate:
        try:
            config: Any = {
                "response_mime_type": "application/json",
                "response_schema": NutritionEstimate,
                "temperature": 0,
            }
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model, contents=GEMINI_PROMPT + description, config=config
                ),
                timeout=self.timeout_s,
            )
            text = response.text
        except Exception as exc:  # timeout, network, API/auth/quota errors
            raise NutritionUnavailableError(UNAVAILABLE_ERROR) from exc
        if not text:
            raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR) from exc
        return parse_estimate(payload)
