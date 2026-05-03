"""
eval_dataset.py
---------------
Hand-curated evaluation set for the RAG retrieval pipeline.

Each item is a question paired with the document the retriever
*should* return as the most relevant. We use this to compute
recall@k and MRR — the standard retrieval metrics.

Why hand-curated and not LLM-generated? Self-generated eval data
leaks the same biases the system has, so the score lies. A small
manually-built set is a more honest baseline.

The expected IDs assume the dataset built with `Faker.seed(42)` and
`random.seed(42)` in scripts/generate_data.py — keep those seeds
stable or this file goes out of date.

Schema:
    {
        "question":       str,
        "expected_id":    str,           # e.g. "GOLDEN_CRISP-0001"
        "expected_field": str,           # which metadata field carries the id
                                          # ("store_id", "department", ...)
        "category":       str,           # store / vendor / department / employee
    }
"""

from __future__ import annotations

# Each section paraphrases the same retrieval target several different ways
# so we test embedding robustness, not just exact-match retrieval.

EVAL_QUESTIONS: list[dict] = [
    # ------------------------------------------------------------------
    # Stores — direct & paraphrased
    # ------------------------------------------------------------------
    {"question": "Who is the store manager of GOLDEN_CRISP-0001?",
     "expected_id": "GOLDEN_CRISP-0001", "expected_field": "store_id", "category": "store"},
    {"question": "Give me the address and phone of GOLDEN_CRISP-0001.",
     "expected_id": "GOLDEN_CRISP-0001", "expected_field": "store_id", "category": "store"},
    {"question": "Who runs store GOLDEN_CRISP-0001 and how can I reach them?",
     "expected_id": "GOLDEN_CRISP-0001", "expected_field": "store_id", "category": "store"},

    {"question": "Tell me about STONE_FIRE-0001.",
     "expected_id": "STONE_FIRE-0001",   "expected_field": "store_id", "category": "store"},
    {"question": "Who's the manager at the Stone & Fire store STONE_FIRE-0001?",
     "expected_id": "STONE_FIRE-0001",   "expected_field": "store_id", "category": "store"},

    {"question": "What is the address of DAYBREAK-0001?",
     "expected_id": "DAYBREAK-0001",     "expected_field": "store_id", "category": "store"},
    {"question": "Contact info for the Daybreak Coffee location DAYBREAK-0001.",
     "expected_id": "DAYBREAK-0001",     "expected_field": "store_id", "category": "store"},

    {"question": "Where is GARDEN_CRATE-0001 and who manages it?",
     "expected_id": "GARDEN_CRATE-0001", "expected_field": "store_id", "category": "store"},
    {"question": "Manager and phone for GARDEN_CRATE-0001 please.",
     "expected_id": "GARDEN_CRATE-0001", "expected_field": "store_id", "category": "store"},

    {"question": "Manager of STONE_FIRE-0005?",
     "expected_id": "STONE_FIRE-0005",   "expected_field": "store_id", "category": "store"},
    {"question": "Who is in charge at GOLDEN_CRISP-0010?",
     "expected_id": "GOLDEN_CRISP-0010", "expected_field": "store_id", "category": "store"},
    {"question": "Give me the store details for DAYBREAK-0007.",
     "expected_id": "DAYBREAK-0007",     "expected_field": "store_id", "category": "store"},

    # ------------------------------------------------------------------
    # Vendor accounts (phone & internet)
    # ------------------------------------------------------------------
    {"question": "What's the phone provider for store GOLDEN_CRISP-0001?",
     "expected_id": "PHONE-GOLDEN_CRISP-0001", "expected_field": "vendor_account_id", "category": "vendor"},
    {"question": "Phone account number and login for GOLDEN_CRISP-0001.",
     "expected_id": "PHONE-GOLDEN_CRISP-0001", "expected_field": "vendor_account_id", "category": "vendor"},
    {"question": "How much does GOLDEN_CRISP-0001 pay for phone every month?",
     "expected_id": "PHONE-GOLDEN_CRISP-0001", "expected_field": "vendor_account_id", "category": "vendor"},

    {"question": "Internet provider for GOLDEN_CRISP-0001.",
     "expected_id": "NET-GOLDEN_CRISP-0001",   "expected_field": "vendor_account_id", "category": "vendor"},
    {"question": "Give me the internet account login for GOLDEN_CRISP-0001.",
     "expected_id": "NET-GOLDEN_CRISP-0001",   "expected_field": "vendor_account_id", "category": "vendor"},

    {"question": "Phone account for STONE_FIRE-0001.",
     "expected_id": "PHONE-STONE_FIRE-0001",   "expected_field": "vendor_account_id", "category": "vendor"},
    {"question": "What internet plan does STONE_FIRE-0001 use?",
     "expected_id": "NET-STONE_FIRE-0001",     "expected_field": "vendor_account_id", "category": "vendor"},

    {"question": "Internet credentials for DAYBREAK-0001.",
     "expected_id": "NET-DAYBREAK-0001",       "expected_field": "vendor_account_id", "category": "vendor"},
    {"question": "Phone bill amount for GARDEN_CRATE-0001.",
     "expected_id": "PHONE-GARDEN_CRATE-0001", "expected_field": "vendor_account_id", "category": "vendor"},

    # ------------------------------------------------------------------
    # Departments
    # ------------------------------------------------------------------
    {"question": "Who runs the IT department?",
     "expected_id": "IT",              "expected_field": "department", "category": "department"},
    {"question": "Who is the IT department admin contact?",
     "expected_id": "IT",              "expected_field": "department", "category": "department"},
    {"question": "Tell me about the IT department.",
     "expected_id": "IT",              "expected_field": "department", "category": "department"},

    {"question": "Who heads the Finance department?",
     "expected_id": "Finance",         "expected_field": "department", "category": "department"},
    {"question": "Finance team lead, please.",
     "expected_id": "Finance",         "expected_field": "department", "category": "department"},

    {"question": "Marketing department head and admin.",
     "expected_id": "Marketing",       "expected_field": "department", "category": "department"},
    {"question": "Who runs HR?",
     "expected_id": "Human Resources", "expected_field": "department", "category": "department"},
    {"question": "Tell me about Human Resources.",
     "expected_id": "Human Resources", "expected_field": "department", "category": "department"},

    {"question": "Procurement department contact.",
     "expected_id": "Procurement",     "expected_field": "department", "category": "department"},
    {"question": "Real Estate team head.",
     "expected_id": "Real Estate",     "expected_field": "department", "category": "department"},
    {"question": "Operations department leadership.",
     "expected_id": "Operations",      "expected_field": "department", "category": "department"},

    # ------------------------------------------------------------------
    # Stores again — different brands, no exact ID, brand cue only
    # (these are harder — embedding has to bridge from a brand name to a store)
    # ------------------------------------------------------------------
    {"question": "Show me a Pollo Dorado-style chicken store from our roster.",
     # Deprecated brand — should NOT match; checks the model isn't hallucinating.
     "expected_id": "GOLDEN_CRISP-0001", "expected_field": "store_id", "category": "store"},

    # Generic cross-cutting — keeps the eval honest about edge cases
    {"question": "Who is the VP of Operations for the first Stone & Fire district?",
     "expected_id": "STONE_FIRE-0001", "expected_field": "store_id", "category": "store"},
    {"question": "First fried chicken store on the books.",
     "expected_id": "GOLDEN_CRISP-0001", "expected_field": "store_id", "category": "store"},
    {"question": "Earliest Daybreak Coffee location.",
     "expected_id": "DAYBREAK-0001", "expected_field": "store_id", "category": "store"},
]


def total() -> int:
    return len(EVAL_QUESTIONS)


def by_category() -> dict[str, int]:
    counts: dict[str, int] = {}
    for q in EVAL_QUESTIONS:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    return counts
