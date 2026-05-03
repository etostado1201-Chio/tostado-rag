"""Tests for backend.auth: bcrypt + JWT + Flask decorator."""

from __future__ import annotations

import time

import jwt
import pytest

from backend import auth as auth_module
from backend.auth import (
    decode_token,
    find_admin,
    issue_token,
    verify_password,
)
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, ADMIN_DEPARTMENT


def test_find_admin_finds_seeded_user(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    assert admin is not None
    assert admin["department"] == ADMIN_DEPARTMENT


def test_find_admin_is_case_insensitive(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME.upper(), data_dir=tmp_data_dir)
    assert admin is not None


def test_find_admin_returns_none_for_unknown(tmp_data_dir):
    assert find_admin("nobody@nowhere.com", data_dir=tmp_data_dir) is None


def test_verify_password_accepts_correct(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    assert verify_password(ADMIN_PASSWORD, admin["password_hash"]) is True


def test_verify_password_rejects_wrong(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    assert verify_password("wrong-pwd", admin["password_hash"]) is False


def test_verify_password_handles_garbage_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_jwt_round_trip(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    token   = issue_token(admin)
    payload = decode_token(token)

    assert payload is not None
    assert payload["sub"]        == ADMIN_USERNAME
    assert payload["department"] == ADMIN_DEPARTMENT
    assert payload["exp"]        > int(time.time())


def test_decode_token_rejects_garbage():
    assert decode_token("garbage.token.here") is None


def test_decode_token_rejects_expired(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    expired = jwt.encode(
        {"sub": admin["username"], "department": admin["department"], "exp": 1},
        auth_module.JWT_SECRET,
        algorithm=auth_module.JWT_ALGORITHM,
    )
    assert decode_token(expired) is None


def test_decode_token_rejects_wrong_signature(tmp_data_dir):
    admin = find_admin(ADMIN_USERNAME, data_dir=tmp_data_dir)
    bad = jwt.encode(
        {"sub": admin["username"], "exp": int(time.time()) + 60},
        "wrong-secret-wrong-secret-wrong-secret-wrong",
        algorithm="HS256",
    )
    assert decode_token(bad) is None
