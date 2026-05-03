"""
voice.py
--------
Speech-to-text via HuggingFace `transformers` + Whisper.

The dependencies (`transformers`, `torch`) are optional. If they are not
installed, `transcribe()` raises VoiceUnavailable and the Flask route
returns 501 with a helpful hint.

Model: openai/whisper-tiny.en  (~75 MB, fast on CPU, English only)
Swap to "openai/whisper-tiny" for multilingual or "openai/whisper-base"
for higher accuracy.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "openai/whisper-tiny.en")


class VoiceUnavailable(RuntimeError):
    """Raised when transformers/torch are not installed."""


_pipeline = None


def _load_pipeline():
    """Lazy-load the Whisper pipeline on first use."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    try:
        from transformers import pipeline
    except ImportError as e:
        raise VoiceUnavailable(
            "Voice features require the 'transformers' and 'torch' packages. "
            "Install them with:  pip install -r requirements-voice.txt"
        ) from e

    print(f"[Voice] Loading Whisper model: {WHISPER_MODEL}")
    _pipeline = pipeline("automatic-speech-recognition", model=WHISPER_MODEL)
    print("[Voice] Whisper ready.")
    return _pipeline


def transcribe(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """
    Transcribe an audio blob to text.

    The pipeline relies on ffmpeg to decode whatever container/codec the
    browser's MediaRecorder produced, so the system must have ffmpeg
    installed (see README).
    """
    pipe = _load_pipeline()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        result = pipe(str(tmp_path))
        text = (result.get("text") or "").strip() if isinstance(result, dict) else str(result).strip()
        return text
    finally:
        tmp_path.unlink(missing_ok=True)
