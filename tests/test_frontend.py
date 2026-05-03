"""
Tests for the static frontend assets.

These don't need a real browser — they parse the HTML / read the JS
text and verify that the suggestion chips and the JS code that wires
them up are present and correct.

We catch regressions like:
  * a developer renames a brand and forgets to update the chips
  * the click handler is removed
  * a chip's `data-prompt` no longer matches what's shown to the user
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT          = Path(__file__).resolve().parent.parent
INDEX_HTML    = ROOT / "frontend" / "index.html"
CHAT_JS       = ROOT / "frontend" / "js" / "chat.js"


# ---------------------------------------------------------------------------
# Tiny HTML parser that pulls out every <li data-prompt="..."> inside
# <ul class="suggestions">
# ---------------------------------------------------------------------------

class SuggestionExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_suggestions  = False
        self.depth_in_ul     = 0
        self._current_prompt: str | None = None
        self._current_text:   list[str]  = []
        self.items:           list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "ul" and attr_dict.get("class") == "suggestions":
            self.in_suggestions = True
            self.depth_in_ul = 1
            return
        if not self.in_suggestions:
            return
        self.depth_in_ul += 1
        if tag == "li":
            self._current_prompt = attr_dict.get("data-prompt")
            self._current_text   = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_suggestions:
            return
        if tag == "li" and self._current_prompt is not None:
            self.items.append({
                "prompt":  self._current_prompt,
                "label":   "".join(self._current_text).strip(),
            })
            self._current_prompt = None
        self.depth_in_ul -= 1
        if tag == "ul" and self.depth_in_ul == 0:
            self.in_suggestions = False

    def handle_data(self, data: str) -> None:
        if self.in_suggestions and self._current_prompt is not None:
            self._current_text.append(data)


@pytest.fixture(scope="module")
def suggestion_chips() -> list[dict]:
    parser = SuggestionExtractor()
    parser.feed(INDEX_HTML.read_text(encoding="utf-8"))
    return parser.items


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_index_html_exists():
    assert INDEX_HTML.exists(), "frontend/index.html is missing"


def test_chat_js_exists():
    assert CHAT_JS.exists(), "frontend/js/chat.js is missing"


def test_there_are_exactly_four_suggestion_chips(suggestion_chips):
    # Four chips, one per brand area or per common workflow.
    assert len(suggestion_chips) == 4, (
        f"expected 4 suggestion chips, got {len(suggestion_chips)}: "
        f"{[c['label'] for c in suggestion_chips]}"
    )


def test_every_chip_has_a_non_empty_prompt(suggestion_chips):
    for chip in suggestion_chips:
        assert chip["prompt"].strip(), f"chip with empty prompt: {chip}"


def test_every_chip_has_a_visible_label(suggestion_chips):
    for chip in suggestion_chips:
        assert chip["label"], f"chip with empty visible label: {chip}"


def test_chips_cover_the_four_main_query_categories(suggestion_chips):
    """
    The four chips are intentional onboarding scaffolding: each one points
    the user at one of the four data domains they can query.
        1. a store manager (people)
        2. a vendor account (vendor / credentials)
        3. a brand-level role (org chart)
        4. a corporate department
    If we ever drift away from that coverage, this test should fail
    loudly so we can rewrite the chips on purpose, not by accident.
    """
    prompts_lower = " ".join(c["prompt"].lower() for c in suggestion_chips)

    assert "store manager"     in prompts_lower, "no chip about store manager"
    assert "internet"          in prompts_lower or "vendor" in prompts_lower, "no chip about vendor accounts"
    assert "vp of operations"  in prompts_lower, "no chip about VP of Operations"
    assert "department"        in prompts_lower, "no chip about a corporate department"


def test_chips_reference_real_store_id_format(suggestion_chips):
    """
    At least one chip must reference a synthetic store ID in the format
    BRAND_SLUG-#### so users see the format they're expected to use.
    """
    pattern = re.compile(r"[A-Z_]+-\d{4}")
    matches = [
        c for c in suggestion_chips
        if pattern.search(c["prompt"])
    ]
    assert matches, "no chip mentions a store ID in BRAND-#### format"


def test_chips_use_current_brand_names(suggestion_chips):
    """
    Catch the regression we already had once: a brand rename that
    leaves stale Spanish names in the chips.
    """
    deprecated = ["Pollo Dorado", "Forno Rosso", "Café Aurora", "Verde Vivo",
                  "POLLO_DORADO",  "FORNO_ROSSO",  "CAFE_AURORA",  "VERDE_VIVO"]
    blob = " ".join(c["prompt"] + " " + c["label"] for c in suggestion_chips)
    for name in deprecated:
        assert name not in blob, f"deprecated brand name still in chips: {name}"


def test_chat_js_wires_up_chip_clicks():
    """
    Make sure the JS that turns a chip click into a populated input box
    is still present.
    """
    js = CHAT_JS.read_text(encoding="utf-8")
    # Selector for the chips
    assert ".suggestions li" in js, "chat.js no longer queries '.suggestions li'"
    # Click handler that pulls the data-prompt attribute
    assert "data-prompt" not in js or "dataset.prompt" in js, (
        "chat.js should read the data-prompt attribute via dataset.prompt"
    )
    assert "addEventListener(\"click\"" in js, (
        "chat.js no longer registers a click handler on chips"
    )
    # The handler must populate the textarea
    assert "inputEl.value" in js, "click handler should populate the input"
