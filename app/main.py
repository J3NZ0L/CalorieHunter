import os
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, db, validator
from .providers import (
    INVALID_AI_OUTPUT_ERROR,
    UNAVAILABLE_ERROR,
    Clock,
    GeminiNutritionProvider,
    InvalidAIOutputError,
    NutritionEstimate,
    NutritionProvider,
    NutritionUnavailableError,
    StubNutritionProvider,
    SystemClock,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Credentials(BaseModel):
    username: str
    password: str


class EstimateRequest(BaseModel):
    description: str


class EntryResponse(BaseModel):
    id: int
    description: str
    normalized_text: str
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: Literal["low", "medium", "high"]
    cached: bool
    entry_date: str
    created_at: str


class EntriesListResponse(BaseModel):
    date: str
    entries: list[EntryResponse]
    total_kcal: float
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float


class _LazyGeminiProvider:
    def __init__(self) -> None:
        self._inner: GeminiNutritionProvider | None = None

    async def estimate(self, description: str) -> NutritionEstimate:
        if self._inner is None:
            self._inner = GeminiNutritionProvider()
        return await self._inner.estimate(description)


def _build_default_provider() -> NutritionProvider:
    if os.environ.get("CALORIEHUNTER_PROVIDER", "").strip().lower() == "stub":
        return StubNutritionProvider()
    return _LazyGeminiProvider()


def get_conn(request: Request) -> sqlite3.Connection:
    return request.app.state.conn  # type: ignore[no-any-return]


def get_clock(request: Request) -> Clock:
    return request.app.state.clock  # type: ignore[no-any-return]


def get_provider(request: Request) -> NutritionProvider:
    return request.app.state.provider  # type: ignore[no-any-return]


def _row_to_entry(row: sqlite3.Row) -> EntryResponse:
    return EntryResponse(
        id=row["id"],
        description=row["description"],
        normalized_text=row["normalized_text"],
        calories_kcal=row["calories_kcal"],
        protein_g=row["protein_g"],
        carbs_g=row["carbs_g"],
        fat_g=row["fat_g"],
        confidence=row["confidence"],
        cached=bool(row["cached"]),
        entry_date=row["entry_date"],
        created_at=row["created_at"],
    )


def create_app(
    db_path: str | None = None,
    clock: Clock | None = None,
    secret: str | None = None,
    provider: NutritionProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="CalorieHunter")
    conn = db.connect(db_path or os.environ.get("CALORIEHUNTER_DB", "caloriehunter.db"))
    db.init_db(conn)
    app.state.conn = conn
    app.state.clock = clock or SystemClock()
    app.state.secret = secret or os.environ.get("SESSION_SECRET") or os.urandom(32).hex()
    app.state.provider = provider if provider is not None else _build_default_provider()

    def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> sqlite3.Row:
        user_id = auth.verify_session_token(
            request.app.state.secret, request.cookies.get(auth.SESSION_COOKIE)
        )
        user = db.get_user_by_id(conn, user_id) if user_id is not None else None
        if user is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return user

    def set_session(request: Request, response: Response, user_id: int) -> None:
        response.set_cookie(
            auth.SESSION_COOKIE,
            auth.make_session_token(request.app.state.secret, user_id),
            httponly=True,
            samesite="lax",
            max_age=auth.SESSION_TTL,
        )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/register", status_code=201)
    def register(
        creds: Credentials,
        request: Request,
        response: Response,
        conn: sqlite3.Connection = Depends(get_conn),
        clock: Clock = Depends(get_clock),
    ) -> dict[str, str]:
        username = creds.username.strip()
        if not (1 <= len(username) <= 50) or len(creds.password) < 6:
            raise HTTPException(status_code=400, detail="Invalid username or password (min 6 chars)")
        if db.get_user_by_username(conn, username):
            raise HTTPException(status_code=409, detail="Username already taken")
        user_id = db.create_user(conn, username, auth.hash_password(creds.password), clock.now().isoformat())
        set_session(request, response, user_id)
        return {"username": username}

    @app.post("/login")
    def login(
        creds: Credentials,
        request: Request,
        response: Response,
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, str]:
        user = db.get_user_by_username(conn, creds.username.strip())
        if user is None or not auth.verify_password(creds.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Unauthorized")
        set_session(request, response, user["id"])
        return {"username": user["username"]}

    @app.post("/logout")
    def logout(response: Response) -> dict[str, str]:
        response.delete_cookie(auth.SESSION_COOKIE)
        return {"detail": "Logged out"}

    @app.get("/me")
    def me(user: sqlite3.Row = Depends(current_user)) -> dict[str, str]:
        return {"username": user["username"]}

    @app.post("/estimate", response_model=EntryResponse)
    async def estimate(
        body: EstimateRequest,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_conn),
        clock: Clock = Depends(get_clock),
        provider: NutritionProvider = Depends(get_provider),
    ) -> EntryResponse:
        try:
            trimmed = validator.validate_description(body.description)
        except validator.InvalidDescriptionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        normalized = validator.normalize_text(trimmed)
        today_str = clock.today().isoformat()
        now_str = clock.now().isoformat()

        cached_row = db.get_cached_nutrition(conn, normalized)
        if cached_row is not None:
            entry_row = db.create_entry(
                conn,
                user_id=user["id"],
                description=trimmed,
                normalized_text=normalized,
                calories_kcal=cached_row["calories_kcal"],
                protein_g=cached_row["protein_g"],
                carbs_g=cached_row["carbs_g"],
                fat_g=cached_row["fat_g"],
                confidence=cached_row["confidence"],
                cached=True,
                entry_date=today_str,
                created_at=now_str,
            )
            return _row_to_entry(entry_row)

        try:
            raw_est = await provider.estimate(trimmed)
            raw_payload: Any = raw_est.model_dump() if isinstance(raw_est, BaseModel) else raw_est
            if not isinstance(raw_payload, Mapping):
                raise InvalidAIOutputError(INVALID_AI_OUTPUT_ERROR)
            validated = validator.validate_estimate(raw_payload)
        except InvalidAIOutputError as exc:
            raise HTTPException(status_code=502, detail=INVALID_AI_OUTPUT_ERROR) from exc
        except NutritionUnavailableError as exc:
            raise HTTPException(status_code=503, detail=UNAVAILABLE_ERROR) from exc

        try:
            db.save_cached_nutrition(
                conn,
                normalized_text=normalized,
                calories_kcal=validated.calories_kcal,
                protein_g=validated.protein_g,
                carbs_g=validated.carbs_g,
                fat_g=validated.fat_g,
                confidence=validated.confidence,
                created_at=now_str,
                commit=False,
            )
            entry_row = db.create_entry(
                conn,
                user_id=user["id"],
                description=trimmed,
                normalized_text=normalized,
                calories_kcal=validated.calories_kcal,
                protein_g=validated.protein_g,
                carbs_g=validated.carbs_g,
                fat_g=validated.fat_g,
                confidence=validated.confidence,
                cached=False,
                entry_date=today_str,
                created_at=now_str,
                commit=True,
            )
        except Exception:
            conn.rollback()
            raise
        return _row_to_entry(entry_row)

    @app.get("/entries", response_model=EntriesListResponse)
    def get_entries(
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_conn),
        clock: Clock = Depends(get_clock),
    ) -> EntriesListResponse:
        today_str = clock.today().isoformat()
        rows = db.list_entries_for_date(conn, user["id"], today_str)
        entries = [_row_to_entry(row) for row in rows]
        return EntriesListResponse(
            date=today_str,
            entries=entries,
            total_kcal=round(sum(e.calories_kcal for e in entries), 4),
            total_protein_g=round(sum(e.protein_g for e in entries), 4),
            total_carbs_g=round(sum(e.carbs_g for e in entries), 4),
            total_fat_g=round(sum(e.fat_g for e in entries), 4),
        )

    @app.delete("/entries/{entry_id}")
    def delete_entry(
        entry_id: int,
        user: sqlite3.Row = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_conn),
    ) -> dict[str, int | str]:
        if not db.delete_entry(conn, entry_id, user["id"]):
            raise HTTPException(status_code=404, detail="Entry not found")
        return {"detail": "Entry deleted", "id": entry_id}

    return app


def _default_app() -> FastAPI:
    load_dotenv()
    return create_app()


if "uvicorn" in sys.modules or os.environ.get("CALORIEHUNTER_EAGER"):
    app = _default_app()
