import sqlite3
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import (
    INVALID_AI_OUTPUT_ERROR,
    UNAVAILABLE_ERROR,
    StubNutritionProvider,
)
from app.validator import DESCRIPTION_ERROR

CHICKEN = {
    "calories_kcal": 248,
    "protein_g": 46.5,
    "carbs_g": 0,
    "fat_g": 5.4,
    "confidence": "medium",
}


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def set(self, current: datetime) -> None:
        self._current = current

    def today(self) -> date:
        return self._current.date()

    def now(self) -> datetime:
        return self._current


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 1, 15, 12, 0, 0))


@pytest.fixture
def stub() -> StubNutritionProvider:
    return StubNutritionProvider(default=CHICKEN)


@pytest.fixture
def app(db_path: str, clock: MutableClock, stub: StubNutritionProvider):
    return create_app(db_path=db_path, clock=clock, secret="test-secret", provider=stub)


@pytest.fixture
def client(app) -> TestClient:
    c = TestClient(app)
    r = c.post("/register", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 201
    return c


def test_ac1_normal_estimate_logs_entry_and_updates_total(
    client: TestClient, stub: StubNutritionProvider
):
    r = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert r.status_code == 200
    body = r.json()
    assert body["calories_kcal"] == 248
    assert body["protein_g"] == 46.5
    assert body["carbs_g"] == 0
    assert body["fat_g"] == 5.4
    assert body["confidence"] == "medium"
    assert body["cached"] is False
    assert stub.call_count == 1

    entries_resp = client.get("/entries")
    assert entries_resp.status_code == 200
    data = entries_resp.json()
    assert data["total_kcal"] == 248
    assert len(data["entries"]) == 1
    assert data["entries"][0]["description"] == "150 g chicken breast"
    assert data["entries"][0]["cached"] is False


def test_ac2_cache_hit_normalizes_skips_provider_and_logs_second_entry(
    app, client: TestClient, stub: StubNutritionProvider
):
    first = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert first.status_code == 200
    assert stub.call_count == 1

    second = client.post("/estimate", json={"description": "  150  G  Chicken Breast "})
    assert second.status_code == 200
    body = second.json()
    assert body["calories_kcal"] == 248
    assert body["protein_g"] == 46.5
    assert body["carbs_g"] == 0
    assert body["fat_g"] == 5.4
    assert body["confidence"] == "medium"
    assert body["cached"] is True
    assert stub.call_count == 1

    data = client.get("/entries").json()
    assert len(data["entries"]) == 2
    assert data["total_kcal"] == 496

    # Cache is global across users
    other = TestClient(app)
    assert other.post("/register", json={"username": "bob", "password": "secret123"}).status_code == 201
    other_est = other.post("/estimate", json={"description": "150 g chicken breast"})
    assert other_est.status_code == 200
    assert other_est.json()["cached"] is True
    assert stub.call_count == 1


def test_ac3_length_boundary(client: TestClient, stub: StubNutritionProvider, db_path: str):
    ok = client.post("/estimate", json={"description": "a" * 200})
    assert ok.status_code == 200
    assert stub.call_count == 1

    too_long = client.post("/estimate", json={"description": "b" * 201})
    assert too_long.status_code == 400
    assert too_long.json()["detail"] == DESCRIPTION_ERROR == "Description must be 1–200 characters"
    assert stub.call_count == 1

    count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert count == 1


@pytest.mark.parametrize("raw", ["", "   "])
def test_ac4_empty_and_whitespace_rejected(
    raw: str, client: TestClient, stub: StubNutritionProvider, db_path: str
):
    r = client.post("/estimate", json={"description": raw})
    assert r.status_code == 400
    assert r.json()["detail"] == DESCRIPTION_ERROR == "Description must be 1–200 characters"
    assert stub.call_count == 0
    count = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert count == 0


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"calories_kcal": 248, "protein_g": -5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"},
        {"protein_g": 46.5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"},
        {"calories_kcal": 900, "protein_g": 30, "carbs_g": 45, "fat_g": 0, "confidence": "low"},
    ],
)
def test_ac5_invalid_ai_output_returns_502_without_storing_or_caching(
    bad_payload: dict, db_path: str, clock: MutableClock
):
    stub = StubNutritionProvider(default=bad_payload)
    app = create_app(db_path=db_path, clock=clock, secret="test-secret", provider=stub)
    c = TestClient(app)
    c.post("/register", json={"username": "alice", "password": "secret123"})

    r = c.post("/estimate", json={"description": "150 g chicken breast"})
    assert r.status_code == 502
    assert r.json()["detail"] == INVALID_AI_OUTPUT_ERROR == "The AI returned an invalid result"

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nutrition_cache").fetchone()[0] == 0


def test_ac6_provider_unavailable_returns_503_and_app_stays_usable(
    client: TestClient, stub: StubNutritionProvider, db_path: str
):
    stub.mode = "timeout"
    r = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert r.status_code == 503
    assert r.json()["detail"] == UNAVAILABLE_ERROR == "Nutrition service unavailable"

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nutrition_cache").fetchone()[0] == 0

    # Service recovers and client remains usable
    stub.mode = "ok"
    r2 = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert r2.status_code == 200
    assert r2.json()["cached"] is False


def test_ac7_unauthorized_and_cross_user_isolation(app):
    anon = TestClient(app)
    assert anon.post("/estimate", json={"description": "apple"}).status_code == 401
    assert anon.get("/entries").status_code == 401
    assert anon.delete("/entries/1").status_code == 401

    user_a = TestClient(app)
    assert user_a.post("/register", json={"username": "alice", "password": "secret123"}).status_code == 201
    assert user_a.post("/login", json={"username": "alice", "password": "wrong"}).status_code == 401

    est = user_a.post("/estimate", json={"description": "150 g chicken breast"})
    assert est.status_code == 200
    entry_id = est.json()["id"]

    user_b = TestClient(app)
    assert user_b.post("/register", json={"username": "bob", "password": "secret123"}).status_code == 201
    assert user_b.delete(f"/entries/{entry_id}").status_code == 404

    a_entries = user_a.get("/entries").json()["entries"]
    assert len(a_entries) == 1 and a_entries[0]["id"] == entry_id


def test_ac8_daily_total_date_boundary_and_delete(db_path: str):
    clock = MutableClock(datetime(2026, 1, 14, 18, 0, 0))
    stub = StubNutritionProvider(
        responses={
            "dinner yesterday": {"calories_kcal": 700, "protein_g": 40, "carbs_g": 80, "fat_g": 24, "confidence": "medium"},
            "oatmeal": {"calories_kcal": 300, "protein_g": 10, "carbs_g": 50, "fat_g": 6, "confidence": "high"},
            "salad bowl": {"calories_kcal": 450, "protein_g": 30, "carbs_g": 35, "fat_g": 20, "confidence": "medium"},
        }
    )
    app = create_app(db_path=db_path, clock=clock, secret="test-secret", provider=stub)
    c = TestClient(app)
    assert c.post("/register", json={"username": "alice", "password": "secret123"}).status_code == 201

    assert c.post("/estimate", json={"description": "dinner yesterday"}).status_code == 200

    clock.set(datetime(2026, 1, 15, 9, 0, 0))
    r1 = c.post("/estimate", json={"description": "oatmeal"})
    assert r1.status_code == 200
    oatmeal_id = r1.json()["id"]

    clock.set(datetime(2026, 1, 15, 13, 0, 0))
    r2 = c.post("/estimate", json={"description": "salad bowl"})
    assert r2.status_code == 200

    today_view = c.get("/entries").json()
    assert today_view["date"] == "2026-01-15"
    assert len(today_view["entries"]) == 2
    assert today_view["total_kcal"] == 750

    del_resp = c.delete(f"/entries/{oatmeal_id}")
    assert del_resp.status_code == 200

    after_delete = c.get("/entries").json()
    assert len(after_delete["entries"]) == 1
    assert after_delete["total_kcal"] == 450


def test_ui_serves_all_required_elements(client: TestClient):
    html = client.get("/").text
    for marker in (
        'id="auth-form"',
        'id="estimate-form"',
        'id="food-input"',
        'id="estimate-btn"',
        'id="result-card"',
        'id="res-cached"',
        'id="entries-list"',
        'id="daily-total"',
        'id="app-error"',
        "/estimate",
        "/entries",
    ):
        assert marker in html
