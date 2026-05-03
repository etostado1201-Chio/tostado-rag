"""
evaluate_rag.py
---------------
Evaluation harness for the retrieval pipeline of Tostado Restaurant Group.

Reports the standard retrieval-eval triad:

    Recall@k    — was the correct doc returned in the top-k results?
    MRR         — Mean Reciprocal Rank: 1/rank_of_first_correct, averaged
    Latency     — p50 / p95 ms per retrieval call

Plus a per-category breakdown (store / vendor / department) so we can
spot weak spots (e.g. vendor accounts under-perform vs stores).

Run:
    # Retrieval-only (fast, no Ollama needed):
    python scripts/evaluate_rag.py

    # Full pipeline (also asks the LLM for each question):
    python scripts/evaluate_rag.py --with-llm

The output is human-readable on stdout *and* written to
`docs/eval_results.md` so it can be linked from the README.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                          # so `backend` imports

from backend.rag_engine import RAGEngine               # noqa: E402
from scripts.eval_dataset import EVAL_QUESTIONS, by_category, total  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_matches(doc, expected_id: str, expected_field: str) -> bool:
    """Does this retrieved Document match the expected target?"""
    return str(doc.metadata.get(expected_field, "")) == str(expected_id)


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[idx]


# ---------------------------------------------------------------------------
# Eval loop
# ---------------------------------------------------------------------------

def evaluate(with_llm: bool = False) -> dict:
    print(f"Loading RAG engine ({'with LLM' if with_llm else 'retrieval-only'})...")
    engine = RAGEngine()
    engine.build_or_load_index()
    retriever = engine.vectorstore.as_retriever(search_kwargs={"k": 6})

    n = len(EVAL_QUESTIONS)
    print(f"Running eval on {n} questions across {len(by_category())} categories...\n")

    hits_at_1   = 0
    hits_at_3   = 0
    hits_at_6   = 0
    rr_scores: list[float] = []
    retrieval_ms: list[float] = []
    llm_ms:       list[float] = []
    per_category: dict[str, dict[str, int]] = {
        cat: {"total": 0, "hit@1": 0, "hit@3": 0, "hit@6": 0}
        for cat in by_category()
    }
    misses: list[dict] = []

    for i, item in enumerate(EVAL_QUESTIONS, 1):
        t0 = time.perf_counter()
        docs = retriever.invoke(item["question"])
        retrieval_ms.append((time.perf_counter() - t0) * 1000)

        # Find rank (1-indexed) of the first matching doc, or None.
        rank = next(
            (idx + 1 for idx, d in enumerate(docs)
             if _doc_matches(d, item["expected_id"], item["expected_field"])),
            None,
        )

        cat = item["category"]
        per_category[cat]["total"] += 1

        if rank == 1:
            hits_at_1 += 1
            per_category[cat]["hit@1"] += 1
        if rank is not None and rank <= 3:
            hits_at_3 += 1
            per_category[cat]["hit@3"] += 1
        if rank is not None and rank <= 6:
            hits_at_6 += 1
            per_category[cat]["hit@6"] += 1
            rr_scores.append(1.0 / rank)
        else:
            rr_scores.append(0.0)
            misses.append({
                "question":    item["question"],
                "expected":    item["expected_id"],
                "top_result":  docs[0].metadata if docs else None,
            })

        if with_llm:
            t0 = time.perf_counter()
            engine.ask(item["question"])
            llm_ms.append((time.perf_counter() - t0) * 1000)

        marker = "✓" if rank == 1 else ("·" if rank else "✗")
        print(f"  [{i:2d}/{n}] {marker}  {item['question'][:70]}")

    # ----------------------------------------------------------------
    # Roll-up
    # ----------------------------------------------------------------
    summary = {
        "total":          n,
        "recall_at_1":    round(hits_at_1 / n, 3),
        "recall_at_3":    round(hits_at_3 / n, 3),
        "recall_at_6":    round(hits_at_6 / n, 3),
        "mrr":            round(mean(rr_scores), 3),
        "retrieval_p50_ms": round(_percentile(retrieval_ms, .5), 1),
        "retrieval_p95_ms": round(_percentile(retrieval_ms, .95), 1),
        "by_category": {
            cat: {
                "n":        v["total"],
                "recall@1": round(v["hit@1"] / v["total"], 3) if v["total"] else 0,
                "recall@3": round(v["hit@3"] / v["total"], 3) if v["total"] else 0,
                "recall@6": round(v["hit@6"] / v["total"], 3) if v["total"] else 0,
            }
            for cat, v in per_category.items()
        },
        "misses":         misses,
        "with_llm":       with_llm,
    }
    if with_llm:
        summary["llm_p50_ms"] = round(_percentile(llm_ms, .5),  1)
        summary["llm_p95_ms"] = round(_percentile(llm_ms, .95), 1)
    return summary


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(s: dict) -> None:
    print("\n" + "=" * 64)
    print(f"  RAG retrieval evaluation — {s['total']} questions")
    print("=" * 64)
    print(f"  Recall@1   : {s['recall_at_1']*100:5.1f}%   ({int(s['recall_at_1']*s['total'])}/{s['total']})")
    print(f"  Recall@3   : {s['recall_at_3']*100:5.1f}%   ({int(s['recall_at_3']*s['total'])}/{s['total']})")
    print(f"  Recall@6   : {s['recall_at_6']*100:5.1f}%   ({int(s['recall_at_6']*s['total'])}/{s['total']})")
    print(f"  MRR        : {s['mrr']:5.3f}")
    print(f"  Retrieval  : p50 {s['retrieval_p50_ms']:>5.1f} ms · p95 {s['retrieval_p95_ms']:>5.1f} ms")
    if s["with_llm"]:
        print(f"  LLM answer : p50 {s['llm_p50_ms']:>5.1f} ms · p95 {s['llm_p95_ms']:>5.1f} ms")
    print()
    print("  By category:")
    print(f"    {'category':<14} {'n':>3} {'r@1':>7} {'r@3':>7} {'r@6':>7}")
    for cat, v in s["by_category"].items():
        print(f"    {cat:<14} {v['n']:>3} {v['recall@1']*100:>6.1f}% {v['recall@3']*100:>6.1f}% {v['recall@6']*100:>6.1f}%")
    if s["misses"]:
        print(f"\n  {len(s['misses'])} miss(es) — first few:")
        for m in s["misses"][:5]:
            print(f"    ✗ {m['question'][:60]}")
            print(f"        expected {m['expected']}, top result {m['top_result']}")
    print()


def write_markdown(s: dict, path: Path) -> None:
    lines = [
        "# RAG retrieval evaluation",
        "",
        f"_Last run: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Questions          | {s['total']} |",
        f"| Recall@1           | {s['recall_at_1']*100:.1f}% |",
        f"| Recall@3           | {s['recall_at_3']*100:.1f}% |",
        f"| Recall@6           | {s['recall_at_6']*100:.1f}% |",
        f"| MRR                | {s['mrr']:.3f} |",
        f"| Retrieval p50 (ms) | {s['retrieval_p50_ms']} |",
        f"| Retrieval p95 (ms) | {s['retrieval_p95_ms']} |",
    ]
    if s["with_llm"]:
        lines += [
            f"| LLM p50 (ms)       | {s['llm_p50_ms']} |",
            f"| LLM p95 (ms)       | {s['llm_p95_ms']} |",
        ]
    lines += [
        "",
        "## By category",
        "",
        "| Category | n | Recall@1 | Recall@3 | Recall@6 |",
        "|---|---:|---:|---:|---:|",
    ]
    for cat, v in s["by_category"].items():
        lines.append(
            f"| {cat} | {v['n']} | {v['recall@1']*100:.1f}% | "
            f"{v['recall@3']*100:.1f}% | {v['recall@6']*100:.1f}% |"
        )
    if s["misses"]:
        lines += ["", "## Misses", ""]
        for m in s["misses"]:
            lines.append(f"- **{m['question']}** — expected `{m['expected']}`")
    lines += [
        "",
        "## Methodology",
        "",
        "- Hand-curated eval set in [`scripts/eval_dataset.py`](../scripts/eval_dataset.py).",
        "- Each question paraphrases or directly references one ground-truth document.",
        "- Retrieval uses HuggingFace `all-MiniLM-L6-v2` embeddings + FAISS, top-k = 6.",
        "- A retrieval is a **hit@k** if the expected document appears in the top-k results.",
        "- MRR averages 1/rank; missing the doc entirely contributes 0.",
        "",
    ]
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--with-llm",    action="store_true", help="Also call the LLM per question.")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "eval_results.md")
    ap.add_argument("--json", type=Path, default=None,    help="Optional JSON dump path.")
    args = ap.parse_args()

    print(f"Eval dataset: {total()} questions across {by_category()}")
    summary = evaluate(with_llm=args.with_llm)
    print_summary(summary)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(summary, args.out)
    print(f"Wrote {args.out}")

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2))
        print(f"Wrote {args.json}")

    # Exit code reflects retrieval quality so this can gate CI later.
    return 0 if summary["recall_at_6"] >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(main())
