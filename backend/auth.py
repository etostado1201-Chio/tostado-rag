"""
auth.py
-------
Authentication for department admins.

Each department has exactly one admin (created by scripts/generate_data.py).
That admin authenticates with email + password, receives a JWT, and uses it
to call the data-update endpoints.

The JWT payload contains:
    {
        "sub":        admin_username,
        "department": admin_department,
        "exp":        unix-timestamp,
    }
"""

from __future__ import annotations

import json
import os
import time
from functools import wraps
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from flask import jsonify, request

DATA_DIR    = Path(__file__).resolve().parent.parent / "data"
ADMINS_FILE = "admins.json"

JWT_SECRET     = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM  = "HS256"
JWT_TTL_HOURS  = 8


# ---------------------------------------------------------------------------
# Admin lookup
# ---------------------------------------------------------------------------

def _load_admins(data_dir: Optional[Path] = None) -> list[dict]:
    base = Path(data_dir) if data_dir else DATA_DIR
    return json.loads((base / ADMINS_FILE).read_text())


def find_admin(username: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    for a in _load_admins(data_dir):
        if a["username"].lower() == username.lower():
            return a
    return None


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def issue_token(admin: dict) -> str:
    payload = {
        "sub":        admin["username"],
        "department": admin["department"],
        "exp":        int(time.time()) + JWT_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Flask decorator
# ---------------------------------------------------------------------------

def require_admin(view_fn):
    """Protect a Flask route — caller must send `Authorization: Bearer <jwt>`."""
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Missing bearer token"}), 401
        payload = decode_token(header.split(" ", 1)[1])
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.admin = payload     # noqa: attach to request for the view
        return view_fn(*args, **kwargs)
    return wrapper
