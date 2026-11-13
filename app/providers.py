from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel


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
