import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from .validator import validate_nutrition_result


class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...


class SystemClock:
    def today(self) -> date:
        return datetime.now().date()

    def now(self) -> datetime:
        return datetime.now()


class NutritionProvider(Protocol):
    def estimate(self, description: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NutritionResult:
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return {
            "calories_kcal": self.calories_kcal,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "confidence": self.confidence,
        }


class StubNutritionProvider:
    def __init__(
        self,
        result: dict[str, Any] | NutritionResult | None = None,
        failure: str | Exception | None = None,
        failure_mode: str | Exception | None = None,
        results: dict[str, Any] | NutritionResult | None = None,
    ) -> None:
        self.result = result or results or NutritionResult(248, 46.5, 0, 5.4).as_dict()
        self.failure = failure if failure is not None else failure_mode
        self.call_count = 0
        self.calls = 0

    def estimate(self, description: str) -> dict[str, Any]:
        self.call_count += 1
        self.calls += 1
        if self.failure:
            if isinstance(self.failure, Exception):
                raise self.failure
            mode = self.failure.lower()
            if mode in {"timeout", "unavailable", "api_unavailable"}:
                raise TimeoutError("Nutrition service unavailable")
            if mode in {"negative", "negative_macro", "invalid_negative"}:
                return {"calories_kcal": 100, "protein_g": -1, "carbs_g": 10, "fat_g": 2}
            if mode in {"missing", "missing_calories", "invalid_missing_calories"}:
                return {"protein_g": 10, "carbs_g": 10, "fat_g": 2}
            if mode in {"inconsistent", "invalid_inconsistent"}:
                return {"calories_kcal": 900, "protein_g": 10, "carbs_g": 10, "fat_g": 2}
            raise RuntimeError(mode)
        return self.result.as_dict() if isinstance(self.result, NutritionResult) else dict(self.result)

    def get_call_count(self) -> int:
        return self.call_count


class GeminiNutritionProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        client: Any | None = None,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        self.client = client
        self.model = model

    def estimate(self, description: str) -> dict[str, Any]:
        response = self.client.models.generate_content(
            model=self.model,
            contents=(
                "Estimate nutrition for this food description. Return only JSON with "
                "calories_kcal, protein_g, carbs_g, fat_g, and confidence "
                f"(low, medium, or high): {description}"
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "OBJECT",
                    "properties": {
                        "calories_kcal": {"type": "NUMBER"},
                        "protein_g": {"type": "NUMBER"},
                        "carbs_g": {"type": "NUMBER"},
                        "fat_g": {"type": "NUMBER"},
                        "confidence": {"type": "STRING"},
                    },
                    "required": ["calories_kcal", "protein_g", "carbs_g", "fat_g", "confidence"],
                },
            },
        )
        data = json.loads(response.text)
        if not validate_nutrition_result(data):
            raise ValueError("Invalid nutrition result")
        return data
