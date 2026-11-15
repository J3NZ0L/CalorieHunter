# AC verification

Output of the [ac-verifier](/.agent/skills/ac-verifier/SKILL.md) skill, run in Google Antigravity CLI (Gemini 4 Hydrogen) with `/ac-verifier Use the ac-verifier skill to verify the test suite against AC1–AC8, and report the traceability matrix. Do not modify or commit anything.`

I checked the claims against the tests, and they are correct, with one small inaccuracy: in AC8, only `test_acceptance.py` crosses midnight (`23:59:59` -> `00:00:00`), `test_api.py` goes from 18:00 to 09:00 the next day, not midday. Also, the skill only checks that every AC has passing tests, not that the assertions would actually catch a defect - that is what the [defect demo](/docs/defect_demo/README.md) is for.

---

Verification of CalorieHunter against acceptance criteria **AC1–AC8** from [SPECIFICATION.md](/SPECIFICATION.md) and [AGENTS.md](/AGENTS.md) is complete. No files were modified or committed.

### 1. Test Suite Execution
Command: `uv run pytest -v`
- **Result:** **66 passed** in 4.05s (exit code `0`)
  - [test_acceptance.py](/tests/test_acceptance.py): 8/8 passed
  - [test_api.py](/tests/test_api.py): 12/12 passed
  - [test_providers.py](/tests/test_providers.py): 15/15 passed
  - [test_smoke.py](/tests/test_smoke.py): 6/6 passed
  - [test_validator.py](/tests/test_validator.py): 25/25 passed

### 2. Test Isolation Check
- **Provider isolation:** Acceptance and API tests ([test_acceptance.py](/tests/test_acceptance.py#L44-L55), [test_api.py](/tests/test_api.py#L48-L55)) inject `StubNutritionProvider`; [test_providers.py](/tests/test_providers.py#L67-L105) uses an in-memory `FakeModels` stub for `GeminiNutritionProvider`; [test_smoke.py](/tests/test_smoke.py) does not call `/estimate`. No live LLM API calls are made.
- **Clock & DB isolation:** Tests inject `SeededClock`, `MutableClock`, or `FixedClock` implementations of `Clock` and use per-test SQLite databases under pytest's `tmp_path`.

### 3. Traceability Matrix (AC1–AC8)

| AC | Requirement | Test(s) | Status | Notes |
|---|---|---|---|---|
| **AC1** | Normal estimate (`150 g chicken breast`, 200, 248 kcal / 46.5 P / 0 C / 5.4 F / `medium`, `cached: false`, entry logged, daily total grows by 248) | [test_ac1_normal_estimate](/tests/test_acceptance.py#L88-L115), [test_ac1_normal_estimate_logs_entry_and_updates_total](/tests/test_api.py#L66-L86) | PASS | Exact values, `cached: false`, `stub.call_count == 1`, and entry/total update verified. |
| **AC2** | Cache hit (case/whitespace/`120 g`→`120g` normalization, `cached: true`, stub call counter stays 1, second entry logged) | [test_ac2_cache_hit](/tests/test_acceptance.py#L118-L145), [test_ac2_cache_hit_normalizes_skips_provider_and_logs_second_entry](/tests/test_api.py#L89-L117), [test_normalize](/tests/test_validator.py#L30-L46) | PASS | Covers repeated normalized query, cross-user global cache hit, `stub.call_count == 1`, 2 entries totalling 496 kcal, and unit normalization rules. |
| **AC3** | Length boundary (200 chars accepted; 201 chars → 400 `"Description must be 1–200 characters"`, no AI call, no DB write) | [test_ac3_length_boundary (acceptance)](/tests/test_acceptance.py#L148-L192), [test_ac3_length_boundary (api)](/tests/test_api.py#L120-L131), [test_description_trimmed_and_bounds](/tests/test_validator.py#L17-L20), [test_description_rejected](/tests/test_validator.py#L23-L27) | PASS | Also verifies trimmed length bounds, 1-char minimum, and Unicode character vs byte counting (`"á" * 200`). |
| **AC4** | Empty / whitespace-only input (3 spaces / empty → 400 `"Description must be 1–200 characters"`, no AI call, no DB write) | [test_ac4_empty_input](/tests/test_acceptance.py#L195-L209), [test_ac4_empty_and_whitespace_rejected](/tests/test_api.py#L134-L143), [test_description_rejected](/tests/test_validator.py#L23-L27), [test_ui_serves_all_required_elements](/tests/test_api.py#L249-L264) | PASS | Backend contract fully tested; UI error rendering is marked `(M)` manual check in `SPECIFICATION.md` (DOM element `#app-error` verified in HTML). |
| **AC5** | Invalid AI output (negative macro, missing `calories_kcal`, or outside ±20% of `P*4+C*4+F*9` → 502 `"The AI returned an invalid result"`, nothing stored/cached) | [test_ac5_invalid_ai_output_and_macro_boundary](/tests/test_acceptance.py#L212-L250), [test_ac5_invalid_ai_output_returns_502_without_storing_or_caching](/tests/test_api.py#L146-L168), [test_stub_missing_field_raises_invalid_output](/tests/test_providers.py#L45-L49), [test_invalid_estimate](/tests/test_validator.py#L54-L72), [test_tolerance_boundary_and_zero](/tests/test_validator.py#L75-L87) | PASS | Covers negative macro, missing `calories_kcal`, `900` vs `300` kcal, and exact ±20% boundaries (`240`/`360` accepted, `239.9`/`360.1` rejected), with 0 rows in `entries` and `nutrition_cache`. |
| **AC6** | LLM API unavailable / timeout (→ 503 `"Nutrition service unavailable"`, log unchanged, app stays usable) | [test_ac6_llm_api_unavailable](/tests/test_acceptance.py#L253-L283), [test_ac6_provider_unavailable_returns_503_and_app_stays_usable](/tests/test_api.py#L171-L187), [test_stub_timeout_and_unavailable_count_calls](/tests/test_providers.py#L37-L42), [test_ui_serves_all_required_elements](/tests/test_api.py#L249-L264) | PASS | Verifies 503 message, unchanged DB/log, and recovery on subsequent request; UI behavior is marked `(M)` manual check in `SPECIFICATION.md`. |
| **AC7** | Unauthorised access (`/estimate`, `/entries`, `/entries/{id}` without session or tampered cookie → 401; wrong login password → 401; User B deleting User A's entry → 404 and entry remains) | [test_ac7_unauthorised_access](/tests/test_acceptance.py#L286-L324), [test_ac7_unauthorized_and_cross_user_isolation](/tests/test_api.py#L190-L209), [test_login_logout_flow](/tests/test_smoke.py#L51-L57), [test_tampered_cookie_rejected](/tests/test_smoke.py#L60-L62) | PASS | Verifies 401s across unauthenticated/forged-cookie/wrong-password paths and DB + API persistence of User A's entry after User B's 404 delete attempt. |
| **AC8** | Daily total & date boundary (entries seeded via `Clock`: 700 kcal yesterday, 300 + 450 kcal today → `GET /entries` returns 2 entries totalling 750 kcal; `DELETE` 300 kcal → 450 kcal) | [test_ac8_daily_total_and_date_boundary](/tests/test_acceptance.py#L327-L365), [test_ac8_daily_total_date_boundary_and_delete](/tests/test_api.py#L212-L246) | PASS | Tests both midday and `23:59:59` → `00:00:00` date boundaries via injected `Clock`, exact sums (750 → 450), and entry count (2 → 1). |

### 4. Gaps & Observations
- **Failing tests:** None (66/66 passed).
- **Uncovered automated ACs / contract mismatches:** None. All automated acceptance criteria (AC1–AC8), exact HTTP status codes (`200`, `400`, `401`, `404`, `502`, `503`), and exact `detail` strings match [SPECIFICATION.md](/SPECIFICATION.md) and [AGENTS.md](/AGENTS.md).
- **Manual checks (`M`):** Per `SPECIFICATION.md`, browser UI rendering/interaction for AC1, AC4, and AC6 is designated as manual verification (`M`); the automated suite verifies that the required UI element IDs and endpoint references are served in `/` ([test_ui_serves_all_required_elements](/tests/test_api.py#L249-L264)).
