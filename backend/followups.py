"""
followups.py
------------
Generates 2-3 follow-up question suggestions for the chat UI based on
the metadata of the documents the retriever returned for the previous
question.

This is rule-based on purpose: it's instant, free, and deterministic,
which means it's also trivially testable. No second LLM call.

The general idea: if the answer was about a store, the user's natural
next questions are about that store's vendor accounts and its leadership.
If it was about a department, the natural follow-up is about the
department head or its admin contact.

Public API:
    build_followups(sources: list[dict], asked: str) -> list[str]
"""

from __future__ import annotations

from typing import Iterable

# How many suggestions to return at most.
MAX_SUGGESTIONS = 3


def _primary_source(sources: Iterable[dict]) -> dict | None:
    """The most relevant retrieved doc — first non-empty one."""
    for s in sources or []:
        if s and s.get("metadata"):
            return s
    return None


def _seen(question: str, asked: str) -> bool:
    """Avoid suggesting something the user just asked."""
    a = (asked or "").lower()
    q = question.lower()
    # very loose match: avoid offering a near-duplicate
    return q in a or any(part in a for part in q.split(" about ")[-1:])


def _suggestions_for_store(meta: dict) -> list[str]:
    sid = meta.get("store_id", "this store")
    return [
        f"Show me the phone and internet vendor accounts for {sid}.",
        f"Who is the district manager and VP of Operations for {sid}?",
        f"What is the address and opening date of {sid}?",
    ]


def _suggestions_for_vendor(meta: dict) -> list[str]:
    sid     = meta.get("store_id", "this store")
    service = meta.get("service",  "this service").lower()
    other   = "internet" if service == "phone" else "phone"
    return [
        f"Show me the {other} account for {sid}.",
        f"Who is the store manager of {sid}?",
        f"What is the address of {sid}?",
    ]


def _suggestions_for_department(meta: dict) -> list[str]:
    dept = meta.get("department", "this department")
    return [
        f"Who works in the {dept} department?",
        f"Who is the admin contact for {dept}?",
        f"List the team members of the {dept} department.",
    ]


def _suggestions_for_employee(meta: dict) -> list[str]:
    dept = meta.get("department", "their department")
    return [
        f"Who is the head of the {dept} department?",
        f"Who else works in {dept}?",
        f"Who is the admin contact for {dept}?",
    ]


_DISPATCH = {
    "store":      _suggestions_for_store,
    "vendor":     _suggestions_for_vendor,
    "department": _suggestions_for_department,
    "employee":   _suggestions_for_employee,
}


# Used when the retriever returned nothing useful, or the type isn't one
# of the four we know how to follow up on.
_FALLBACK = [
    "List a few stores in the Golden Crisp brand.",
    "Who is the VP of Operations for Stone & Fire?",
    "Who is the admin contact for the IT department?",
]


def build_followups(sources: list[dict] | None, asked: str = "") -> list[str]:
    """
    Build up to MAX_SUGGESTIONS follow-up question strings for the UI.

    Parameters
    ----------
    sources : list[dict]
        The `sources` list returned by `RAGEngine.ask`. Each item is
        expected to have at least a `metadata` dict.
    asked : str
        The user's previous question. Used to avoid repeating it.

    Returns
    -------
    list[str]
        Between 0 and MAX_SUGGESTIONS suggestion strings. May be empty
        if `sources` is empty *and* the fallback is fully suppressed —
        in practice we always emit at least the fallback list so the UI
        has something to render.
    """
    primary = _primary_source(sources or [])

    if primary is None:
        candidates = list(_FALLBACK)
    else:
        meta    = primary["metadata"] or {}
        builder = _DISPATCH.get(meta.get("type", ""))
        candidates = builder(meta) if builder else list(_FALLBACK)

    # De-dup while keeping order, drop anything that echoes the prior question.
    out:  list[str] = []
    seen: set[str]  = set()
    for q in candidates:
        if q in seen or _seen(q, asked):
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= MAX_SUGGESTIONS:
            break

    return out
