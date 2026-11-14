"""Description trimming/normalization and AI output validation."""

import math
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from app.providers import INVALID_AI_OUTPUT_ERROR, InvalidAIOutputError, NutritionEstimate

MAX_DESCRIPTION_LENGTH = 200
TOLERANCE = 0.20
DESCRIPTION_ERROR = "Description must be 1–200 characters"
CONFIDENCE_VALUES = ("low", "medium", "high")
_NUMERIC_FIELDS = ("calories_kcal", "protein_g", "carbs_g", "fat_g")

_WHITESPACE = re.compile(r"\s+")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
_UNIT_SPACE = re.compile(r"(?<=\d)\s+(?=(?:g|kg|mg|ml|l)\b)")


class InvalidDescriptionError(ValueError):
    """Description is empty or longer than 200 characters after trimming."""


def validate_description(description: str) -> str:
    """Return the trimmed description or raise InvalidDescriptionError."""
    trimmed = description.strip()
    if not 1 <= len(trimmed) <= MAX_DESCRIPTION_LENGTH:
        raise InvalidDescriptionError(DESCRIPTION_ERROR)
    return trimmed


def normalize_text(description: str) -> str:
    """Cache key: trim, lowercase, collapse spaces, decimal comma -> dot, `120 g` -> `120g`."""
    text = _WHITESPACE.sub(" ", description.strip().lower())
    text = _DECIMAL_COMMA.sub(".", text)
    return _UNIT_SPACE.sub("", text)


def _number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
    if not math.isfinite(value) or value < 0:
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
    return float(value)


def validate_estimate(payload: Mapping[str, Any]) -> NutritionEstimate:
    """Validate raw AI output; return a NutritionEstimate or raise InvalidAIOutputError."""
    values = {key: _number(payload, key) for key in _NUMERIC_FIELDS}
    confidence = payload.get("confidence")
    if confidence not in CONFIDENCE_VALUES:
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
    expected = values["protein_g"] * 4 + values["carbs_g"] * 4 + values["fat_g"] * 9
    kcal = values["calories_kcal"]
    if expected == 0:
        consistent = kcal == 0
    else:
        diff = abs(kcal - expected)
        limit = TOLERANCE * expected
        consistent = diff <= limit or math.isclose(diff, limit, rel_tol=1e-9, abs_tol=1e-9)
    if not consistent:
        raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
    return NutritionEstimate(confidence=confidence, **values)

def test_normalize_text(*args: str) -> None:
    """Print the normalized form of each provided query string."""
    for arg in args:
        print(f"Normalized query: {normalize_text(arg)}")


def main(argv: Sequence[str] | None = None) -> None:
    """Run normalization on CLI arguments, or prompt interactively if none are given."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        test_normalize_text(*args)
        return
    test_nutrition_query = input("Enter the test nutrition query text: ")
    test_normalize_text(test_nutrition_query)


if __name__ == "__main__":
    main()
