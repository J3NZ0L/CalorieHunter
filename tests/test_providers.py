import asyncio
from types import SimpleNamespace

import pytest

from app.providers import (
    GeminiNutritionProvider,
    InvalidAIOutputError,
    NutritionEstimate,
    NutritionUnavailableError,
    StubNutritionProvider,
)
from app.validator import validate_estimate

CHICKEN = {"calories_kcal": 248, "protein_g": 46.5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"}


def run(coro):
    return asyncio.run(coro)


def test_stub_default_and_counter():
    stub = StubNutritionProvider(default=CHICKEN)
    est = run(stub.estimate("150 g chicken breast"))
    assert est == NutritionEstimate(**CHICKEN)
    run(stub.estimate("x"))
    assert stub.call_count == 2
    assert stub.calls == ["150 g chicken breast", "x"]


def test_stub_configured_responses_per_description():
    stub = StubNutritionProvider(responses={"a": CHICKEN})
    assert run(stub.estimate("a")).calories_kcal == 248
    assert run(stub.estimate("unknown")).confidence in {"low", "medium", "high"}


def test_stub_timeout_and_unavailable_count_calls():
    for mode in ("timeout", "unavailable"):
        stub = StubNutritionProvider(mode=mode)
        with pytest.raises(NutritionUnavailableError):
            run(stub.estimate("a"))
        assert stub.call_count == 1


def test_stub_missing_field_raises_invalid_output():
    bad = {k: v for k, v in CHICKEN.items() if k != "calories_kcal"}
    stub = StubNutritionProvider(default=bad)
    with pytest.raises(InvalidAIOutputError):
        run(stub.estimate("a"))


def test_stub_semantically_invalid_payloads_are_caught_by_validator():
    for patch in ({"protein_g": -5}, {"calories_kcal": 900, "protein_g": 30, "carbs_g": 45, "fat_g": 0}):
        stub = StubNutritionProvider(default={**CHICKEN, **patch})
        est = run(stub.estimate("a"))
        with pytest.raises(InvalidAIOutputError):
            validate_estimate(est.model_dump())


def test_stub_set_mode_at_runtime():
    stub = StubNutritionProvider(default=CHICKEN)
    stub.mode = "timeout"
    with pytest.raises(NutritionUnavailableError):
        run(stub.estimate("a"))


class FakeModels:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.kwargs = text, exc, None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return SimpleNamespace(text=self.text)


def gemini(text=None, exc=None):
    models = FakeModels(text, exc)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiNutritionProvider(client=client, model="m"), models


def test_gemini_parses_json():
    import json

    provider, models = gemini(json.dumps(CHICKEN))
    est = run(provider.estimate("150 g chicken breast"))
    assert est.protein_g == 46.5
    assert "150 g chicken breast" in models.kwargs["contents"]


@pytest.mark.parametrize("text", ["not json", "[]", '{"protein_g": 1}', None])
def test_gemini_bad_output(text):
    provider, _ = gemini(text)
    with pytest.raises(InvalidAIOutputError):
        run(provider.estimate("a"))


@pytest.mark.parametrize("exc", [TimeoutError(), ConnectionError("x"), RuntimeError("boom")])
def test_gemini_failures_map_to_unavailable(exc):
    provider, _ = gemini(exc=exc)
    with pytest.raises(NutritionUnavailableError):
        run(provider.estimate("a"))


def test_gemini_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(NutritionUnavailableError):
        GeminiNutritionProvider(api_key=None)
