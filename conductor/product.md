# CalorieHunter — Product Definition

A small web app for logging meals: the user types a free-text food description
(Hungarian or English, e.g. "briós 120 g"), the backend asks an LLM for a
structured nutrition estimate, validates and caches it, stores it in the user's
daily log and returns it.

- Roles: Guest (register/login) and User (estimate, view/delete own entries, daily total).
- AI access sits behind a single provider interface; a deterministic stub replaces it in tests/demo.
- Authoritative requirements: `SPECIFICATION.md` (AC1–AC8) and `AGENTS.md`.
