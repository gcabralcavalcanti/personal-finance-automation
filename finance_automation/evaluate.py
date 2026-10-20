"""Run the LLM classifier on the golden set (the descriptions the seed rules miss) and score it."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from . import config
from .classifier import classify_descriptions
from .llm import LLM


def load_golden(path: Path = config.GOLDEN / "labels.csv") -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run(llm: LLM, golden: list[dict] | None = None, threshold: float = config.CONFIDENCE_THRESHOLD) -> dict:
    golden = golden if golden is not None else load_golden()
    items = [{"description": g["description"], "history": g["history"], "direction": g["direction"]} for g in golden]
    answers, stop = classify_descriptions(llm, items, task="eval")
    rows = []
    for g in golden:
        a = answers.get(g["description"])
        if a is None:
            continue
        rows.append(
            {
                "description": g["description"],
                "expected": g["expected_category"],
                "predicted": a["category"],
                "confidence": a["confidence"],
                "auto": a["confidence"] >= threshold,
                "correct": a["category"] == g["expected_category"],
            }
        )
    n = len(rows)
    auto = [r for r in rows if r["auto"]]
    confusion = Counter((r["expected"], r["predicted"]) for r in rows if not r["correct"])
    return {
        "golden": len(golden),
        "answered": n,
        "stopped": stop,
        "accuracy": sum(r["correct"] for r in rows) / n if n else None,
        "auto_applied": len(auto),
        "auto_accuracy": sum(r["correct"] for r in auto) / len(auto) if auto else None,
        "sent_to_review": n - len(auto),
        "errors_caught_by_review": sum(1 for r in rows if not r["correct"] and not r["auto"]),
        "confusion": [{"expected": e, "predicted": p, "count": c} for (e, p), c in sorted(confusion.items())],
        "rows": rows,
    }


def to_text(res: dict) -> str:
    pct = lambda v: "-" if v is None else f"{v:.1%}"
    L = [
        f"Golden set: {res['golden']} descriptions, answered {res['answered']}"
        + (f" (stopped: {res['stopped']})" if res["stopped"] else ""),
        f"Accuracy (all answers): {pct(res['accuracy'])}",
        (
            f"Auto-applied (confidence >= {config.CONFIDENCE_THRESHOLD}): {res['auto_applied']}, "
            f"accuracy {pct(res['auto_accuracy'])}"
        ),
        f"Sent to review: {res['sent_to_review']} (of which wrong: {res['errors_caught_by_review']})",
        "Confusion (expected -> predicted, errors only):",
    ]
    L += [f"  {c['expected']} -> {c['predicted']}: {c['count']}" for c in res["confusion"]] or ["  none"]
    return "\n".join(L)


def to_markdown(res: dict) -> str:
    L = [
        "# Eval: LLM classifier on the golden set",
        "",
        (
            "The golden set holds every description in the synthetic statements that the seed rules do not catch, "
            "with the expected category (`tests/golden/labels.csv`)."
        ),
        "",
        "```",
        to_text(res),
        "```",
        "",
        "| Description | Expected | Predicted | Confidence | Result |",
        "|---|---|---|---:|---|",
    ]
    for r in res["rows"]:
        result = "ok" if r["correct"] else ("wrong, sent to review" if not r["auto"] else "wrong, auto-applied")
        L.append(f"| {r['description']} | {r['expected']} | {r['predicted']} | {r['confidence']:.2f} | {result} |")
    return "\n".join(L) + "\n"
