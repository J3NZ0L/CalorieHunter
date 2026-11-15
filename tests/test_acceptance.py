"""Acceptance tests mapped 1-to-1 to AC1–AC8 in SPECIFICATION.md."""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import (
    INVALID_AI_OUTPUT_ERROR,
    UNAVAILABLE_ERROR,
    StubNutritionProvider,
)
from app.validator import DESCRIPTION_ERROR

CHICKEN_BREAST: dict[str, Any] = {
    "calories_kcal": 248,
    "protein_g": 46.5,
    "carbs_g": 0,
    "fat_g": 5.4,
    "confidence": "medium",
}


class SeededClock:
    """Controllable clock for testing date boundaries without wall-clock dependence."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    def set(self, current: datetime) -> None:
        self._current = current

    def today(self) -> date:
        return self._current.date()

    def now(self) -> datetime:
        return self._current


def _make_app(
    db_path: str,
    *,
    clock: SeededClock | None = None,
    provider: StubNutritionProvider | None = None,
) -> FastAPI:
    return create_app(
        db_path=db_path,
        clock=clock or SeededClock(datetime(2026, 1, 15, 12, 0, 0)),
        secret="acceptance-test-secret",
        provider=provider or StubNutritionProvider(default=CHICKEN_BREAST),
    )


def _register_and_login(app: FastAPI, username: str = "alice", password: str = "secret123") -> TestClient:
    client = TestClient(app)
    resp = client.post("/register", json={"username": username, "password": password})
    assert resp.status_code == 201
    return client


def _table_count(db_path: str, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])


def _user_id(db_path: str, username: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        assert row is not None
        return int(row[0])


def _entry_exists_for(db_path: str, entry_id: int, user_id: int) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE id = ? AND user_id = ?", (entry_id, user_id)
        ).fetchone()
        assert row is not None
        return int(row[0]) == 1


def test_ac1_normal_estimate(tmp_path: Path) -> None:
    """AC1 — Normal case: normal food estimate returns exact macros, logs entry, and updates daily total."""
    db_path = str(tmp_path / "ac1.db")
    stub = StubNutritionProvider(default=CHICKEN_BREAST)
    app = _make_app(db_path, provider=stub)
    client = _register_and_login(app)

    before = client.get("/entries")
    assert before.status_code == 200
    assert before.json()["total_kcal"] == 0

    resp = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["calories_kcal"] == 248
    assert body["protein_g"] == 46.5
    assert body["carbs_g"] == 0
    assert body["fat_g"] == 5.4
    assert body["confidence"] == "medium"
    assert body["cached"] is False
    assert stub.call_count == 1

    after = client.get("/entries")
    assert after.status_code == 200
    data = after.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["description"] == "150 g chicken breast"
    assert data["total_kcal"] == 248


def test_ac2_cache_hit(tmp_path: Path) -> None:
    """AC2 — Cache hit: normalized repeat query skips provider, sets cached=true, and logs a second entry."""
    db_path = str(tmp_path / "ac2.db")
    stub = StubNutritionProvider(default=CHICKEN_BREAST)
    app = _make_app(db_path, provider=stub)
    client = _register_and_login(app)

    first = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert stub.call_count == 1

    second = client.post("/estimate", json={"description": "  150  G   Chicken   Breast "})
    assert second.status_code == 200
    body = second.json()
    assert body["calories_kcal"] == 248
    assert body["protein_g"] == 46.5
    assert body["carbs_g"] == 0
    assert body["fat_g"] == 5.4
    assert body["confidence"] == "medium"
    assert body["cached"] is True
    assert stub.call_count == 1

    entries_resp = client.get("/entries")
    assert entries_resp.status_code == 200
    data = entries_resp.json()
    assert len(data["entries"]) == 2
    assert data["total_kcal"] == 496


def test_ac3_length_boundary(tmp_path: Path) -> None:
    """AC3 — Boundary edge case (200 vs 201 chars): 200 trimmed chars accepted; 201 rejected with 400 and no AI/DB work."""
    db_path = str(tmp_path / "ac3.db")
    stub = StubNutritionProvider(default=CHICKEN_BREAST)
    app = _make_app(db_path, provider=stub)
    client = _register_and_login(app)

    ok = client.post("/estimate", json={"description": "a" * 200})
    assert ok.status_code == 200
    assert stub.call_count == 1
    assert _table_count(db_path, "entries") == 1
    assert _table_count(db_path, "nutrition_cache") == 1

    too_long = client.post("/estimate", json={"description": "b" * 201})
    assert too_long.status_code == 400
    assert too_long.json()["detail"] == DESCRIPTION_ERROR == "Description must be 1–200 characters"
    assert stub.call_count == 1
    assert _table_count(db_path, "entries") == 1
    assert _table_count(db_path, "nutrition_cache") == 1

    # Trimmed length is what counts toward the 200-character limit:
    # 204 raw chars that trim to exactly 200 must be accepted and stored trimmed.
    padded_ok = client.post("/estimate", json={"description": "  " + ("c" * 200) + "  "})
    assert padded_ok.status_code == 200
    assert padded_ok.json()["description"] == "c" * 200
    assert stub.call_count == 2
    assert _table_count(db_path, "entries") == 2

    # ...and 205 raw chars that trim to 201 must still be rejected.
    padded_too_long = client.post("/estimate", json={"description": "  " + ("d" * 201) + "  "})
    assert padded_too_long.status_code == 400
    assert padded_too_long.json()["detail"] == DESCRIPTION_ERROR
    assert stub.call_count == 2
    assert _table_count(db_path, "entries") == 2
    assert _table_count(db_path, "nutrition_cache") == 2

    # Lower bound: a single character after trimming is accepted.
    one_char = client.post("/estimate", json={"description": "  x  "})
    assert one_char.status_code == 200
    assert one_char.json()["description"] == "x"

    # The limit counts characters, not UTF-8 bytes (Hungarian input: "á" is 2 bytes).
    accented = client.post("/estimate", json={"description": "á" * 200})
    assert accented.status_code == 200
    assert stub.call_count == 4


def test_ac4_empty_input(tmp_path: Path) -> None:
    """AC4 — Invalid input / error case: whitespace-only (3 spaces) and empty input return 400 with no AI call or DB write."""
    db_path = str(tmp_path / "ac4.db")
    stub = StubNutritionProvider(default=CHICKEN_BREAST)
    app = _make_app(db_path, provider=stub)
    client = _register_and_login(app)

    for raw in ("   ", ""):
        resp = client.post("/estimate", json={"description": raw})
        assert resp.status_code == 400
        assert resp.json()["detail"] == DESCRIPTION_ERROR == "Description must be 1–200 characters"

    assert stub.call_count == 0
    assert _table_count(db_path, "entries") == 0
    assert _table_count(db_path, "nutrition_cache") == 0


def test_ac5_invalid_ai_output_and_macro_boundary(tmp_path: Path) -> None:
    """AC5 — Boundary edge case (±20% macro boundary) and invalid input / error case: invalid AI output returns 502 without storing or caching."""
    # Macros: 30 P * 4 + 45 C * 4 + 0 F * 9 = 300 expected kcal -> ±20% bounds are [240, 360].
    invalid_payloads: list[dict[str, Any]] = [
        {"calories_kcal": 248, "protein_g": -5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"},
        {"protein_g": 46.5, "carbs_g": 0, "fat_g": 5.4, "confidence": "medium"},
        {"calories_kcal": 900, "protein_g": 30, "carbs_g": 45, "fat_g": 0, "confidence": "low"},
        {"calories_kcal": 239.9, "protein_g": 30, "carbs_g": 45, "fat_g": 0, "confidence": "low"},
        {"calories_kcal": 360.1, "protein_g": 30, "carbs_g": 45, "fat_g": 0, "confidence": "low"},
    ]
    for idx, payload in enumerate(invalid_payloads):
        db_path = str(tmp_path / f"ac5_invalid_{idx}.db")
        stub = StubNutritionProvider(default=payload)
        client = _register_and_login(_make_app(db_path, provider=stub))

        resp = client.post("/estimate", json={"description": "150 g chicken breast"})
        assert resp.status_code == 502
        assert resp.json()["detail"] == INVALID_AI_OUTPUT_ERROR == "The AI returned an invalid result"
        assert _table_count(db_path, "entries") == 0
        assert _table_count(db_path, "nutrition_cache") == 0

    # Exact -20% (240 kcal) and +20% (360 kcal) boundaries against 300 expected kcal must be accepted.
    for idx, boundary_kcal in enumerate((240, 360)):
        db_path = str(tmp_path / f"ac5_boundary_{idx}.db")
        payload = {
            "calories_kcal": boundary_kcal,
            "protein_g": 30,
            "carbs_g": 45,
            "fat_g": 0,
            "confidence": "medium",
        }
        stub = StubNutritionProvider(default=payload)
        client = _register_and_login(_make_app(db_path, provider=stub))

        resp = client.post("/estimate", json={"description": "boundary meal"})
        assert resp.status_code == 200
        assert resp.json()["calories_kcal"] == boundary_kcal
        assert _table_count(db_path, "entries") == 1
        assert _table_count(db_path, "nutrition_cache") == 1


def test_ac6_llm_api_unavailable(tmp_path: Path) -> None:
    """AC6 — Invalid input / error case: provider timeout returns 503, leaves log unchanged, and app stays usable."""
    db_path = str(tmp_path / "ac6.db")
    stub = StubNutritionProvider(
        responses={
            "oatmeal": {"calories_kcal": 300, "protein_g": 10, "carbs_g": 50, "fat_g": 6, "confidence": "high"},
        },
        default=CHICKEN_BREAST,
    )
    app = _make_app(db_path, provider=stub)
    client = _register_and_login(app)

    seed = client.post("/estimate", json={"description": "oatmeal"})
    assert seed.status_code == 200

    stub.mode = "timeout"
    resp = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == UNAVAILABLE_ERROR == "Nutrition service unavailable"

    assert _table_count(db_path, "entries") == 1
    assert _table_count(db_path, "nutrition_cache") == 1
    entries_after_err = client.get("/entries").json()
    assert len(entries_after_err["entries"]) == 1
    assert entries_after_err["total_kcal"] == 300

    # Provider recovers; app remains usable for subsequent requests.
    stub.mode = "ok"
    recovered = client.post("/estimate", json={"description": "150 g chicken breast"})
    assert recovered.status_code == 200
    assert recovered.json()["calories_kcal"] == 248


def test_ac7_unauthorised_access(tmp_path: Path) -> None:
    """AC7 — Unauthorised access: 401 unauthenticated/invalid session/wrong password, and 404 cross-user delete."""
    db_path = str(tmp_path / "ac7.db")
    app = _make_app(db_path)

    anon = TestClient(app)
    assert anon.post("/estimate", json={"description": "apple"}).status_code == 401
    assert anon.get("/entries").status_code == 401
    assert anon.delete("/entries/1").status_code == 401

    bad_cookie = TestClient(app)
    bad_cookie.cookies.set("session", "forged.token")
    assert bad_cookie.post("/estimate", json={"description": "apple"}).status_code == 401
    assert bad_cookie.get("/entries").status_code == 401

    user_a = _register_and_login(app, username="alice", password="secret123")
    assert anon.post("/login", json={"username": "alice", "password": "wrong-password"}).status_code == 401

    created = user_a.post("/estimate", json={"description": "150 g chicken breast"})
    assert created.status_code == 200
    entry_id = created.json()["id"]

    alice_id = _user_id(db_path, "alice")
    assert _entry_exists_for(db_path, entry_id, alice_id)

    user_b = _register_and_login(app, username="bob", password="secret123")
    assert user_b.delete(f"/entries/{entry_id}").status_code == 404
    # A nonexistent id gives the same 404, so the response leaks nothing about other users' ids.
    assert user_b.delete(f"/entries/{entry_id + 999}").status_code == 404
    assert bad_cookie.delete(f"/entries/{entry_id}").status_code == 401

    # Verify directly in the DB (not only via the API) that the row survived, still owned by Alice.
    assert _entry_exists_for(db_path, entry_id, alice_id)
    assert _table_count(db_path, "entries") == 1

    a_entries = user_a.get("/entries").json()["entries"]
    assert len(a_entries) == 1
    assert a_entries[0]["id"] == entry_id
    assert user_b.get("/entries").json()["entries"] == []


def test_ac8_daily_total_and_date_boundary(tmp_path: Path) -> None:
    """AC8 — Date boundary / regression case: seeded clock separates yesterday vs today entries and delete recalculates total."""
    db_path = str(tmp_path / "ac8.db")
    # Sharpest boundary: last second of yesterday vs first second of today.
    clock = SeededClock(datetime(2026, 1, 14, 23, 59, 59))
    stub = StubNutritionProvider(
        responses={
            "dinner yesterday": {"calories_kcal": 700, "protein_g": 40, "carbs_g": 80, "fat_g": 24, "confidence": "medium"},
            "oatmeal": {"calories_kcal": 300, "protein_g": 10, "carbs_g": 50, "fat_g": 6, "confidence": "high"},
            "salad bowl": {"calories_kcal": 450, "protein_g": 30, "carbs_g": 35, "fat_g": 20, "confidence": "medium"},
        }
    )
    app = _make_app(db_path, clock=clock, provider=stub)
    client = _register_and_login(app)

    assert client.post("/estimate", json={"description": "dinner yesterday"}).status_code == 200

    clock.set(datetime(2026, 1, 15, 0, 0, 0))
    oatmeal = client.post("/estimate", json={"description": "oatmeal"})
    assert oatmeal.status_code == 200
    oatmeal_id = oatmeal.json()["id"]

    clock.set(datetime(2026, 1, 15, 13, 0, 0))
    salad = client.post("/estimate", json={"description": "salad bowl"})
    assert salad.status_code == 200

    today_view = client.get("/entries")
    assert today_view.status_code == 200
    today_data = today_view.json()
    assert today_data["date"] == "2026-01-15"
    assert len(today_data["entries"]) == 2
    assert today_data["total_kcal"] == 750

    deleted = client.delete(f"/entries/{oatmeal_id}")
    assert deleted.status_code == 200

    after_delete = client.get("/entries").json()
    assert len(after_delete["entries"]) == 1
    assert after_delete["total_kcal"] == 450
