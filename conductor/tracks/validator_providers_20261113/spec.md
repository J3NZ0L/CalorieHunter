# Spec: Validator, normalizer and LLM providers

## Overview
Implement `app/validator.py` and extend `app/providers.py` to support AC1–AC6 and SPECIFICATION §5.

## Functional Requirements
1. **Input validation:** trim description; valid iff `1 <= len <= 200`; otherwise raise error with message `Description must be 1–200 characters` (U+2013).
2. **Normalization:** trim, lowercase, collapse whitespace to single spaces, remove space between a number and `g` (`120 g`→`120g`, `  150  G  Chicken Breast ` → `150g chicken breast`).
3. **AI output validation:** require `calories_kcal, protein_g, carbs_g, fat_g, confidence` (confidence in low/medium/high); numbers finite and >= 0; `expected = 4P + 4C + 9F`; reject if `|kcal - expected| > 0.20 * expected`; if `expected == 0` require `kcal == 0`. Failure raises `InvalidAIOutputError` ("The AI returned an invalid result").
4. **Providers (`app/providers.py`):** `NutritionEstimate`, `NutritionProvider` protocol, `NutritionUnavailableError`, `StubNutritionProvider` (configured responses, call counter, modes: invalid payload, timeout/unavailable), `GeminiNutritionProvider` (google-genai, `GEMINI_API_KEY` from env, JSON structured output, timeout/API errors mapped to `NutritionUnavailableError`).

## Non-Functional
Type annotations everywhere; no LLM SDK use outside `providers.py`; no wall-clock use; tests offline.

## Acceptance Criteria
- AC3/AC4 length rules, AC2 normalization equivalence, AC5 invalid outputs (negative, missing kcal, 900 vs 300 kcal), AC6 unavailable stub; AC1 stub values 248/46.5/0/5.4/medium pass validation.

## Out of Scope
HTTP routes (`/estimate`, `/entries`), DB writes/cache, UI.
