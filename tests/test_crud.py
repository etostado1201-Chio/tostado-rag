"""Tests for backend.crud — CRUD operations on JSON datasets."""

from __future__ import annotations

import json

import pytest

from backend.crud import (
    CrudError,
    create_brand,
    create_record,
    create_store,
    get_record,
    hard_delete_record,
    list_records,
    soft_delete_record,
    update_record,
)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def test_list_records(tmp_data_dir):
    stores = list_records(tmp_data_dir, "stores")
    assert len(stores) == 2


def test_get_record_existing(tmp_data_dir):
    s = get_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001")
    assert s["status"] == "active"


def test_get_record_missing_raises_404(tmp_data_dir):
    with pytest.raises(CrudError) as exc:
        get_record(tmp_data_dir, "stores", "NOPE-9999")
    assert exc.value.status_code == 404


def test_get_record_unknown_dataset_raises(tmp_data_dir):
    with pytest.raises(CrudError):
        get_record(tmp_data_dir, "secrets", "anything")


# ---------------------------------------------------------------------------
# Update — deep merge
# ---------------------------------------------------------------------------

def test_update_shallow_field(tmp_data_dir):
    updated = update_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001",
                            {"phone": "(214) 555-7777"})
    assert updated["phone"] == "(214) 555-7777"


def test_update_deep_preserves_sibling_fields(tmp_data_dir):
    """The OLD shallow .update() bug: patching one nested field clobbered
    its siblings. Deep merge must preserve them."""
    updated = update_record(tmp_data_dir, "vendors", "PHONE-GOLDEN_CRISP-0001",
                            {"login": {"username": "newuser"}})
    assert updated["login"]["username"] == "newuser"
    # The password from fixtures should still be there:
    assert updated["login"]["password"] == "vendorPass!"


def test_update_rejects_pk_change(tmp_data_dir):
    with pytest.raises(CrudError):
        update_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001",
                      {"store_id": "RENAMED-0001"})


def test_update_rejects_empty_patch(tmp_data_dir):
    with pytest.raises(CrudError):
        update_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001", {})


def test_update_persists_to_disk(tmp_data_dir):
    update_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001",
                  {"phone": "NEW"})
    raw = json.loads((tmp_data_dir / "stores.json").read_text())
    target = next(s for s in raw if s["store_id"] == "GOLDEN_CRISP-0001")
    assert target["phone"] == "NEW"


# ---------------------------------------------------------------------------
# Create — generic
# ---------------------------------------------------------------------------

def test_create_employee(tmp_data_dir):
    payload = {"id": "EMP-IT-099", "full_name": "New Person",
               "email": "new@x.com", "phone": "555", "department": "IT"}
    created = create_record(tmp_data_dir, "employees", payload)
    assert created["id"] == "EMP-IT-099"
    assert len(list_records(tmp_data_dir, "employees")) == 2


def test_create_rejects_duplicate(tmp_data_dir):
    payload = {"id": "EMP-IT-001", "full_name": "Duplicate"}
    with pytest.raises(CrudError) as exc:
        create_record(tmp_data_dir, "employees", payload)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Create brand
# ---------------------------------------------------------------------------

def test_create_brand(tmp_data_dir):
    brand = create_brand(tmp_data_dir, {
        "id": "wave_sushi", "name": "Wave Sushi", "category": "Sushi",
    })
    assert brand["status"] == "active"
    assert len(list_records(tmp_data_dir, "brands")) == 3


def test_create_brand_rejects_duplicate(tmp_data_dir):
    with pytest.raises(CrudError) as exc:
        create_brand(tmp_data_dir, {
            "id": "golden_crisp", "name": "x", "category": "x",
        })
    assert exc.value.status_code == 409


def test_create_brand_normalises_id(tmp_data_dir):
    brand = create_brand(tmp_data_dir, {
        "id": "Wave Sushi", "name": "Wave Sushi", "category": "Sushi",
    })
    assert brand["id"] == "wave_sushi"


# ---------------------------------------------------------------------------
# Create store — atomic vendor account creation
# ---------------------------------------------------------------------------

def test_create_store_assigns_next_id(tmp_data_dir):
    payload = {
        "brand_id": "golden_crisp",
        "address": {"street": "9 New St", "city": "Plano", "state": "TX", "zipcode": "75024"},
        "manager": {"full_name": "New Manager", "phone": "555", "email": "x@y"},
    }
    created = create_store(tmp_data_dir, payload)
    assert created["store_id"] == "GOLDEN_CRISP-0002"


def test_create_store_creates_phone_and_internet_vendors(tmp_data_dir):
    """The atomicity guarantee: new store ALWAYS comes with both vendor accounts."""
    payload = {
        "brand_id": "stone_fire",
        "address": {"street": "5 New", "city": "Frisco", "state": "TX", "zipcode": "75033"},
        "manager": {"full_name": "M", "phone": "1", "email": "m@x"},
    }
    created  = create_store(tmp_data_dir, payload)
    vendors  = list_records(tmp_data_dir, "vendors")
    related  = [v for v in vendors if v["store_id"] == created["store_id"]]
    services = sorted(v["service"] for v in related)
    assert services == ["Internet", "Phone"]


def test_create_store_rejects_unknown_brand(tmp_data_dir):
    with pytest.raises(CrudError) as exc:
        create_store(tmp_data_dir, {
            "brand_id": "made_up",
            "address": {"street": "x", "city": "x", "state": "TX", "zipcode": "00000"},
            "manager": {"full_name": "x", "phone": "x", "email": "x"},
        })
    assert exc.value.status_code == 404


def test_create_store_rejects_inactive_brand(tmp_data_dir):
    # Add a fresh brand with no stores, then close it.
    create_brand(tmp_data_dir, {"id": "wave_sushi", "name": "Wave", "category": "Sushi"})
    soft_delete_record(tmp_data_dir, "brands", "wave_sushi")
    with pytest.raises(CrudError) as exc:
        create_store(tmp_data_dir, {
            "brand_id": "wave_sushi",
            "address": {"street": "x", "city": "x", "state": "TX", "zipcode": "00000"},
            "manager": {"full_name": "x", "phone": "x", "email": "x"},
        })
    assert exc.value.status_code == 409


def test_create_store_required_fields(tmp_data_dir):
    with pytest.raises(CrudError):
        create_store(tmp_data_dir, {"brand_id": "golden_crisp"})


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

def test_soft_delete_store(tmp_data_dir):
    closed = soft_delete_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001",
                                closed_on="2026-05-01")
    assert closed["status"]    == "closed"
    assert closed["closed_on"] == "2026-05-01"
    # And the record IS still on disk (auditability):
    assert any(s["store_id"] == "GOLDEN_CRISP-0001"
               for s in list_records(tmp_data_dir, "stores"))


def test_soft_delete_brand_with_active_stores_blocked(tmp_data_dir):
    """Referential integrity: closing a brand with active stores must fail."""
    with pytest.raises(CrudError) as exc:
        soft_delete_record(tmp_data_dir, "brands", "golden_crisp")
    assert exc.value.status_code == 409


def test_soft_delete_brand_after_closing_its_stores(tmp_data_dir):
    soft_delete_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001")
    closed = soft_delete_record(tmp_data_dir, "brands", "golden_crisp")
    assert closed["status"] == "closed"


def test_soft_delete_unsupported_dataset(tmp_data_dir):
    with pytest.raises(CrudError):
        soft_delete_record(tmp_data_dir, "vendors", "PHONE-GOLDEN_CRISP-0001")


# ---------------------------------------------------------------------------
# Hard delete
# ---------------------------------------------------------------------------

def test_hard_delete_store(tmp_data_dir):
    hard_delete_record(tmp_data_dir, "stores", "GOLDEN_CRISP-0001")
    assert all(s["store_id"] != "GOLDEN_CRISP-0001"
               for s in list_records(tmp_data_dir, "stores"))


def test_hard_delete_brand_with_stores_blocked(tmp_data_dir):
    with pytest.raises(CrudError) as exc:
        hard_delete_record(tmp_data_dir, "brands", "golden_crisp")
    assert exc.value.status_code == 409


def test_hard_delete_missing(tmp_data_dir):
    with pytest.raises(CrudError) as exc:
        hard_delete_record(tmp_data_dir, "stores", "NOPE-9999")
    assert exc.value.status_code == 404
