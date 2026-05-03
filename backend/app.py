"""
app.py
------
Flask backend for the Tostado Restaurant Group chatbot.

Endpoints
---------
GET  /                      Serve the chat UI (frontend/index.html)
GET  /admin                 Serve the admin UI  (frontend/admin.html)
POST /api/chat              Public — ask a question to the RAG pipeline
POST /api/transcribe        Public — speech-to-text (HuggingFace Whisper)
POST /api/login             Department-admin login -> JWT
POST /api/admin/update      Update a JSON record (auth required)
POST /api/admin/reindex     Rebuild the FAISS index (auth required)
GET  /api/health            Liveness probe

The app is built via a factory (`create_app`) so that tests can inject
a mock RAG engine and a temporary data directory without touching Ollama
or sentence-transformers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from .auth import (
    find_admin,
    issue_token,
    require_admin,
    verify_password,
)
from .crud import (
    CrudError,
    DATASETS,
    create_record,
    get_record,
    hard_delete_record,
    list_records,
    soft_delete_record,
    update_record,
)
from .followups import build_followups
from .logging_config import configure_logging
from .metrics import metrics
from .voice import VoiceUnavailable, transcribe

configure_logging()
log = logging.getLogger("tostado.app")


ROOT          = Path(__file__).resolve().parent.parent
FRONTEND_DIR  = ROOT / "frontend"
DEFAULT_DATA  = ROOT / "data"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(engine=None, data_dir: Optional[Path] = None) -> Flask:
    """
    Build a configured Flask app.

    Parameters
    ----------
    engine : object
        Anything with `.ask(question)` returning {"answer", "sources"}
        and `.rebuild_index()`. If None, a real RAGEngine is built and
        loaded — this requires Ollama + the embedding model.
    data_dir : Path
        Directory containing the JSON datasets. Defaults to <repo>/data.
    """
    data_dir = data_dir or DEFAULT_DATA

    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    CORS(app)

    if engine is None:
        # Local import — keeps tests from pulling sentence-transformers/torch.
        from .rag_engine import RAGEngine
        engine = RAGEngine()
        engine.build_or_load_index()

    # ------------------------------------------------------------------
    # Static UI
    # ------------------------------------------------------------------

    @app.get("/")
    def home():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/admin")
    def admin_page():
        return send_from_directory(FRONTEND_DIR, "admin.html")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/metrics")
    def metrics_endpoint():
        """In-process metrics snapshot (counters + latency percentiles)."""
        return jsonify(metrics.snapshot())

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        question = (body.get("message") or "").strip()
        if not question:
            metrics.incr("chat.errors")
            return jsonify({"error": "Empty message"}), 400

        with metrics.timer("chat"):
            result = engine.ask(question)

        followups = build_followups(result.get("sources"), asked=question)
        log.info("chat", extra={
            "question_chars": len(question),
            "n_sources":      len(result.get("sources") or []),
            "n_followups":    len(followups),
        })
        return jsonify({
            "answer":    result["answer"],
            "sources":   result["sources"],
            "followups": followups,
        })

    # ------------------------------------------------------------------
    # Speech-to-text (Whisper)
    # ------------------------------------------------------------------

    @app.post("/api/transcribe")
    def transcribe_audio():
        if "audio" not in request.files:
            metrics.incr("transcribe.errors")
            return jsonify({"error": "Missing 'audio' file in form data"}), 400

        upload = request.files["audio"]
        audio_bytes = upload.read()
        if not audio_bytes:
            metrics.incr("transcribe.errors")
            return jsonify({"error": "Empty audio payload"}), 400

        suffix = Path(upload.filename or "rec.webm").suffix or ".webm"

        try:
            with metrics.timer("transcribe"):
                text = transcribe(audio_bytes, suffix=suffix)
        except VoiceUnavailable as e:
            metrics.incr("transcribe.unavailable")
            return jsonify({"error": str(e)}), 501
        except Exception as e:                              # noqa: BLE001
            metrics.incr("transcribe.errors")
            log.exception("transcription failed")
            return jsonify({"error": f"Transcription failed: {e}"}), 500

        log.info("transcribed", extra={"chars": len(text)})
        return jsonify({"text": text})

    # ------------------------------------------------------------------
    # Admin auth
    # ------------------------------------------------------------------

    @app.post("/api/login")
    def login():
        body     = request.get_json(silent=True) or {}
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""

        with metrics.timer("login"):
            admin = find_admin(username, data_dir=data_dir)
            if not admin or not verify_password(password, admin["password_hash"]):
                metrics.incr("login.failed")
                log.warning("login_failed", extra={"username": username})
                return jsonify({"error": "Invalid credentials"}), 401

            token = issue_token(admin)

        log.info("login_ok", extra={"username": admin["username"], "department": admin["department"]})
        return jsonify({
            "token":      token,
            "department": admin["department"],
            "username":   admin["username"],
        })

    # ------------------------------------------------------------------
    # Admin CRUD
    # ------------------------------------------------------------------

    @app.get("/api/admin/<dataset>")
    @require_admin
    def admin_list(dataset: str):
        """List all records in a dataset. Useful for the admin UI dropdowns."""
        if dataset not in DATASETS:
            return jsonify({"error": f"Unknown dataset: {dataset}"}), 400
        return jsonify({"records": list_records(data_dir, dataset)})

    @app.get("/api/admin/<dataset>/<path:record_id>")
    @require_admin
    def admin_get(dataset: str, record_id: str):
        try:
            return jsonify(get_record(data_dir, dataset, record_id))
        except CrudError as e:
            return jsonify({"error": str(e)}), e.status_code

    @app.post("/api/admin/<dataset>")
    @require_admin
    def admin_create(dataset: str):
        body = request.get_json(silent=True) or {}
        try:
            with metrics.timer("admin.create"):
                created = create_record(data_dir, dataset, body)
            with metrics.timer("admin.reindex"):
                engine.rebuild_index()
        except CrudError as e:
            return jsonify({"error": str(e)}), e.status_code

        log.info("admin_create", extra={
            "by":         request.admin["sub"],
            "department": request.admin["department"],
            "dataset":    dataset,
        })
        return jsonify({"status": "created", "dataset": dataset, "record": created}), 201

    @app.patch("/api/admin/<dataset>/<path:record_id>")
    @require_admin
    def admin_patch(dataset: str, record_id: str):
        """Deep-merge patch — fixes the old shallow-update bug for nested fields."""
        body = request.get_json(silent=True) or {}
        patch = body.get("patch", body)        # accept either {"patch": {...}} or raw dict
        try:
            with metrics.timer("admin.update"):
                updated = update_record(data_dir, dataset, record_id, patch)
            with metrics.timer("admin.reindex"):
                engine.rebuild_index()
        except CrudError as e:
            return jsonify({"error": str(e)}), e.status_code

        log.info("admin_update", extra={
            "by":         request.admin["sub"],
            "department": request.admin["department"],
            "dataset":    dataset,
            "id":         record_id,
            "fields":     sorted(patch.keys()) if isinstance(patch, dict) else [],
        })
        return jsonify({"status": "updated", "dataset": dataset, "record": updated})

    @app.delete("/api/admin/<dataset>/<path:record_id>")
    @require_admin
    def admin_delete(dataset: str, record_id: str):
        """
        Soft delete by default (sets status=closed).
        Add `?hard=true` to remove the record from disk entirely.
        Hard delete also requires query param `confirm=<record_id>`
        so curl + UI both have to spell out the ID twice.
        """
        hard    = request.args.get("hard", "false").lower() == "true"
        confirm = request.args.get("confirm", "")

        try:
            if hard:
                if confirm != record_id:
                    return jsonify({
                        "error": "Hard delete requires ?confirm=<record_id> to match.",
                    }), 400
                with metrics.timer("admin.hard_delete"):
                    result = hard_delete_record(data_dir, dataset, record_id)
            else:
                closed_on = request.args.get("closed_on")
                with metrics.timer("admin.soft_delete"):
                    result = soft_delete_record(data_dir, dataset, record_id, closed_on)
            with metrics.timer("admin.reindex"):
                engine.rebuild_index()
        except CrudError as e:
            return jsonify({"error": str(e)}), e.status_code

        log.warning("admin_delete", extra={
            "by":         request.admin["sub"],
            "department": request.admin["department"],
            "dataset":    dataset,
            "id":         record_id,
            "hard":       hard,
        })
        return jsonify({"status": "hard_deleted" if hard else "closed",
                        "dataset": dataset, "result": result})

    @app.post("/api/admin/reindex")
    @require_admin
    def admin_reindex():
        with metrics.timer("admin.reindex"):
            engine.rebuild_index()
        return jsonify({"status": "reindexed", "by": request.admin["sub"]})


    # ------------------------------------------------------------------
    # Backwards-compatibility — original /api/admin/update
    # ------------------------------------------------------------------

    @app.post("/api/admin/update")
    @require_admin
    def admin_update_legacy():
        """
        Original endpoint kept so existing tests / scripts don't break.
        New code should call PATCH /api/admin/<dataset>/<id>.
        """
        body      = request.get_json(silent=True) or {}
        dataset   = body.get("dataset")
        record_id = body.get("id")
        patch     = body.get("patch") or {}

        if dataset not in DATASETS:
            return jsonify({"error": f"dataset must be one of {sorted(DATASETS)}"}), 400
        if not record_id:
            return jsonify({"error": "id is required"}), 400

        try:
            with metrics.timer("admin.update"):
                updated = update_record(data_dir, dataset, record_id, patch)
            with metrics.timer("admin.reindex"):
                engine.rebuild_index()
        except CrudError as e:
            return jsonify({"error": str(e)}), e.status_code

        log.info("admin_update", extra={
            "by":         request.admin["sub"],
            "department": request.admin["department"],
            "dataset":    dataset,
            "id":         record_id,
            "fields":     sorted(patch.keys()),
        })
        return jsonify({
            "status":     "updated",
            "dataset":    dataset,
            "id":         record_id,
            "updated_by": request.admin["sub"],
            "department": request.admin["department"],
        })

    return app


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)
