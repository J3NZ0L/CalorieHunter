# CalorieHunter

A small web app for logging meals: you type a food description (like `150 g chicken breast` or `briós 120 g`), the backend asks an LLM (Gemini) for a nutrition estimate, validates and caches it, and logs it into your daily list.

The requirements and the acceptance criteria (AC1-AC8) are in [SPECIFICATION.md](SPECIFICATION.md).

## Setup

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

Then paste your Gemini API key into `.env`. Optional settings: `GEMINI_MODEL` (default `gemini-3.5-flash-lite`), `CALORIEHUNTER_DB` (default `caloriehunter.db`) and `SESSION_SECRET` (random on every start if not set, so you have to log in again after a restart).

## Running Locally

Start the local development server with `uv` and `uvicorn`:

```bash
uv run uvicorn app.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### Running in Demo / Stub Mode

To run CalorieHunter offline without requiring a `GEMINI_API_KEY`, launch the app with `CALORIEHUNTER_PROVIDER=stub`:

```bash
CALORIEHUNTER_PROVIDER=stub uv run uvicorn app.main:app --reload
```

In stub mode, any new food query receives a valid mock nutrition estimate. Subsequent requests with the same normalized query will hit the cache.

To test with a fresh, clean database (e.g. without existing cached queries):

```bash
CALORIEHUNTER_PROVIDER=stub CALORIEHUNTER_DB=demo.db uv run uvicorn app.main:app --reload
```

## Tests

All tests run offline, with the stub provider and an injected clock:

```bash
uv run pytest -v
```

Current result: `66 passed`. The faulty vs. corrected test runs can be found in the [defect demo](docs/defect_demo/README.md).

### Verification of the acceptance criteria

Every AC has a `test_acN_*` test in both [tests/test_acceptance.py](tests/test_acceptance.py) and [tests/test_api.py](tests/test_api.py). The validator and the providers have their own unit tests in [tests/test_validator.py](tests/test_validator.py) and [tests/test_providers.py](tests/test_providers.py).

| AC | Case | Verification |
|---|---|---|
| AC1 normal estimate | normal case | automated + manual |
| AC2 cache hit | normal case | automated |
| AC3 length boundary | edge case (200 vs 201 chars after trim) | automated |
| AC4 empty input | invalid input | automated + manual |
| AC5 invalid AI output | edge case (±20% boundary), error case | automated |
| AC6 LLM unavailable | error case | automated + manual |
| AC7 unauthorised access | unauthorised operation | automated |
| AC8 daily total and date boundary | edge case (midnight) | automated |

The regression cases are the `1,5 g` and the 10.8 kcal boundary cases in [tests/test_validator.py](tests/test_validator.py), which were added together with the fix of these bugs (commit `9c40121`).

### Manual checks

Start the app in stub mode with a fresh database, and register a user:

```bash
rm -f demo.db
CALORIEHUNTER_PROVIDER=stub CALORIEHUNTER_DB=demo.db uv run uvicorn app.main:app
```

- AC1: Type `150 g chicken breast` and click Estimate. Expected: the result card shows 248 kcal, 46.5 g protein, 0 g carbs, 5.4 g fat, `medium` confidence and no cached badge, the entry shows up in today's list, and the daily total is 248 kcal.
- AC4: Type 3 spaces and click Estimate. Expected: the error "Description must be 1–200 characters" shows up, and the list and the daily total stay the same.
- AC6: Stop the app, and start it again with an invalid API key (it overrides the one in `.env`):

  ```bash
  GEMINI_API_KEY=invalid CALORIEHUNTER_DB=demo.db uv run uvicorn app.main:app
  ```

  Log in again and estimate something that is not cached yet, like `100 g rice`. Expected: the error "Nutrition service unavailable" shows up, the list stays the same, and the page is still usable (e.g. you can delete an entry or log out).

## Project state

The current version is `1.0.0`, every AC1-AC8 feature is implemented and tested. The versions are tagged in git:
- `v0.1.0` - first runnable version: auth, SQLite schema and UI shell,
- `v0.2.0` - nutrition provider, cache normalizer and macro validator,
- `v0.3.0` - end-to-end meal estimation, caching and daily log UI,
- `v1.0.0` - all AC1-AC8 verified.

The change request is not implemented yet.

## Documentation

### AI Usage

The documentation of my use of AI can be found here:

[AI_USAGE.md](docs/AI_USAGE.md)

The two versions of the feature implemented twice (by Antigravity and Copilot) are in [docs/comparison/](docs/comparison/).
