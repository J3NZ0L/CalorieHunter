# AGENTS.md — CalorieHunter Development Guide

This document defines the architecture, tooling, interfaces, schema, and acceptance contracts for **CalorieHunter**. [SPECIFICATION.md](SPECIFICATION.md) is the authoritative source of product requirements and acceptance criteria (AC1–AC8).

---

## 1. Tooling, Dependencies & Versioning

- **Package & environment manager:** Use **`uv`** exclusively (`uv init`, `uv add`, `uv sync`, `uv run`, `uv version`). Do not use `pip`, `poetry`, or manual virtualenvs.
- **Python version:** `>=3.12` (pinned via `.python-version` and `pyproject.toml`).
- **Semantic Versioning (SemVer):** Maintain `MAJOR.MINOR.PATCH` in `pyproject.toml` starting from the first runnable version (`0.1.0`), incrementing:
  - `PATCH` for bug fixes and test/doc updates,
  - `MINOR` for new backward-compatible endpoints or features,
  - `MAJOR` for breaking API/schema changes (`1.0.0` at full v1.0 feature completion).
- Keep `uv.lock` committed and in sync with `pyproject.toml`.

---

## 2. Project Structure

Follow this exact module layout:

```text
app/
  __init__.py
  main.py          # FastAPI app, dependency wiring, HTTP routes (/register, /login, /logout, /estimate, /entries)
  db.py            # SQLite connection management, schema initialization, parameterized queries
  auth.py          # Password hashing, session cookie signing/verification, current-user dependency
  providers.py     # Clock & NutritionProvider interfaces, SystemClock, Gemini provider, StubNutritionProvider, provider/AI-output error classes
  validator.py     # Description trimming/normalization, length bounds, AI output & ±20% macro/energy validation
static/
  index.html       # Single-page HTML/JS UI (auth form, food input + Estimate, result card + cached badge, today's entries + delete + daily total)
tests/
  ...              # Pytest suite covering AC1–AC8 using StubNutritionProvider and an injectable Clock
```

---

## 3. Architectural Decisions (from SPECIFICATION.md)

- **Roles:** `Guest` (register/login only) and `User` (estimate food, view/delete own entries, view own daily total). No admin role.
- **Authentication:** Passwords must be securely hashed (never stored in plaintext). A session cookie is the sole authentication mechanism. No email verification or password reset.
- **Languages & Duplicates:** Accepts Hungarian and English food descriptions. Duplicate entries are allowed.
- **Description Length:** Counted in characters **after trimming** (`1 <= len(trimmed) <= 200`).
- **Global Cache & Normalization:**
  - `nutrition_cache` is global across all users.
  - Cache key is `normalized_text`: trim leading/trailing whitespace, lowercase, collapse internal whitespace to single spaces, and remove space between numbers and `g` (e.g., `"  150  G  Chicken Breast "` -> `"150g chicken breast"`, `"120 g"` -> `"120g"`).
  - Matching is **exact**, never fuzzy.
  - On a cache hit, do not call `NutritionProvider`; return `cached: true` and still log a new entry for the user.
- **Date Boundary ("Today"):** Defined as the server's local date, read exclusively through an injectable `Clock`.

---

## 4. Injectable Interfaces (`app/providers.py`)

Both `Clock` and `NutritionProvider` must be injectable (via FastAPI dependencies / `app.dependency_overrides` or app factory) so automated tests never depend on wall-clock dates or external LLM APIs.

### `Clock`
```python
class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...
```
- `SystemClock`: returns `datetime.now().date()` / `datetime.now()` (server local time).
- Test `Clock`: returns a controllable date/time to verify date boundaries (AC8).

### `NutritionProvider`
```python
class NutritionEstimate(BaseModel):  # or dataclass / TypedDict
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: Literal["low", "medium", "high"]

class NutritionProvider(Protocol):
    async def estimate(self, description: str) -> NutritionEstimate: ...
```
- **Error classes (in `app/providers.py`):** `InvalidAIOutputError` (AC5, 502) and `NutritionUnavailableError` (AC6, 503), plus `INVALID_AI_OUTPUT_ERROR` and `UNAVAILABLE_ERROR` message constants. `validator.py` re-uses them.
- **Missing-field payloads:** A payload lacking a required field cannot be a `NutritionEstimate`; providers parse raw payloads with `parse_estimate()` and raise `InvalidAIOutputError` on failure.
- **Semantic checks:** Negative values and the ±20% check are done by `validator.validate_estimate()`, not by providers.
- **Real Provider:** `GeminiNutritionProvider` uses `google-genai` (`GEMINI_API_KEY`, optional `GEMINI_MODEL`). Timeouts and API/network errors raise `NutritionUnavailableError`.
- **`StubNutritionProvider`:** Deterministic test/demo provider supporting configured responses, call counting (for AC2), invalid payload simulation (AC5), and timeout/unavailable simulation (AC6).

---

## 5. SQLite Schema (`app/db.py`)

Initialize these three tables idempotently on startup:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    description TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    calories_kcal REAL NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    confidence TEXT NOT NULL,
    cached INTEGER NOT NULL DEFAULT 0,
    entry_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nutrition_cache (
    normalized_text TEXT PRIMARY KEY,
    calories_kcal REAL NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    confidence TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- Always use parameterized SQL (`?` placeholders); never interpolate user input into SQL strings.

---

## 6. Validation & Exact HTTP Error Contracts (AC1–AC8)

### Validation (`app/validator.py`)
`validator.py` raises `InvalidDescriptionError` for input errors and re-uses `InvalidAIOutputError` from `app/providers.py`.

1. **Input validation:** Trim `description`. If length is `0` or `> 200`, reject immediately before any cache lookup, AI call, or DB write.
2. **AI output validation:**
   - Must contain `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, and `confidence`.
   - All numeric values must be finite and non-negative (`>= 0`).
   - Macro/energy consistency: compute `expected_kcal = protein_g * 4 + carbs_g * 4 + fat_g * 9`. Reject if `calories_kcal` deviates by more than **±20%** from `expected_kcal` (e.g., `abs(calories_kcal - expected_kcal) > 0.20 * expected_kcal`; if `expected_kcal == 0`, require `calories_kcal == 0`).
   - On invalid AI output or provider failure, **nothing** is written to `entries` or `nutrition_cache`.

### Exact HTTP Status Codes & Error Messages
| AC | Condition | HTTP Status | Exact `detail` / Behavior |
|---|---|---|---|
| **AC1** | Normal estimate (`150 g chicken breast`) | `200` | Returns `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `confidence`, `cached: false`; logs entry; daily total increases. |
| **AC2** | Repeat normalized query | `200` | Returns cached values with `cached: true`; provider call count unchanged; logs a new entry. |
| **AC3** | Description > 200 chars after trim | `400` | `"Description must be 1–200 characters"` (en-dash `–`, U+2013). No AI call, no DB write. |
| **AC4** | Empty / whitespace-only description | `400` | `"Description must be 1–200 characters"`. UI displays error; no AI call, no DB write. |
| **AC5** | Invalid AI output (negative macro, missing `calories_kcal`, or outside ±20%) | `502` | `"The AI returned an invalid result"`. Nothing stored or cached. |
| **AC6** | LLM provider timeout / unavailable | `503` | `"Nutrition service unavailable"`. UI shows message and stays usable; log unchanged. |
| **AC7** | Missing/invalid session on `/estimate` or `/entries`; wrong login password | `401` | Unauthorized. |
| **AC7** | User B deletes User A's entry | `404` | Not Found; entry remains in User A's list. |
| **AC8** | Daily total & date boundary | `200` | `GET /entries` returns only entries matching `Clock.today()` and their sum; `DELETE /entries/{id}` updates the total. |

---

## 7. Coding Rules

- Use Python type annotations on all functions, methods, and public interfaces.
- Keep modules strictly separated by responsibility (`main.py` = HTTP/DI, `db.py` = SQLite, `auth.py` = auth/cookies, `providers.py` = `Clock`, `NutritionProvider` & provider/AI-output error classes, `validator.py` = normalization & validation).
- Never call `datetime.now()` or `date.today()` directly in route handlers or business logic; always use the injected `Clock`.
- Never call LLM SDKs outside `app/providers.py`.
- All automated tests must run offline via `uv run pytest` using `StubNutritionProvider` and an injected `Clock`.
