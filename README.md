# CalorieHunter

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

## Documentation

### AI Usage

The documentation of my use of AI can be found here:

[AI_USAGE.md](docs/AI_USAGE.md)

