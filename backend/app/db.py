"""シナリオ永続化(SQLite)。"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "scenarios.db"


def db_path() -> Path:
    return Path(os.environ.get("TRANSIM_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scenarios (
             id TEXT PRIMARY KEY,
             name TEXT NOT NULL,
             description TEXT NOT NULL DEFAULT '',
             lines_json TEXT NOT NULL DEFAULT '[]',
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
           )"""
    )
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "lines": json.loads(row["lines_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_scenarios() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM scenarios ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "line_count": len(json.loads(r["lines_json"])),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_scenario(scenario_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_scenario(name: str, description: str = "", lines: list | None = None) -> dict:
    sid = uuid.uuid4().hex[:12]
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO scenarios (id, name, description, lines_json, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (sid, name, description, json.dumps(lines or [], ensure_ascii=False), now, now),
        )
    return get_scenario(sid)


def update_scenario(scenario_id: str, *, name=None, description=None, lines=None) -> dict | None:
    cur = get_scenario(scenario_id)
    if cur is None:
        return None
    with connect() as conn:
        conn.execute(
            "UPDATE scenarios SET name = ?, description = ?, lines_json = ?, updated_at = ?"
            " WHERE id = ?",
            (
                name if name is not None else cur["name"],
                description if description is not None else cur["description"],
                json.dumps(lines if lines is not None else cur["lines"], ensure_ascii=False),
                _now(),
                scenario_id,
            ),
        )
    return get_scenario(scenario_id)


def delete_scenario(scenario_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
    return cur.rowcount > 0
