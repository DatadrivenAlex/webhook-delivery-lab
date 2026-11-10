"""SQLite-backed webhook scheduling with deterministic mock delivery.

No network calls are made. Signatures demonstrate integrity, not key management.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_ATTEMPTS = 4

def timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()

def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn

def initialize(path: str | Path) -> None:
    with connect(path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL,
            created_at TEXT NOT NULL, last_error TEXT)''')

def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def verify(payload: str, secret: str, signature: str) -> bool:
    return hmac.compare_digest(sign(payload, secret), signature)

class Conflict(ValueError):
    pass

def enqueue(path: str | Path, key: str, payload: dict[str, Any], now: datetime | None = None) -> tuple[dict[str, Any], bool]:
    body, at = canonical(payload), timestamp(now)
    with connect(path) as db:
        db.execute('INSERT OR IGNORE INTO events (idempotency_key, payload, next_attempt_at, created_at) VALUES (?, ?, ?, ?)', (key, body, at, at))
        created = db.execute('SELECT changes()').fetchone()[0] == 1
        row = db.execute('SELECT * FROM events WHERE idempotency_key = ?', (key,)).fetchone()
        if row['payload'] != body:
            raise Conflict('Idempotency key already used with a different payload')
        return dict(row), created

def get_event(path: str | Path, event_id: int) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        return dict(row) if row else None

def deliver_one(path: str | Path, event_id: int, succeeds: bool, now: datetime | None = None) -> dict[str, Any] | None:
    """Simulate one attempt. Atomic transaction prevents concurrent double attempts."""
    current = now or datetime.now(timezone.utc)
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if row is None:
            db.rollback()
            return None
        if row['status'] != 'pending' or row['next_attempt_at'] > timestamp(current):
            db.rollback()
            return dict(row)
        attempts = row['attempts'] + 1
        status = 'delivered' if succeeds else ('failed' if attempts >= MAX_ATTEMPTS else 'pending')
        next_at = timestamp(current + timedelta(seconds=2 ** attempts * 10))
        db.execute('UPDATE events SET status=?, attempts=?, next_attempt_at=?, last_error=? WHERE id=?',
                   (status, attempts, next_at, None if succeeds else 'simulated failure', event_id))
        updated = dict(db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone())
        db.commit()
        return updated
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
