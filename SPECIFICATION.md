# CalorieHunter — Specification v1.0

## 1. Objective and architecture
A small web app for logging meals: the user types a free-text food description ("briós 120 g"), the backend asks an LLM for a structured nutrition estimate, validates and caches it, stores it in the user's daily log and returns it.
- **Frontend** (single page, HTML/JS): login/register form; food input + *Estimate* button; result card (kcal, protein, carbs, fat, confidence, *cached* badge); today's entries with delete and a daily total.
- **Backend** (Python/FastAPI + SQLite): `/register`, `/login`, `/logout`, `/estimate`, `/entries` (GET, DELETE).
- AI access sits behind one provider interface; a deterministic stub provider replaces it in tests and demo mode.

## 2. Roles
- **Guest**: register or log in only.
- **User**: estimate food, view/delete own entries, see own daily total. No admin role.

## 3. Main scenarios
- S1 register/log in
- S2 estimate a food, auto-logged
- S3 repeat a query, served from cache
- S4 review the daily total
- S5 delete an entry

## 4. Acceptance criteria
Verification: **A** = automated test (stub AI), **M** = manual UI check.

1. **Normal estimate (A, M).** Logged-in user submits `150 g chicken breast`; stub returns 248 kcal / 46.5 P / 0 C / 5.4 F / confidence `medium`. Response 200 contains exactly these values, a new entry appears in the list, and the daily total grows by 248 kcal.
2. **Cache hit (A).** After AC1, submitting `150 G Chicken Breast` with extra leading, trailing and inner spaces returns the same values with `cached: true`, the stub call counter stays at 1, and a second entry is logged.
3. **Length boundary (A).** A 200-character description is accepted; a 201-character one returns 400 with "Description must be 1–200 characters", no AI call and no stored entry.
4. **Empty input (A, M).** A whitespace-only description (3 spaces) returns 400, the UI shows an error, no AI call is made and nothing is stored.
5. **Invalid AI output (A).** Stub returns a negative macro, a missing `calories_kcal`, or 900 kcal against macros implying 300 kcal (outside ±20%): response 502 "The AI returned an invalid result"; nothing is stored or cached.
6. **LLM API unavailable (A, M).** Stub raises a timeout: response 503 "Nutrition service unavailable", the UI shows the message and stays usable, the log is unchanged.
7. **Unauthorised access (A).** `/estimate` and `/entries` without a session, and login with a wrong password, return 401; user B deleting user A's entry returns 404 and the entry remains in A's list.
8. **Daily total and date boundary (A; dates seeded via the clock).** With entries of 300 and 450 kcal today and 700 kcal yesterday, today's view lists 2 entries totalling 750 kcal; after deleting the 300 kcal entry the total is 450 kcal.

## 5. Uncertainties and resolutions
- **LLM output is non-deterministic**, so it cannot anchor an acceptance criterion. Resolution: every AC is verified against an injected stub provider; the real LLM runs only in the manual demo, so the app is testable without an AI service.
- **"Today"** = the server's local date, read through an injectable clock so date boundaries are testable.
- Description length is counted in characters **after trimming**.
- **Cache** is global, keyed by normalised text (trim, lowercase, collapse spaces, `120 g`→`120g`); matching is exact, never fuzzy.
- **Macro/energy tolerance** is ±20% (Px4+Cx4+Fx9 vs. kcal): tolerates rounding and fibre, rejects nonsense.
- Hungarian and English input are accepted.
- Duplicate entries are allowed.
- Passwords are hashed; a session cookie is the only auth mechanism. No email verification or password reset.
