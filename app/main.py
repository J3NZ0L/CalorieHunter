import os
import sqlite3
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import auth, db
from .providers import Clock, SystemClock

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Credentials(BaseModel):
    username: str
    password: str


def create_app(
    db_path: str | None = None,
    clock: Clock | None = None,
    secret: str | None = None,
) -> FastAPI:
    app = FastAPI(title="CalorieHunter")
    conn = db.connect(db_path or os.environ.get("CALORIEHUNTER_DB", "caloriehunter.db"))
    db.init_db(conn)
    app.state.conn = conn
    app.state.clock = clock or SystemClock()
    app.state.secret = secret or os.environ.get("SESSION_SECRET") or os.urandom(32).hex()

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

    return app


def _default_app() -> FastAPI:
    return create_app()


if "uvicorn" in sys.modules or os.environ.get("CALORIEHUNTER_EAGER"):
    app = _default_app()
