# Tech Stack

- Python >=3.12, managed exclusively with `uv`
- FastAPI + uvicorn; SQLite (parameterized SQL only)
- `google-genai` for the real LLM provider (only inside `app/providers.py`)
- Single-page HTML/JS frontend (`static/index.html`)
- pytest + httpx; offline tests via `StubNutritionProvider` and injectable `Clock`
