`app/validator.py` and `app/providers.py` are implemented on the `validator-normalizer-and-llm-provider-agy` branch, and all 43 tests pass offline with `uv run pytest`. The `GeminiNutritionProvider` was only tested against a mocked client. I didn't call the real Gemini API.

**Conductor workflow:**
- **Setup:** The three skills work interactively, but your request already specified the product and tech stack, so I used autogenerate mode and skipped the question prompts. Setup created `conductor/` with the product, guidelines, tech stack, workflow and Python/general style guides.
- **Track:** The new track is `validator_providers_20261113`. Its spec, plan and registry entry are under [conductor](file:///home/zoltanjeney/Documents/University/BME%20AI%20MSc/1st_sem/Subjects/AI%20Assisted%20SW%20Dev/Homework%20Assignment/CalorieHunter/conductor/).
- **Implement:** I followed TDD in two phases (tests failing first, then the implementation). Each phase has its own commit with a git note, and the plan is marked complete.
- **Version:** I bumped it to 0.2.0.

**What's in the code:**
- **[validator.py](file:///home/zoltanjeney/Documents/University/BME%20AI%20MSc/1st_sem/Subjects/AI%20Assisted%20SW%20Dev/Homework%20Assignment/CalorieHunter/app/validator.py):**
  - `validate_description` enforces 1–200 characters after trimming, with the en-dash message.
  - `normalize_text` produces the cache key, so `  150  G  Chicken Breast ` becomes `150g chicken breast`.
  - `validate_estimate` checks required fields, finite non-negative numbers and the confidence value. It rejects any `4P + 4C + 9F` mismatch beyond ±20%, and requires 0 kcal when the macros sum to 0.
- **[providers.py](file:///home/zoltanjeney/Documents/University/BME%20AI%20MSc/1st_sem/Subjects/AI%20Assisted%20SW%20Dev/Homework%20Assignment/CalorieHunter/app/providers.py):**
  - `StubNutritionProvider` has a call counter, per-description responses, and `timeout`/`unavailable` modes. It can also return deliberately invalid payloads.
  - `GeminiNutritionProvider` reads `GEMINI_API_KEY` and `GEMINI_MODEL`, and asks for JSON output.
  - Provider timeouts and API errors become `NutritionUnavailableError`, which is the 503 case. Unparseable output becomes `InvalidAIOutputError`, which is the 502 case.

**Where the code differs from AGENTS.md:** `InvalidAIOutputError` and `NutritionUnavailableError` live in `providers.py`, not `validator.py`. Putting them in `validator.py` would create a circular import, and `validator.py` re-uses them. A missing-field payload can't be a `NutritionEstimate`, so the provider raises `InvalidAIOutputError` for it. The ±20% and negative-value checks are left to `validate_estimate`.

The `/estimate` route, DB writes and cache are not wired up yet. They were out of scope for this track.
