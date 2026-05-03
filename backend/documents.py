"""
documents.py
------------
Convert the JSON datasets into LangChain Document objects.

Each piece of structured data is turned into a short, descriptive passage
that the LLM can quote from. Metadata is preserved for filtering/citations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from langchain_core.documents import Document

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

def store_to_text(s: dict) -> str:
    a = s["address"]
    status = s.get("status", "active")
    status_line = f" Status: {status}."
    if status == "closed" and s.get("closed_on"):
        status_line += f" Closed on {s['closed_on']}."
    return (
        f"Store {s['store_id']} - {s['brand_name']} ({s['category']}).{status_line}\n"
        f"Address: {a['street']}, {a['city']}, {a['state']} {a['zipcode']}.\n"
        f"Store phone: {s['phone']}. Store email: {s['email']}. "
        f"Opened on {s['opened_on']}.\n"
        f"Store manager: {s['manager']['full_name']} - "
        f"phone {s['manager']['phone']}, email {s['manager']['email']}.\n"
        f"District manager: {s['district_manager']['name']} - "
        f"phone {s['district_manager']['phone']}, email {s['district_manager']['email']}.\n"
        f"VP of Operations: {s['vp_operations']['name']} - "
        f"phone {s['vp_operations']['phone']}, email {s['vp_operations']['email']}."
    )


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------

def vendor_to_text(v: dict) -> str:
    return (
        f"{v['service']} account for store {v['store_id']}.\n"
        f"Provider: {v['provider']}. Account number: {v['account_number']}. "
        f"Monthly cost: ${v['monthly_cost']:.2f}.\n"
        f"Support phone: {v['support_phone']}. Portal URL: {v['portal_url']}.\n"
        f"Login username: {v['login']['username']}. "
        f"Login password: {v['login']['password']}."
    )


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

def department_to_text(d: dict) -> str:
    return (
        f"Department: {d['name']}. {d['description']}\n"
        f"Department head: {d['head']['name']} - "
        f"phone {d['head']['phone']}, email {d['head']['email']}.\n"
        f"Admin contact (data updates): {d['admin_contact']['name']} - "
        f"phone {d['admin_contact']['phone']}, email {d['admin_contact']['email']}.\n"
        f"Team size: {len(d['team_member_ids'])} members."
    )


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

def employee_to_text(e: dict) -> str:
    return (
        f"Employee {e['id']}: {e['full_name']}, {e.get('title', 'Staff')}, "
        f"{e.get('department', 'Unknown')} department.\n"
        f"Email: {e['email']}. Phone: {e['phone']}."
    )


# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------

def brand_to_text(b: dict) -> str:
    return (
        f"Brand: {b['name']} ({b['category']}). "
        f"Brand ID: {b['id']}. Status: {b.get('status', 'active')}."
    )


# ---------------------------------------------------------------------------
# Master loader
# ---------------------------------------------------------------------------

def load_all_documents(data_dir: Path | None = None) -> List[Document]:
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    docs: List[Document] = []

    stores      = json.loads((base / "stores.json").read_text())
    vendors     = json.loads((base / "vendors.json").read_text())
    employees   = json.loads((base / "employees.json").read_text())
    departments = json.loads((base / "departments.json").read_text())

    # Brands are optional for backwards compatibility — old datasets won't have them.
    brands_path = base / "brands.json"
    brands = json.loads(brands_path.read_text()) if brands_path.exists() else []

    for s in stores:
        docs.append(Document(
            page_content=store_to_text(s),
            metadata={
                "type":     "store",
                "store_id": s["store_id"],
                "brand_id": s["brand_id"],
                "city":     s["address"]["city"],
                "state":    s["address"]["state"],
                "status":   s.get("status", "active"),
            },
        ))

    for v in vendors:
        docs.append(Document(
            page_content=vendor_to_text(v),
            metadata={
                "type":     "vendor",
                "store_id": v["store_id"],
                "service":  v["service"],
                "provider": v["provider"],
            },
        ))

    for d in departments:
        docs.append(Document(
            page_content=department_to_text(d),
            metadata={"type": "department", "department": d["name"]},
        ))

    for e in employees:
        docs.append(Document(
            page_content=employee_to_text(e),
            metadata={
                "type":       "employee",
                "employee_id": e["id"],
                "department": e.get("department", "Unknown"),
            },
        ))

    for b in brands:
        docs.append(Document(
            page_content=brand_to_text(b),
            metadata={
                "type":     "brand",
                "brand_id": b["id"],
                "status":   b.get("status", "active"),
            },
        ))

    return docs


if __name__ == "__main__":
    docs = load_all_documents()
    print(f"Built {len(docs)} documents.")
    print("Sample:")
    print(docs[0].page_content)
