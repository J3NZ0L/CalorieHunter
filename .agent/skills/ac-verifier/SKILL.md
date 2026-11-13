---
name: ac-verifier
description: >-
  Use this skill when verifying CalorieHunter against its acceptance criteria
  (AC1–AC8). Runs `uv run pytest -v`, maps tests to AC1–AC8 from
  SPECIFICATION.md and AGENTS.md, and reports a traceability matrix with any gaps.
---

# AC Verifier

Verify that the CalorieHunter test suite passes and provides complete, traceable coverage for acceptance criteria **AC1–AC8**.

## Procedure

1. **Review contracts:**
   Ensure you have checked [SPECIFICATION.md](../../../SPECIFICATION.md) and [AGENTS.md](../../../AGENTS.md) for the exact AC1–AC8 requirements, status codes, and error messages.

2. **Run the test suite:**
   Execute `uv run pytest -v` from the repository root and capture the full output (test node IDs and pass/fail status):
   ```bash
   uv run pytest -v
   ```

3. **Check test isolation:**
   Confirm that tests use `StubNutritionProvider` and an injectable `Clock` rather than live LLM APIs or wall-clock dates.

4. **Map tests to AC1–AC8:**
   Inspect `tests/` and match each test to the corresponding acceptance criterion:
   - **AC1:** Normal estimate (`150 g chicken breast`, 200, exact macros/confidence, `cached: false`, entry logged, daily total increases).
   - **AC2:** Cache hit (case/whitespace/`120 g` normalization, `cached: true`, stub call counter unchanged, second entry logged).
   - **AC3:** Length boundary (200 chars accepted; 201 chars -> 400 `"Description must be 1–200 characters"`, no AI call, no DB write).
   - **AC4:** Empty / whitespace-only input (3 spaces -> 400 `"Description must be 1–200 characters"`, no AI call, no DB write).
   - **AC5:** Invalid AI output (negative macro, missing `calories_kcal`, or outside ±20% of `P*4 + C*4 + F*9` -> 502 `"The AI returned an invalid result"`, nothing stored or cached).
   - **AC6:** LLM API unavailable / timeout (-> 503 `"Nutrition service unavailable"`, log unchanged).
   - **AC7:** Unauthorised access (missing/invalid session on `/estimate` & `/entries` -> 401; wrong login password -> 401; User B deleting User A's entry -> 404 and entry remains).
   - **AC8:** Daily total & date boundary (entries seeded via `Clock` across yesterday/today; `GET /entries` returns only today's entries and sum; `DELETE /entries/{id}` updates total).

5. **Report traceability:**
   Present a table with columns: `AC`, `Requirement`, `Test(s)`, `Status` (`PASS` / `FAIL` / `MISSING`), and `Notes`. Highlight any failing tests, uncovered ACs, or contract mismatches.
