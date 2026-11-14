import os
import sqlite3
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, db
from .providers import Clock, GeminiNutritionProvider, NutritionProvider, StubNutritionProvider, SystemClock
from .validator import (
    DESCRIPTION_ERROR,
    normalize_description,
    validate_description,
    validate_nutrition_result,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Credentials(BaseModel):
    username: str
    password: str


class EstimateRequest(BaseModel):
    description: str


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
    app.state.provider = provider or (
        GeminiNutritionProvider() if os.environ.get("GEMINI_API_KEY") else StubNutritionProvider()
    )

    def get_conn(request: Request) -> sqlite3.Connection:
        return request.app.state.conn  # type: ignore[no-any-return]

    def get_clock(request: Request) -> Clock:
        return request.app.state.clock  # type: ignore[no-any-return]

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

    @app.post("/estimate")
    def estimate(
        payload: EstimateRequest,
        request: Request,
        user: sqlite3.Row = Depends(current_user),
        clock: Clock = Depends(get_clock),
    ) -> dict[str, object]:
        description = payload.description
        if not validate_description(description):
            raise HTTPException(status_code=400, detail=DESCRIPTION_ERROR)
        normalized = normalize_description(description)
        cached = conn.execute(
            "SELECT calories_kcal, protein_g, carbs_g, fat_g, confidence "
            "FROM nutrition_cache WHERE normalized_text = ?",
            (normalized,),
        ).fetchone()
        is_cached = cached is not None
        if cached is None:
            try:
                nutrition = request.app.state.provider.estimate(description.strip())
            except ValueError:
                raise HTTPException(status_code=502, detail="The AI returned an invalid result")
            except (TimeoutError, ConnectionError):
                raise HTTPException(status_code=503, detail="Nutrition service unavailable")
            except Exception:
                raise HTTPException(status_code=503, detail="Nutrition service unavailable")
            if not validate_nutrition_result(nutrition):
                raise HTTPException(status_code=502, detail="The AI returned an invalid result")
            values = (
                float(nutrition["calories_kcal"]),
                float(nutrition["protein_g"]),
                float(nutrition["carbs_g"]),
                float(nutrition["fat_g"]),
                str(nutrition.get("confidence", "medium")),
            )
            conn.execute(
                "INSERT INTO nutrition_cache "
                "(normalized_text, calories_kcal, protein_g, carbs_g, fat_g, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (normalized, *values, clock.now().isoformat()),
            )
        else:
            values = tuple(
                cached[key]
                for key in ("calories_kcal", "protein_g", "carbs_g", "fat_g", "confidence")
            )
        conn.execute(
            "INSERT INTO entries "
            "(user_id, description, normalized_text, calories_kcal, protein_g, carbs_g, fat_g, "
            "confidence, cached, entry_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user["id"],
                description.strip(),
                normalized,
                *values,
                int(is_cached),
                clock.today().isoformat(),
                clock.now().isoformat(),
            ),
        )
        conn.commit()
        return {
            "description": description.strip(),
            "calories_kcal": values[0],
            "protein_g": values[1],
            "carbs_g": values[2],
            "fat_g": values[3],
            "confidence": values[4],
            "cached": is_cached,
        }

    @app.get("/entries")
    def entries(
        user: sqlite3.Row = Depends(current_user),
        clock: Clock = Depends(get_clock),
    ) -> dict[str, object]:
        rows = conn.execute(
            "SELECT id, description, calories_kcal, protein_g, carbs_g, fat_g, confidence, cached, created_at "
            "FROM entries WHERE user_id = ? AND entry_date = ? ORDER BY id",
            (user["id"], clock.today().isoformat()),
        ).fetchall()
        result = [dict(row) for row in rows]
        return {
            "entries": result,
            "total_calories_kcal": sum(row["calories_kcal"] for row in result),
        }

    @app.delete("/entries/{entry_id}")
    def delete_entry(entry_id: int, user: sqlite3.Row = Depends(current_user)) -> dict[str, str]:
        cursor = conn.execute(
            "DELETE FROM entries WHERE id = ? AND user_id = ?", (entry_id, user["id"])
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Entry not found")
        return {"detail": "Entry deleted"}

    return app


def _default_app() -> FastAPI:
    return create_app()


if "uvicorn" in sys.modules or os.environ.get("CALORIEHUNTER_EAGER"):
    app = _default_app()
