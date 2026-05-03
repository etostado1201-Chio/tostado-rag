"""Tests for backend.followups: rule-based follow-up suggestion engine."""

from __future__ import annotations

from backend.followups import MAX_SUGGESTIONS, build_followups


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def src(meta: dict, content: str = "irrelevant") -> dict:
    return {"content": content, "metadata": meta}


# ---------------------------------------------------------------------------
# Source-type-driven suggestions
# ---------------------------------------------------------------------------

def test_store_followups_mention_the_store_id():
    out = build_followups([src({"type": "store", "store_id": "GOLDEN_CRISP-0001"})])
    assert len(out) == MAX_SUGGESTIONS
    assert all("GOLDEN_CRISP-0001" in q for q in out)


def test_store_followups_cover_vendor_and_org():
    out = build_followups([src({"type": "store", "store_id": "STONE_FIRE-0007"})])
    blob = " ".join(out).lower()
    assert "vendor" in blob or "phone" in blob or "internet" in blob
    assert "district" in blob or "vp" in blob


def test_vendor_followups_offer_the_other_service():
    """If the user asked about Phone, suggest Internet for the same store."""
    phone = build_followups([src({
        "type": "vendor",
        "store_id": "GOLDEN_CRISP-0001",
        "service":  "Phone",
    })])
    assert any("internet" in q.lower() for q in phone)
    assert all("phone" not in q.lower() or "GOLDEN_CRISP-0001" in q for q in phone)

    internet = build_followups([src({
        "type": "vendor",
        "store_id": "GOLDEN_CRISP-0001",
        "service":  "Internet",
    })])
    assert any("phone" in q.lower() for q in internet)


def test_department_followups_mention_the_department_name():
    out = build_followups([src({"type": "department", "department": "IT"})])
    assert all("IT" in q for q in out)


def test_employee_followups_pivot_to_their_department():
    out = build_followups([src({
        "type": "employee",
        "employee_id": "EMP-IT-001",
        "department":  "IT",
    })])
    blob = " ".join(out).lower()
    assert "department" in blob or "team" in blob
    assert "it" in blob


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_sources_falls_back_to_generic_suggestions():
    out = build_followups([])
    assert len(out) > 0
    assert len(out) <= MAX_SUGGESTIONS


def test_none_sources_does_not_crash():
    out = build_followups(None)
    assert isinstance(out, list)
    assert len(out) > 0


def test_unknown_source_type_falls_back_cleanly():
    out = build_followups([src({"type": "spaceship"})])
    # Falls back to the generic list rather than raising.
    assert isinstance(out, list)
    assert len(out) > 0


def test_returns_at_most_three():
    """Even if there's a flood of sources, we cap at MAX_SUGGESTIONS."""
    sources = [src({"type": "store", "store_id": f"GOLDEN_CRISP-{i:04d}"})
               for i in range(20)]
    out = build_followups(sources)
    assert len(out) <= MAX_SUGGESTIONS


def test_does_not_echo_the_users_previous_question():
    """If the user just asked about the address, don't suggest the same."""
    asked = "What is the address and opening date of GOLDEN_CRISP-0001?"
    out = build_followups(
        [src({"type": "store", "store_id": "GOLDEN_CRISP-0001"})],
        asked=asked,
    )
    assert "What is the address and opening date of GOLDEN_CRISP-0001?" not in out


def test_suggestions_are_phrased_as_questions():
    """Every suggestion should be a usable next prompt."""
    out = build_followups([src({"type": "store", "store_id": "GOLDEN_CRISP-0001"})])
    for q in out:
        assert q.endswith("?") or q.endswith("."), f"unfriendly suggestion: {q!r}"
        assert len(q) >= 10, f"suggestion too short: {q!r}"


def test_suggestions_are_unique():
    out = build_followups([src({"type": "store", "store_id": "GOLDEN_CRISP-0001"})])
    assert len(out) == len(set(out))
