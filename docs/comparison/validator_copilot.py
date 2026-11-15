import re
from collections.abc import Mapping
from math import isfinite
from typing import Any


DESCRIPTION_ERROR = "Description must be 1–200 characters"


def normalize_description(description: str) -> str:
    """Return the canonical key used for nutrition cache lookups."""
    normalized = " ".join(description.strip().lower().split())
    return re.sub(r"(?<=\d)\s+(?=(?:g|kg|mg|ml|l)\b)", "", normalized)


normalize_cache_key = normalize_description


def validate_description(description: str) -> bool:
    if not isinstance(description, str):
        return False
    return 1 <= len(description.strip()) <= 200


def is_valid_description(description: str) -> bool:
    return validate_description(description)


def validate_nutrition_result(result: Mapping[str, Any]) -> bool:
    required = ("calories_kcal", "protein_g", "carbs_g", "fat_g")
    if not isinstance(result, Mapping) or any(key not in result for key in required):
        return False
    try:
        values = [float(result[key]) for key in required]
    except (TypeError, ValueError):
        return False
    if not all(isfinite(value) and value >= 0 for value in values):
        return False

    calories, protein, carbs, fat = values
    implied = 4 * protein + 4 * carbs + 9 * fat
    if implied == 0:
        return calories == 0
    return abs(calories - implied) <= implied * 0.2


def validate_macros(result: Mapping[str, Any]) -> bool:
    return validate_nutrition_result(result)
