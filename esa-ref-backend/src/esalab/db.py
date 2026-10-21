"""The only persistent store: one SQLite file (users, jobs with their docx blobs, settings)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "esalab.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT, hash TEXT, created REAL);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, user TEXT, started REAL, state TEXT, input BLOB, output BLOB, deleted REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lookups (query TEXT PRIMARY KEY, created REAL, result TEXT);
CREATE TABLE IF NOT EXISTS single_tasks (id TEXT PRIMARY KEY, user TEXT, created REAL, query TEXT, meta TEXT, stage TEXT, result TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS prefs (username TEXT PRIMARY KEY, author TEXT);
CREATE TABLE IF NOT EXISTS refs (id TEXT PRIMARY KEY, user TEXT, created REAL, query TEXT, meta TEXT, reference TEXT, type TEXT, issues TEXT, check_ok INTEGER, problems TEXT);
CREATE TABLE IF NOT EXISTS events (t REAL, user TEXT, via TEXT, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS shares (token TEXT PRIMARY KEY, job TEXT, user TEXT, created REAL, png BLOB, png_at REAL, png_sq BLOB);
CREATE INDEX IF NOT EXISTS events_t ON events (t);
"""


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)  # one short-lived connection per call: safe across job threads
    con.executescript(SCHEMA)
    if "tour" not in {r[1] for r in con.execute("PRAGMA table_info(prefs)")}:  # column added later: stage of the onboarding tour
        con.execute("ALTER TABLE prefs ADD COLUMN tour TEXT")
    if "deleted" not in {r[1] for r in con.execute("PRAGMA table_info(jobs)")}:  # soft delete: the row keeps feeding the stats
        con.execute("ALTER TABLE jobs ADD COLUMN deleted REAL")
    if "png_sq" not in {r[1] for r in con.execute("PRAGMA table_info(shares)")}:  # the square share card, cached like png
        con.execute("ALTER TABLE shares ADD COLUMN png_sq BLOB")
    return con


def event(user: str, via: str, kind: str, detail: str = ""):
    """One line of the audit trail the admin timeline shows: who did what, through the web UI / curl / MCP."""
    with connect() as con:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (time.time(), user, via, kind, detail))


def setting(key: str, make: callable) -> str:
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row:
            return row[0]
        value = make()
        con.execute("INSERT INTO settings VALUES (?,?)", (key, value))
        return value
