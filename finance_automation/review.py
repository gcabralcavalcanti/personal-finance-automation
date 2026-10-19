"""Human review of low-confidence LLM labels. An approval becomes a new keyword rule, so the same
merchant is caught by the rules next month with zero API calls."""
from __future__ import annotations

from pathlib import Path

from . import config
from .classifier import classify_ledger
from .ledger import Ledger
from .rules import Rule, RuleBook, append_rule, load_rules
from .text import normalize


def queue(ledger: Ledger) -> list[dict]:
    out = []
    for lab in ledger.labels("review"):
        rows = ledger.db.execute("SELECT COUNT(*) n, COALESCE(SUM(amount_cents),0) s FROM transactions "
                                 "WHERE description_norm=?", (lab["description_norm"],)).fetchone()
        out.append({"id": lab["id"], "description": lab["description_norm"], "history": lab["history_norm"],
                    "llm_category": lab["llm_category"], "confidence": lab["confidence"], "reason": lab["reason"],
                    "suggested_keyword": lab["suggested_keyword"], "rows": rows["n"], "total": rows["s"] / 100})
    return out


def keyword_problem(keyword: str, description_norm: str, rules: list[Rule]) -> str | None:
    """A learned keyword must be in the description, at least 3 characters long and not already a rule."""
    kw = normalize(keyword)
    if len(kw) < config.MIN_KEYWORD_LEN:
        return f"keyword {kw!r} is shorter than {config.MIN_KEYWORD_LEN} characters"
    if kw not in description_norm:
        return f"keyword {kw!r} is not part of the description"
    if kw in {r.keyword for r in rules}:
        return f"keyword {kw!r} is already a rule"
    return None


def approve(ledger: Ledger, label_id: int, category: str | None = None,
            rules_path: Path = config.RULES, reclassify: bool = True) -> dict:
    lab = ledger.label(label_id)
    if lab is None:
        raise ValueError(f"no review item with id {label_id}")
    if lab["status"] == "approved":
        raise ValueError(f"item {label_id} was already approved")
    final = category or lab["llm_category"]
    if final not in config.CATEGORIES:
        raise ValueError(f"unknown category {final!r}; use one of: {', '.join(config.CATEGORY_LIST)}")
    rules = load_rules(rules_path)
    problem = keyword_problem(lab["suggested_keyword"] or "", lab["description_norm"], rules)
    rule_added = None
    if problem is None:
        rule_added = normalize(lab["suggested_keyword"])
        append_rule(Rule(rule_added, final, source="review"), rules_path)
        note = f"new rule {rule_added!r} -> {final}"
    else:
        note = f"approved without a new rule ({problem})"
    ledger.approve_label(label_id, final, rule_added, note)
    result = {"id": label_id, "description": lab["description_norm"], "category": final,
              "rule_added": rule_added, "note": note}
    if reclassify:
        result["reclassified"] = classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm=None)
    return result


def approve_all_suggested(ledger: Ledger, rules_path: Path = config.RULES) -> list[dict]:
    """Accept the LLM's category and keyword for every item in the queue, then reclassify once.
    An "Other" guess means the model did not know, so it stays in the queue for a person."""
    results = [approve(ledger, item["id"], None, rules_path, reclassify=False)
               for item in queue(ledger) if item["llm_category"] != "Other"]
    if results:
        stats = classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm=None)
        results.append({"reclassified": stats})
    return results
