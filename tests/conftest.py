"""
Shared pytest fixtures.

Provides:
    tmp_data_dir   — a fresh, populated `data/` for each test
    mock_engine    — a stand-in RAG engine that records calls
    client         — a Flask test client wired to the above
    admin_token    — a valid JWT for the IT department admin
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import bcrypt
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

ADMIN_PASSWORD = "test-password-1234"
ADMIN_USERNAME = "ada.lovelace@tostadogroup.com"
ADMIN_DEPARTMENT = "IT"


def _bcrypt(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _build_fixture_data(target: Path) -> None:
    """Write a tiny but realistic dataset into `target`."""
    target.mkdir(parents=True, exist_ok=True)

    brands = [
        {"id": "golden_crisp", "name": "Golden Crisp", "category": "Fried Chicken", "status": "active"},
        {"id": "stone_fire",   "name": "Stone & Fire", "category": "Pizza",         "status": "active"},
    ]

    stores = [{
        "store_id":   "GOLDEN_CRISP-0001",
        "brand_id":   "golden_crisp",
        "brand_name": "Golden Crisp",
        "category":   "Fried Chicken",
        "status":     "active",
        "address":    {"street": "1 Main St", "city": "Dallas",  "state": "TX", "zipcode": "75201"},
        "phone":      "(214) 555-0100",
        "email":      "store0001@goldencrisp.tostadogroup.com",
        "opened_on":  "2020-01-15",
        "closed_on":  None,
        "manager":          {"id": "SM-1", "full_name": "Grace Hopper",  "phone": "(214) 555-0101", "email": "grace@tostadogroup.com",  "title": "Store Manager"},
        "district_manager": {"id": "DM-1", "name":      "Alan Turing",   "phone": "(214) 555-0102", "email": "alan@tostadogroup.com"},
        "vp_operations":    {"id": "VP-1", "name":      "Edsger Dijkstra","phone":"(214) 555-0103", "email": "edsger@tostadogroup.com"},
    }, {
        "store_id":   "STONE_FIRE-0001",
        "brand_id":   "stone_fire",
        "brand_name": "Stone & Fire",
        "category":   "Pizza",
        "status":     "active",
        "address":    {"street": "2 Oak Ave", "city": "Irving",   "state": "TX", "zipcode": "75038"},
        "phone":      "(972) 555-0200",
        "email":      "store0001@stonefire.tostadogroup.com",
        "opened_on":  "2021-06-01",
        "closed_on":  None,
        "manager":          {"id": "SM-2", "full_name": "Linus Torvalds", "phone": "(972) 555-0201", "email": "linus@tostadogroup.com", "title": "Store Manager"},
        "district_manager": {"id": "DM-2", "name":      "Margaret Hamilton","phone":"(972) 555-0202","email":"margaret@tostadogroup.com"},
        "vp_operations":    {"id": "VP-2", "name":      "Donald Knuth",   "phone":"(972) 555-0203","email":"donald@tostadogroup.com"},
    }]

    vendors = [{
        "vendor_account_id": "PHONE-GOLDEN_CRISP-0001",
        "store_id":   "GOLDEN_CRISP-0001",
        "service":    "Phone",
        "provider":   "AT&T Business",
        "account_number": "1111-2222-3333",
        "monthly_cost":   99.99,
        "support_phone":  "(800) 555-1234",
        "portal_url":     "https://example.com",
        "login": {"username": "tostado.gc-0001", "password": "vendorPass!"},
    }]

    employees = [{
        "id":         "EMP-IT-001",
        "full_name":  "Ada Lovelace",
        "first_name": "Ada",
        "last_name":  "Lovelace",
        "email":      ADMIN_USERNAME,
        "phone":      "(214) 555-9999",
        "title":      "IT Administrator",
        "department": "IT",
    }]

    departments = [{
        "name": "IT",
        "description":  "The IT department of Tostado Restaurant Group.",
        "head":         {"id": "EMP-IT-000", "name": "Charles Babbage", "email": "charles@tostadogroup.com", "phone": "(214) 555-9000"},
        "admin_contact":{"id": "EMP-IT-001", "name": "Ada Lovelace",    "email": ADMIN_USERNAME,             "phone": "(214) 555-9999"},
        "team_member_ids": ["EMP-IT-001"],
    }]

    admins = [{
        "department":     ADMIN_DEPARTMENT,
        "username":       ADMIN_USERNAME,
        "password_plain": ADMIN_PASSWORD,
        "password_hash":  _bcrypt(ADMIN_PASSWORD),
        "employee_id":    "EMP-IT-001",
    }]

    (target / "stores.json").write_text(json.dumps(stores, indent=2))
    (target / "vendors.json").write_text(json.dumps(vendors, indent=2))
    (target / "employees.json").write_text(json.dumps(employees, indent=2))
    (target / "departments.json").write_text(json.dumps(departments, indent=2))
    (target / "admins.json").write_text(json.dumps(admins, indent=2))
    (target / "brands.json").write_text(json.dumps(brands, indent=2))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stable_jwt_secret(monkeypatch):
    """Force a long, stable JWT secret so we get no warnings and stable tokens."""
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    # auth.py reads the env var at import time, so re-import to refresh.
    import importlib
    from backend import auth as _auth
    importlib.reload(_auth)


@pytest.fixture
def tmp_data_dir(tmp_path) -> Path:
    target = tmp_path / "data"
    _build_fixture_data(target)
    return target


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.ask.return_value = {
        "answer":  "Mocked answer for testing.",
        "sources": [{"content": "ctx", "metadata": {"type": "store"}}],
    }
    return engine


@pytest.fixture
def app(mock_engine, tmp_data_dir):
    from backend.app import create_app
    application = create_app(engine=mock_engine, data_dir=tmp_data_dir)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token(client):
    """Log in as the seeded IT admin and return the JWT."""
    res = client.post("/api/login", json={
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200, res.get_json()
    return res.get_json()["token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
