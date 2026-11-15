# AI usage documentation

The chosen development phases were the proposed ones:
- design,
- implementation,
- and testing.

The detailed usage regarding the chosen three decision cases in the specific phases can be read below.

## Design

### Decision case 1

#### The problem
Making non-deterministic LLM outputs and date boundaries (like `today` vs `yesterday`) completely determninistic in the unit tests.

#### Solution
The model I interacted with, proposed utilizing **dependency injection overrides** in the tests, while using working production LLM and time providers in production - specifically, the FastAPI `Depends()` function, by defining `get_provider()` and `get_clock()` methods and test overrides.

#### Verdict and reasoning
I accepted this proposal, because I knew this functionality available in FastAPI, and have already used it in the past, so I was familiar with the approach of dependency injection, and this exact implementation as well. In short, I think it is the technologically correct approach, because it does not require modifying runtime state untraceably via reaching into a module and overriding the result of a core function manually, rather, it involves defining a clearly distinctive method that will be used instead of the production equivalents at test time. I also briefly investigated alternative approaches, like the well-known "monkeypatching" approach in dynamic programming languages like python, where I would "manually" override a function or attribute at runtime. This latter approach would introduce clear code-maintainability issues and it is also hard to use when the type of object to override would be a built in C type.

For these reasons, I was happy to accept the proposed dependency injection override approach.

#### Tools used
- Claude Opus 5.5 via Claude Code CLI

#### Relevant context
- A draft of the [specification](/SPECIFICATION.md)

#### Verification Evidence :
- Code reference: Implemented in [app/providers.py](/app/providers.py) (`Clock`, `SystemClock`, `NutritionProvider`, `StubNutritionProvider`, `GeminiNutritionProvider`) and wired via `create_app()` and FastAPI `Depends(get_clock)` in [app/main.py](/app/main.py), as specified in [AGENTS.md](/AGENTS.md).
- Test reference: Utilized by `FixedClock` injected into `create_app()` in [tests/test_smoke.py](/tests/test_smoke.py) and by `StubNutritionProvider` and the injected fake Gemini client in [tests/test_providers.py](/tests/test_providers.py).
- Execution result: Running `uv run pytest -v` executes all 46 tests completely offline and deterministically (`46 passed in 0.62s`), without making any live network calls or depending on the system wall clock.

## Implementation

### Decision case 2

#### The problem
Normalizing free-text food descriptions for caching (like turning `120 g` into `120g`, collapsing spaces, and lowercasing), and validating the LLM's nutrition output against the 20% macro-to-calorie tolerance formula (`4*P + 4*C + 9*F`) without running into edge-case bugs like division by zero on zero-calorie items or circular imports between the validator and provider modules.

#### Solution
I gave almost the same prompt to both Antigravity and GitHub Copilot to implement the validator, normalizer, and the LLM providers (`StubNutritionProvider` and `GeminiNutritionProvider`). Antigravity proposed a two-step regex in `normalize_text()` (`\s+` and `(\d(?:[.,]\d+)?) g\b`), a strict `validate_estimate()` function that checks field types, confidence values, and the 20% tolerance using multiplication (`abs(kcal - expected) <= 0.20 * expected` with an explicit `if expected == 0: consistent = kcal == 0` branch), and placed the shared error classes in `app/providers.py` alongside an async Gemini provider. Copilot proposed a lookaround regex (`(?<=\d)\s+(?=(?:g|kg|mg|ml|l)\b)`), a simpler boolean validator using `float(result[key])` with the same zero-calorie check, synchronous providers, and also went ahead and implemented the HTTP routes in `app/main.py`.

#### Verdict and reasoning
I decided to accept the Antigravity implementation as the main solution, though a mixed selection taking Copilot's regex would actually be the ideal combination. Antigravity's validator and provider implementation is much more solid technically: in Python, `bool` is a subclass of `int`, so Copilot's `float(result[key])` silently accepts `True` and `False` as `1.0` and `0.0`, and Copilot completely forgot to validate the `confidence` field. Antigravity also properly implemented `estimate()` as an `async` method with `asyncio.wait_for` timeouts and separated 502 vs 503 error classes, whereas Copilot used synchronous calls that would block FastAPI's event loop. On the other hand, Copilot's lookaround regex for unit normalization is cleaner and also strips spaces before `kg`, `mg`, `ml`, and `l`, while Antigravity only handles `g`.

Even though both tools avoided the zero-calorie division-by-zero trap by multiplying instead of dividing, both implementations still lack some edge-case logic, which shows the limitations of this validation method. First, because of standard IEEE 754 floating-point precision, writing `abs(kcal - expected) <= 0.20 * expected` falsely rejects exact 20% boundaries on certain numbers (for example, 1g of fat implies 9 kcal, and an exact +20% value of 10.8 kcal gives `abs(10.8 - 9.0) = 1.8000000000000007 > 1.8`). Second, requiring `kcal == 0` when macros are 0 rejects real low-calorie foods where macros round to zero (like black coffee with 3 kcal and 0g macros), and the formula ignores fiber (2 kcal/g) and alcohol (7 kcal/g). Finally, neither normalizer converts Hungarian decimal commas to dots (`1,5 g` becomes `1,5g` while `1.5 g` becomes `1.5g`), so identical quantities written with different decimal separators miss the cache.

#### Dual-tool comparison
Comparing the two outputs side by side, Antigravity respected the task boundaries (`app/validator.py` and `app/providers.py`) and generated 37 unit tests covering boundaries, NaN/infinity, booleans, bad confidence, and provider failure modes, while Copilot wrote zero tests and leaked raw SQL into `app/main.py`.

Regarding the two working methods, providing Antigravity with `AGENTS.md` and the Conductor plugin (enforcing SDD and TDD) kept the agent strictly within the planned module scope and forced it to verify edge cases through failing tests first. In contrast, running GitHub Copilot with just the prompt and no SDD/TDD guardrails resulted in faster one-shot scaffolding, but left behind silent validation gaps and untested code.

#### Tools used
- Google Antigravity CLI (with Conductor plugin)
- GitHub Copilot

#### Relevant context
- [SPECIFICATION.md](/SPECIFICATION.md)
- [AGENTS.md](/AGENTS.md) (provided only to Antigravity)
- Conductor track files in [conductor/tracks/validator_providers_20261113/](/conductor/tracks/validator_providers_20261113/spec.md) (used only with Antigravity)

#### Verification Evidence :
- Code reference: Implemented in [app/validator.py](/app/validator.py) and [app/providers.py](/app/providers.py) (compared against Copilot's version in [app/docs/comparison/validator_copilot.py](/app/docs/comparison/validator_copilot.py) and branch `validator-normalizer-and-llm-provider-copilot`).
- Test reference: Utilized by unit tests in [tests/test_validator.py](/tests/test_validator.py) and [tests/test_providers.py](/tests/test_providers.py).
- Execution result: Running `uv run pytest -v` passes all 43 tests (`43 passed in 0.60s`). Running targeted Python checks confirmed that Antigravity rejects `{"calories_kcal": 4, "protein_g": True, "carbs_g": False, "fat_g": False, "confidence": "low"}` and `confidence="super_high"` while Copilot passes both, and that both reject the exact +20% float boundary `{"calories_kcal": 10.8, "protein_g": 0, "carbs_g": 0, "fat_g": 1, "confidence": "low"}`.

## Testing

### Decision case 3

#### The problem
Verifying that the acceptance tests generated by Antigravity in [tests/test_acceptance.py](/tests/test_acceptance.py) actually test the boundary conditions accurately, and not just pass - mainly that the 200 vs 201 character limit is counted *after trimming* the leading/trailing spaces, and that a cross-user delete returns `404` while User A's entry still exists in the database.

#### Solution
I went through the assertions one by one with Claude, and compared them against the code they actually exercise (`validate_description()` in `app/validator.py`, `db.delete_entry()` with its `WHERE id = ? AND user_id = ?` query, and the routes in `app/main.py`) and against AC1-AC8 in the specification. The generated tests were mostly correct, but there were some gaps: AC3 never tested a padded 201 character input and never checked the `nutrition_cache` table after a rejected request, AC7 only checked User A's entry through the API and not directly in the DB, and AC8 used 18:00 and 09:00 as the date boundary instead of an actual midnight crossing.

So I added the missing assertions: in AC3 a padded 201 character input that has to be rejected, no cache/entry writes on rejection, checking that the padded 200 character input is stored trimmed, a 1 character lower bound and a `"á" * 200` check (so it counts characters and not bytes, which matters for Hungarian input). In AC7 a direct SQL check before and after Bob's `DELETE` that the row still exists and still belongs to Alice, plus a nonexistent id also giving `404`, a forged cookie delete giving `401`, and Bob's list being empty. In AC8 the clock now goes from 23:59:59 to 00:00:00.

To prove that the tests actually catch a real defect, I also introduced a deliberate fault behind the `CALORIEHUNTER_SIMULATE_FAULT=1` environment variable, where the length is checked on the raw text before `.strip()`.

#### Verdict and reasoning
I accepted the AI-generated tests, with the refinements above. The main boundary logic was actually already correct, since Antigravity's AC3 already had a padded 200 character case (`"  " + 200 chars + "  "` has to be accepted), and AC4 already had the `"   "` case. These padded inputs are the only ones that can tell apart "trim then measure" from "measure then trim", because the plain `"a" * 200` / `"b" * 201` pair passes with both versions. The faulty run confirmed this as well - the unpadded 200/201 assertions still passed, and the original padded 200 and `"   "` assertions failed. So my additions did not catch this specific fault, rather they closed the remaining gaps. For AC7 in particular, I think the direct SQL check is important, because an API-only check relies on the same application code that it is supposed to verify.

#### Tools used
- Google Antigravity CLI (with Conductor plugin - generated the acceptance tests)
- Claude Opus 5.5 via Claude Code CLI (reviewing the assertions, refinements and the fault demo)

#### Relevant context
- [SPECIFICATION.md](/SPECIFICATION.md)
- [AGENTS.md](/AGENTS.md)

#### Verification Evidence :
- Code reference: The faulty and corrected versions are both in `validate_description()` in [app/validator.py](/app/validator.py), see also [docs/defect_demo/README.md](/docs/defect_demo/README.md).
- Test reference: `test_ac3_length_boundary`, `test_ac7_unauthorised_access` and `test_ac8_daily_total_and_date_boundary` in [tests/test_acceptance.py](/tests/test_acceptance.py).
- Execution result: Running `CALORIEHUNTER_SIMULATE_FAULT=1 uv run pytest -v -p no:cacheprovider` gives `5 failed, 61 passed` (AC3 fails with `assert 400 == 200` on the padded 200 input, AC4 fails with `assert 200 == 400` on `"   "`, plus three unit/API tests), the output is saved in [test_run_faulty.txt](/docs/defect_demo/test_run_faulty.txt). Running `uv run pytest -v -p no:cacheprovider` without the fault passes all 66 tests (`66 passed`), the output is saved in [test_run_corrected.txt](/docs/defect_demo/test_run_corrected.txt).
