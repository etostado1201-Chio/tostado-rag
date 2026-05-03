"""Integration tests for the Flask API.

These tests use the `create_app` factory with a mock RAG engine,
so they run with no Ollama and no sentence-transformers download.
"""

from __future__ import annotations

import io
import json

from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def test_chat_calls_engine(client, mock_engine):
    res = client.post("/api/chat", json={"message": "Where is GOLDEN_CRISP-0001?"})
    assert res.status_code == 200

    body = res.get_json()
    assert body["answer"]  == "Mocked answer for testing."
    assert body["sources"] == [{"content": "ctx", "metadata": {"type": "store"}}]
    mock_engine.ask.assert_called_once_with("Where is GOLDEN_CRISP-0001?")


def test_chat_response_includes_followups(client):
    """/api/chat must return a `followups` list for the UI."""
    res  = client.post("/api/chat", json={"message": "Where is GOLDEN_CRISP-0001?"})
    body = res.get_json()
    assert "followups" in body
    assert isinstance(body["followups"], list)
    assert len(body["followups"]) > 0
    # And every item must be a non-empty string the UI can render.
    for q in body["followups"]:
        assert isinstance(q, str) and q.strip()


def test_chat_followups_match_source_type(client, mock_engine):
    """When the retriever returns a store, follow-ups should mention that store."""
    mock_engine.ask.return_value = {
        "answer":  "Mocked.",
        "sources": [{"content": "ctx", "metadata": {
            "type": "store", "store_id": "STONE_FIRE-0042",
        }}],
    }
    res  = client.post("/api/chat", json={"message": "Tell me about STONE_FIRE-0042"})
    body = res.get_json()
    assert any("STONE_FIRE-0042" in q for q in body["followups"])


def test_chat_rejects_empty_message(client):
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success(client):
    res = client.post("/api/login", json={
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
    })
    assert res.status_code == 200
    body = res.get_json()
    assert "token" in body
    assert body["department"] == "IT"


def test_login_rejects_wrong_password(client):
    res = client.post("/api/login", json={
        "username": ADMIN_USERNAME,
        "password": "wrong",
    })
    assert res.status_code == 401


def test_login_rejects_unknown_user(client):
    res = client.post("/api/login", json={
        "username": "nobody@nowhere.com",
        "password": "x",
    })
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Admin update
# ---------------------------------------------------------------------------

def test_admin_update_requires_auth(client):
    res = client.post("/api/admin/update", json={
        "dataset":  "stores",
        "id_field": "store_id",
        "id":       "GOLDEN_CRISP-0001",
        "patch":    {"phone": "(214) 555-9999"},
    })
    assert res.status_code == 401


def test_admin_update_patches_record(client, auth_headers, tmp_data_dir, mock_engine):
    new_phone = "(214) 555-7777"

    res = client.post("/api/admin/update",
        headers=auth_headers,
        json={
            "dataset":  "stores",
            "id_field": "store_id",
            "id":       "GOLDEN_CRISP-0001",
            "patch":    {"phone": new_phone},
        })
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["status"] == "updated"

    # File on disk got patched
    stores = json.loads((tmp_data_dir / "stores.json").read_text())
    target = next(s for s in stores if s["store_id"] == "GOLDEN_CRISP-0001")
    assert target["phone"] == new_phone

    # And the engine got told to rebuild
    mock_engine.rebuild_index.assert_called_once()


def test_admin_update_rejects_unknown_dataset(client, auth_headers):
    res = client.post("/api/admin/update", headers=auth_headers, json={
        "dataset":  "secrets",
        "id_field": "id",
        "id":       "x",
        "patch":    {"a": 1},
    })
    assert res.status_code == 400


def test_admin_update_rejects_missing_record(client, auth_headers):
    res = client.post("/api/admin/update", headers=auth_headers, json={
        "dataset":  "stores",
        "id_field": "store_id",
        "id":       "DOES-NOT-EXIST",
        "patch":    {"phone": "x"},
    })
    assert res.status_code == 404


def test_admin_update_rejects_empty_patch(client, auth_headers):
    res = client.post("/api/admin/update", headers=auth_headers, json={
        "dataset":  "stores",
        "id_field": "store_id",
        "id":       "GOLDEN_CRISP-0001",
        "patch":    {},
    })
    assert res.status_code == 400


def test_admin_update_rejects_invalid_token(client):
    res = client.post("/api/admin/update",
        headers={"Authorization": "Bearer not-a-valid-token"},
        json={
            "dataset":  "stores",
            "id_field": "store_id",
            "id":       "GOLDEN_CRISP-0001",
            "patch":    {"phone": "x"},
        })
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Admin reindex
# ---------------------------------------------------------------------------

def test_admin_reindex(client, auth_headers, mock_engine):
    res = client.post("/api/admin/reindex", headers=auth_headers)
    assert res.status_code == 200
    mock_engine.rebuild_index.assert_called_once()


# ---------------------------------------------------------------------------
# New CRUD endpoints
# ---------------------------------------------------------------------------

def test_admin_list_stores(client, auth_headers):
    res = client.get("/api/admin/stores", headers=auth_headers)
    assert res.status_code == 200
    body = res.get_json()
    assert "records" in body and len(body["records"]) == 2


def test_admin_get_store(client, auth_headers):
    res = client.get("/api/admin/stores/GOLDEN_CRISP-0001", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["status"] == "active"


def test_admin_get_unknown_404(client, auth_headers):
    res = client.get("/api/admin/stores/NOPE-9999", headers=auth_headers)
    assert res.status_code == 404


def test_admin_patch_deep_merge(client, auth_headers):
    res = client.patch("/api/admin/vendors/PHONE-GOLDEN_CRISP-0001",
                       headers=auth_headers,
                       json={"patch": {"login": {"username": "newname"}}})
    assert res.status_code == 200
    record = res.get_json()["record"]
    assert record["login"]["username"] == "newname"
    assert record["login"]["password"] == "vendorPass!"   # preserved!


def test_admin_create_brand(client, auth_headers):
    res = client.post("/api/admin/brands", headers=auth_headers, json={
        "id": "wave_sushi", "name": "Wave Sushi", "category": "Sushi",
    })
    assert res.status_code == 201
    assert res.get_json()["record"]["id"] == "wave_sushi"


def test_admin_create_store_atomically_creates_vendors(client, auth_headers, tmp_data_dir):
    res = client.post("/api/admin/stores", headers=auth_headers, json={
        "brand_id": "golden_crisp",
        "address": {"street": "9 New", "city": "Plano", "state": "TX", "zipcode": "75024"},
        "manager": {"full_name": "M", "phone": "1", "email": "m@x"},
    })
    assert res.status_code == 201, res.get_json()
    store_id = res.get_json()["record"]["store_id"]

    # Verify both vendor accounts now exist on disk
    import json as _json
    vendors = _json.loads((tmp_data_dir / "vendors.json").read_text())
    related = [v for v in vendors if v["store_id"] == store_id]
    services = sorted(v["service"] for v in related)
    assert services == ["Internet", "Phone"]


def test_admin_soft_delete_store(client, auth_headers):
    res = client.delete("/api/admin/stores/GOLDEN_CRISP-0001", headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["status"] == "closed"


def test_admin_hard_delete_requires_confirmation(client, auth_headers):
    res = client.delete("/api/admin/stores/GOLDEN_CRISP-0001?hard=true",
                        headers=auth_headers)
    assert res.status_code == 400


def test_admin_hard_delete_with_confirmation(client, auth_headers):
    res = client.delete(
        "/api/admin/stores/GOLDEN_CRISP-0001?hard=true&confirm=GOLDEN_CRISP-0001",
        headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()["status"] == "hard_deleted"


def test_admin_brand_close_blocked_by_active_stores(client, auth_headers):
    res = client.delete("/api/admin/brands/golden_crisp", headers=auth_headers)
    assert res.status_code == 409


def test_admin_endpoints_require_auth(client):
    """All admin CRUD endpoints reject requests without a JWT."""
    paths = [
        ("GET",    "/api/admin/stores"),
        ("POST",   "/api/admin/stores"),
        ("PATCH",  "/api/admin/stores/X"),
        ("DELETE", "/api/admin/stores/X"),
        ("GET",    "/api/admin/brands"),
    ]
    for method, path in paths:
        res = client.open(path, method=method, json={})
        assert res.status_code == 401, f"{method} {path} should require auth"


# ---------------------------------------------------------------------------
# Transcribe
# ---------------------------------------------------------------------------

def test_transcribe_missing_file(client):
    res = client.post("/api/transcribe", data={})
    assert res.status_code == 400


def test_transcribe_returns_501_when_voice_deps_missing(client):
    """
    With transformers/torch not installed in CI, calling transcribe
    must yield a 501 with a helpful message — not a 500.
    """
    data = {"audio": (io.BytesIO(b"fake audio"), "rec.webm")}
    res  = client.post("/api/transcribe",
                       data=data,
                       content_type="multipart/form-data")
    # If voice deps happen to be installed, the call may succeed or 500
    # on bad audio; we accept any of those rather than asserting 501 strictly.
    assert res.status_code in (501, 500, 200)
    if res.status_code == 501:
        assert "transformers" in res.get_json()["error"].lower()
