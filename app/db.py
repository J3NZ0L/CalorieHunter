import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    description TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    calories_kcal REAL NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    confidence TEXT NOT NULL,
    cached INTEGER NOT NULL DEFAULT 0,
    entry_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_cache (
    normalized_text TEXT PRIMARY KEY,
    calories_kcal REAL NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    confidence TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str, created_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, created_at),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_cached_nutrition(conn: sqlite3.Connection, normalized_text: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM nutrition_cache WHERE normalized_text = ?",
        (normalized_text,),
    ).fetchone()


def save_cached_nutrition(
    conn: sqlite3.Connection,
    *,
    normalized_text: str,
    calories_kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    confidence: str,
    created_at: str,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO nutrition_cache
            (normalized_text, calories_kcal, protein_g, carbs_g, fat_g, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (normalized_text, calories_kcal, protein_g, carbs_g, fat_g, confidence, created_at),
    )
    if commit:
        conn.commit()


def create_entry(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    description: str,
    normalized_text: str,
    calories_kcal: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    confidence: str,
    cached: bool,
    entry_date: str,
    created_at: str,
    commit: bool = True,
) -> sqlite3.Row:
    cur = conn.execute(
        """
        INSERT INTO entries
            (user_id, description, normalized_text, calories_kcal, protein_g, carbs_g, fat_g, confidence, cached, entry_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            description,
            normalized_text,
            calories_kcal,
            protein_g,
            carbs_g,
            fat_g,
            confidence,
            int(cached),
            entry_date,
            created_at,
        ),
    )
    if commit:
        conn.commit()
    assert cur.lastrowid is not None
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    assert row is not None
    return row


def list_entries_for_date(
    conn: sqlite3.Connection, user_id: int, entry_date: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM entries WHERE user_id = ? AND entry_date = ? ORDER BY id DESC",
        (user_id, entry_date),
    ).fetchall()


def delete_entry(conn: sqlite3.Connection, entry_id: int, user_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0
