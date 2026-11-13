import sqlite3
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class FixedClock:
    def today(self) -> date:
        return date(2026, 1, 15)

    def now(self) -> datetime:
        return datetime(2026, 1, 15, 12, 0, 0)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path=db_path, clock=FixedClock(), secret="test-secret"))


def test_schema_initialized(client, db_path):
    tables = {r[0] for r in sqlite3.connect(db_path).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "entries", "nutrition_cache"} <= tables


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "CalorieHunter" in r.text


def test_register_hashes_password_and_sets_session(client, db_path):
    r = client.post("/register", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 201 and "session" in r.cookies
    h = sqlite3.connect(db_path).execute("SELECT password_hash FROM users").fetchone()[0]
    assert "secret123" not in h
    assert client.get("/me").json() == {"username": "alice"}


def test_duplicate_register_conflict(client):
    client.post("/register", json={"username": "alice", "password": "secret123"})
    assert client.post("/register", json={"username": "alice", "password": "secret123"}).status_code == 409


def test_login_logout_flow(client):
    client.post("/register", json={"username": "alice", "password": "secret123"})
    client.post("/logout")
    assert client.get("/me").status_code == 401
    assert client.post("/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    assert client.post("/login", json={"username": "alice", "password": "secret123"}).status_code == 200
    assert client.get("/me").status_code == 200


def test_tampered_cookie_rejected(client):
    client.cookies.set("session", "bogus.token")
    assert client.get("/me").status_code == 401
