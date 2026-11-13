# Plan

## Phase 1: Validator and normalizer
- [ ] Task: Write failing tests for length check and normalization (`tests/test_validator.py`)
- [ ] Task: Implement `validate_description` and `normalize_text` in `app/validator.py`
- [ ] Task: Write failing tests for AI output validation (negative, missing, ±20%, zero case, NaN, bad confidence)
- [ ] Task: Implement `validate_estimate` in `app/validator.py`
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)

## Phase 2: Providers
- [ ] Task: Write failing tests for `StubNutritionProvider` (responses, call counter, invalid payload, timeout) and `GeminiNutritionProvider` (mocked client)
- [ ] Task: Implement `NutritionEstimate`, errors, `StubNutritionProvider`, `GeminiNutritionProvider` in `app/providers.py`
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
