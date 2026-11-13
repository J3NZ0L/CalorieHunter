import math

import pytest

from app.validator import (
    DESCRIPTION_ERROR,
    InvalidAIOutputError,
    InvalidDescriptionError,
    normalize_text,
    validate_description,
    validate_estimate,
)

GOOD = {"calories_kcal": 248, "protein_g": 46.5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"}


def test_description_trimmed_and_bounds():
    assert validate_description("  abc  ") == "abc"
    assert len(validate_description("a" * 200)) == 200
    assert len(validate_description("  " + "a" * 200 + "  ")) == 200


@pytest.mark.parametrize("bad", ["", "   ", "a" * 201, " " + "a" * 201 + " "])
def test_description_rejected(bad):
    with pytest.raises(InvalidDescriptionError) as e:
        validate_description(bad)
    assert str(e.value) == DESCRIPTION_ERROR == "Description must be 1–200 characters"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  150  G  Chicken Breast ", "150g chicken breast"),
        ("150 g chicken breast", "150g chicken breast"),
        ("120 g", "120g"),
        ("Briós   120 G", "briós 120g"),
        ("1.5 g salt", "1.5g salt"),
        ("2 eggs", "2 eggs"),
        ("5 grapes", "5 grapes"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_text(raw) == expected


def test_valid_estimate():
    est = validate_estimate(dict(GOOD))
    assert est.calories_kcal == 248 and est.confidence == "medium"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(protein_g=-1),
        lambda d: d.pop("calories_kcal"),
        lambda d: d.update(calories_kcal=900, protein_g=30, carbs_g=45, fat_g=0),
        lambda d: d.update(calories_kcal=float("nan")),
        lambda d: d.update(fat_g=math.inf),
        lambda d: d.update(confidence="certain"),
        lambda d: d.update(protein_g="lots"),
        lambda d: d.update(calories_kcal=True),
    ],
)
def test_invalid_estimate(mutate):
    d = dict(GOOD)
    mutate(d)
    with pytest.raises(InvalidAIOutputError) as e:
        validate_estimate(d)
    assert str(e.value) == "The AI returned an invalid result"


def test_tolerance_boundary_and_zero():
    base = {"protein_g": 25, "carbs_g": 0, "fat_g": 0, "confidence": "low"}  # expected 100
    validate_estimate({**base, "calories_kcal": 120})
    validate_estimate({**base, "calories_kcal": 80})
    with pytest.raises(InvalidAIOutputError):
        validate_estimate({**base, "calories_kcal": 120.5})
    zero = {"protein_g": 0, "carbs_g": 0, "fat_g": 0, "confidence": "low"}
    validate_estimate({**zero, "calories_kcal": 0})
    with pytest.raises(InvalidAIOutputError):
        validate_estimate({**zero, "calories_kcal": 1})
