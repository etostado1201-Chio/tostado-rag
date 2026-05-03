"""
crud.py
-------
Create / Read / Update / Delete operations on the JSON datasets.

Why a module instead of inline in app.py? Two reasons:
  1. Side-effects matter — creating a store also creates two vendor
     accounts. That logic lives here, not scattered across routes.
  2. Validation rules (no-orphan brands, soft vs hard delete, status
     transitions) need one place to live so they stay consistent.

All functions in this module raise `CrudError` for known failure cases
so the route layer can map them to clean HTTP responses.
"""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Any


class CrudError(Exception):
    """Raised on any validation / business-rule failure."""
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

# Maps dataset name -> (filename, primary key field).
DATASETS: dict[str, tuple[str, str]] = {
    "stores":      ("stores.json",      "store_id"),
    "vendors":     ("vendors.json",     "vendor_account_id"),
    "employees":   ("employees.json",   "id"),
    "departments": ("departments.json", "name"),
    "brands":      ("brands.json",      "id"),
}

# Datasets that support a `status` field for soft-delete.
SOFT_DELETE_DATASETS = {"stores", "brands"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _path(data_dir: Path, dataset: str) -> Path:
    if dataset not in DATASETS:
        raise CrudError(f"Unknown dataset: {dataset!r}. Allowed: {sorted(DATASETS)}.")
    fname, _ = DATASETS[dataset]
    return data_dir / fname


def _read(data_dir: Path, dataset: str) -> list[dict]:
    path = _path(data_dir, dataset)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _write(data_dir: Path, dataset: str, records: list[dict]) -> None:
    _path(data_dir, dataset).write_text(json.dumps(records, indent=2))


def _pk(dataset: str) -> str:
    return DATASETS[dataset][1]


def _deep_merge(target: dict, patch: dict) -> dict:
    """
    Deep-merge `patch` into `target` (target mutated and returned).

    Unlike `dict.update`, nested dicts are merged recursively — so
    `{"login": {"username": "x"}}` updates the username without losing
    the password. To explicitly clear a nested value, set it to None.
    """
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v
    return target


def _random_password(length: int = 14) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(random.choices(chars, k=length))


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_records(data_dir: Path, dataset: str) -> list[dict]:
    return _read(data_dir, dataset)


def get_record(data_dir: Path, dataset: str, record_id: str) -> dict:
    if dataset not in DATASETS:
        raise CrudError(f"Unknown dataset: {dataset!r}")
    pk = _pk(dataset)
    for r in _read(data_dir, dataset):
        if str(r.get(pk)) == str(record_id):
            return r
    raise CrudError(f"No {dataset} record with {pk}={record_id!r}", status_code=404)


# ---------------------------------------------------------------------------
# Update (deep merge)
# ---------------------------------------------------------------------------

def update_record(
    data_dir: Path,
    dataset: str,
    record_id: str,
    patch: dict,
) -> dict:
    if not isinstance(patch, dict) or not patch:
        raise CrudError("patch must be a non-empty object")

    pk = _pk(dataset)
    records = _read(data_dir, dataset)

    target = next((r for r in records if str(r.get(pk)) == str(record_id)), None)
    if target is None:
        raise CrudError(f"No {dataset} record with {pk}={record_id!r}", status_code=404)

    # Don't allow changing the primary key — it would break referential integrity.
    if pk in patch and str(patch[pk]) != str(record_id):
        raise CrudError(f"Cannot change primary key {pk}")

    _deep_merge(target, patch)
    _write(data_dir, dataset, records)
    return target


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def soft_delete_record(
    data_dir: Path,
    dataset: str,
    record_id: str,
    closed_on: str | None = None,
) -> dict:
    """Mark as `status: closed`. Only valid on stores and brands."""
    if dataset not in SOFT_DELETE_DATASETS:
        raise CrudError(
            f"Soft delete is only supported for {sorted(SOFT_DELETE_DATASETS)}, "
            f"not {dataset}. Use hard delete instead."
        )

    if dataset == "brands":
        # A brand cannot be closed if it has active stores.
        active = sum(
            1 for s in _read(data_dir, "stores")
            if s.get("brand_id") == record_id and s.get("status", "active") == "active"
        )
        if active:
            raise CrudError(
                f"Brand {record_id!r} still has {active} active store(s). "
                f"Close those first.",
                status_code=409,
            )

    patch: dict[str, Any] = {"status": "closed"}
    if closed_on and dataset == "stores":
        patch["closed_on"] = closed_on
    return update_record(data_dir, dataset, record_id, patch)


def hard_delete_record(data_dir: Path, dataset: str, record_id: str) -> dict:
    """Remove the record entirely. Use sparingly."""
    pk = _pk(dataset)
    records = _read(data_dir, dataset)
    before  = len(records)
    records = [r for r in records if str(r.get(pk)) != str(record_id)]
    if len(records) == before:
        raise CrudError(f"No {dataset} record with {pk}={record_id!r}", status_code=404)

    # Brand referential integrity also applies to hard delete.
    if dataset == "brands":
        ref = sum(1 for s in _read(data_dir, "stores") if s.get("brand_id") == record_id)
        if ref:
            raise CrudError(
                f"Brand {record_id!r} is referenced by {ref} store(s). "
                f"Reassign or delete those first.",
                status_code=409,
            )

    _write(data_dir, dataset, records)
    return {"deleted": record_id}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

REQUIRED_BRAND_FIELDS = {"id", "name", "category"}
REQUIRED_STORE_FIELDS = {"brand_id", "address", "manager"}


def _next_store_id(records: list[dict], brand_id: str) -> str:
    prefix = f"{brand_id.upper()}-"
    nums = [
        int(r["store_id"].rsplit("-", 1)[-1])
        for r in records
        if r.get("store_id", "").upper().startswith(prefix)
        and r["store_id"].rsplit("-", 1)[-1].isdigit()
    ]
    return f"{prefix}{(max(nums) + 1) if nums else 1:04d}"


def create_brand(data_dir: Path, payload: dict) -> dict:
    missing = REQUIRED_BRAND_FIELDS - payload.keys()
    if missing:
        raise CrudError(f"Brand is missing required fields: {sorted(missing)}")

    brand_id = str(payload["id"]).strip().lower().replace(" ", "_")
    if not brand_id:
        raise CrudError("Brand id cannot be empty")

    records = _read(data_dir, "brands")
    if any(b["id"] == brand_id for b in records):
        raise CrudError(f"Brand {brand_id!r} already exists", status_code=409)

    brand = {
        "id":       brand_id,
        "name":     payload["name"],
        "category": payload["category"],
        "status":   payload.get("status", "active"),
    }
    records.append(brand)
    _write(data_dir, "brands", records)
    return brand


def create_store(data_dir: Path, payload: dict) -> dict:
    """
    Create a store AND its phone + internet vendor accounts atomically.

    The vendor accounts get sensible placeholder values so the data
    stays consistent until the admin fills them in.
    """
    missing = REQUIRED_STORE_FIELDS - payload.keys()
    if missing:
        raise CrudError(f"Store is missing required fields: {sorted(missing)}")

    # Validate brand exists & is active.
    brand_id = payload["brand_id"]
    brands   = _read(data_dir, "brands")
    brand = next((b for b in brands if b["id"] == brand_id), None)
    if brand is None:
        raise CrudError(f"Brand {brand_id!r} does not exist", status_code=404)
    if brand.get("status", "active") != "active":
        raise CrudError(f"Brand {brand_id!r} is not active", status_code=409)

    stores  = _read(data_dir, "stores")
    vendors = _read(data_dir, "vendors")

    store_id = payload.get("store_id") or _next_store_id(stores, brand_id)
    if any(s["store_id"] == store_id for s in stores):
        raise CrudError(f"Store {store_id!r} already exists", status_code=409)

    store = {
        "store_id":   store_id,
        "brand_id":   brand_id,
        "brand_name": brand["name"],
        "category":   brand["category"],
        "status":     payload.get("status", "active"),
        "address":    payload["address"],
        "phone":      payload.get("phone", ""),
        "email":      payload.get("email", f"{store_id.lower()}@tostadogroup.com"),
        "opened_on":  payload.get("opened_on"),
        "closed_on":  None,
        "manager":    payload["manager"],
        "district_manager": payload.get("district_manager", {
            "id": "TBD", "name": "TBD", "phone": "TBD", "email": "TBD",
        }),
        "vp_operations":    payload.get("vp_operations", {
            "id": "TBD", "name": "TBD", "phone": "TBD", "email": "TBD",
        }),
    }
    stores.append(store)

    # Phone vendor account
    vendors.append({
        "vendor_account_id": f"PHONE-{store_id}",
        "store_id":          store_id,
        "service":           "Phone",
        "provider":          "TBD",
        "account_number":    "TBD",
        "monthly_cost":      0.0,
        "support_phone":     "TBD",
        "portal_url":        "",
        "login": {
            "username": f"tostado.{store_id.lower()}@tostadogroup.com",
            "password": _random_password(),
        },
    })
    # Internet vendor account
    vendors.append({
        "vendor_account_id": f"NET-{store_id}",
        "store_id":          store_id,
        "service":           "Internet",
        "provider":          "TBD",
        "account_number":    "TBD",
        "monthly_cost":      0.0,
        "support_phone":     "TBD",
        "portal_url":        "",
        "login": {
            "username": f"tostado.{store_id.lower()}",
            "password": _random_password(),
        },
    })

    _write(data_dir, "stores",  stores)
    _write(data_dir, "vendors", vendors)
    return store


def create_record(data_dir: Path, dataset: str, payload: dict) -> dict:
    """Generic create — stores and brands have specialised paths."""
    if dataset == "stores":
        return create_store(data_dir, payload)
    if dataset == "brands":
        return create_brand(data_dir, payload)

    if dataset not in DATASETS:
        raise CrudError(f"Unknown dataset: {dataset!r}")
    if not isinstance(payload, dict) or not payload:
        raise CrudError("payload must be a non-empty object")

    pk = _pk(dataset)
    if pk not in payload:
        raise CrudError(f"Missing primary key {pk!r}")

    records = _read(data_dir, dataset)
    if any(str(r.get(pk)) == str(payload[pk]) for r in records):
        raise CrudError(f"{dataset} record with {pk}={payload[pk]!r} already exists",
                        status_code=409)

    records.append(payload)
    _write(data_dir, dataset, records)
    return payload
