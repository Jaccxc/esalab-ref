"""Users in SQLite + JWT identity. Every /api route resolves the user from the token, never from a client-sent id."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time

import jwt
from fastapi import Depends, HTTPException, Request

from esalab import db

TOKEN_TTL = 7 * 24 * 3600
ADMINS = set(os.environ.get("ADMIN_USERS", os.environ.get("ADMIN_USER", "admin")).split(","))


def ensure_admin():
    """Seed the admin login once from ADMIN_USER / ADMIN_PASSWORD. No password in the env: nothing is seeded (no built-in default)."""
    name, pw = os.environ.get("ADMIN_USER", "admin"), os.environ.get("ADMIN_PASSWORD")
    ADMINS.add(name)
    if not pw:
        return
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
            salt = secrets.token_hex(16)
            con.execute("INSERT INTO users VALUES (?,?,?,?)", (name, salt, _hash(pw, salt), time.time()))


def _secret() -> str:
    if os.environ.get("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    return db.setting("jwt_secret", lambda: secrets.token_hex(32))  # generated once so tokens survive restarts


def _hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def register(username: str, password: str) -> str:
    username = username.strip()
    if not (1 <= len(username) <= 64) or len(password) < 6:
        raise HTTPException(400, "username 1-64 chars, password at least 6 chars")
    salt = secrets.token_hex(16)
    with db.connect() as con:
        try:
            con.execute("INSERT INTO users VALUES (?,?,?,?)", (username, salt, _hash(password, salt), time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "username already taken")
    return token_for(username)


def login(username: str, password: str) -> str:
    with db.connect() as con:
        row = con.execute("SELECT salt, hash FROM users WHERE username=?", (username.strip(),)).fetchone()
    if not row or not secrets.compare_digest(_hash(password, row[0]), row[1]):
        raise HTTPException(401, "wrong username or password")
    return token_for(username.strip())


def token_for(username: str, ttl: int = TOKEN_TTL) -> str:
    return jwt.encode({"sub": username, "exp": int(time.time()) + ttl}, _secret(), algorithm="HS256")


def user_of(token: str) -> str:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "login required")


def current_user(request: Request) -> str:
    """Bearer header, or ?token= for EventSource/download links which cannot set headers."""
    auth = request.headers.get("authorization", "")
    return user_of(auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", ""))


def current_admin(user: str = Depends(current_user)) -> str:
    if user not in ADMINS:
        raise HTTPException(403, "admin only")
    return user


User = Depends(current_user)
Admin = Depends(current_admin)
