"""Keyword rules and internal-movement detection.

rules.csv columns: keyword, category, origin, min, max, value_category, cents, source
- keyword: matched as a substring of the normalized description; the LONGEST keyword wins.
- origin (optional): 'in' (money received), 'out' (money spent), or text that must appear in the
  normalized history (e.g. 'PIX'). A keyword may have one row per origin; if no row's origin fits,
  the search continues with the next (shorter) keyword.
- min / max / cents (optional): a value condition. When every filled condition holds, the row goes
  to value_category instead of category. cents: 'round' (x,00) or 'non-round'.
- source: 'seed' (written by hand) or 'review' (learned from an approved LLM suggestion).
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config
from .text import is_round, normalize, parse_amount

FIELDS = ["keyword", "category", "origin", "min", "max", "value_category", "cents", "source"]


@dataclass
class Rule:
    keyword: str
    category: str
    origin: str = ""
    min: float = 0.0
    max: float = 0.0
    value_category: str = ""
    cents: str = ""
    source: str = "seed"

    def origin_ok(self, history_norm: str, amount: float) -> bool:
        o = self.origin.strip().lower()
        if not o or o == "any":
            return True
        if o == "in":
            return amount > 0
        if o == "out":
            return amount < 0
        return normalize(self.origin) in history_norm

    def category_for(self, amount: float) -> str:
        """category, or value_category when the value condition is set and holds."""
        has_condition = self.min > 0 or self.max > 0 or self.cents
        if not (self.value_category and has_condition):
            return self.category
        v = abs(amount)
        if self.min > 0 and v < self.min - 1e-6:
            return self.category
        if self.max > 0 and v > self.max + 1e-6:
            return self.category
        if self.cents == "round" and not is_round(v):
            return self.category
        if self.cents == "non-round" and is_round(v):
            return self.category
        return self.value_category


def _norm_cents(s: str) -> str:
    n = normalize(s).replace("_", "-")
    if not n:
        return ""
    if "NON" in n or "QUEBR" in n or "!=" in n or "<>" in n:
        return "non-round"
    if "ROUND" in n or "REDOND" in n or n in (",00", ".00", "00"):
        return "round"
    return ""


def load_rules(path: Path = config.RULES) -> list[Rule]:
    if not Path(path).exists():
        return []
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            kw, cat = normalize(r.get("keyword")), (r.get("category") or "").strip()
            if not kw or not cat:
                continue
            out.append(
                Rule(
                    kw,
                    cat,
                    (r.get("origin") or "").strip(),
                    parse_amount(r.get("min")),
                    parse_amount(r.get("max")),
                    (r.get("value_category") or "").strip(),
                    _norm_cents(r.get("cents") or ""),
                    (r.get("source") or "seed").strip() or "seed",
                )
            )
    return out


def _row(rule: Rule) -> dict:
    d = asdict(rule)
    d["min"] = f"{rule.min:.2f}" if rule.min else ""
    d["max"] = f"{rule.max:.2f}" if rule.max else ""
    return d


def save_rules(rules: list[Rule], path: Path = config.RULES) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rules:
            w.writerow(_row(r))


def append_rule(rule: Rule, path: Path = config.RULES) -> None:
    exists = Path(path).exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if not exists:
            w.writeheader()
        w.writerow(_row(rule))


class RuleBook:
    def __init__(self, rules: list[Rule]):
        self.rules = rules
        # stable sort: longest keyword first, file order among equal lengths
        self._ordered = sorted(rules, key=lambda r: len(r.keyword), reverse=True)
        self.keywords = {r.keyword for r in rules}

    def match(self, description_norm: str, history_norm: str, amount: float) -> tuple[Rule, str] | None:
        for rule in self._ordered:
            if rule.keyword in description_norm and rule.origin_ok(history_norm, amount):
                return rule, rule.category_for(amount)
        return None


def internal_reason(history_norm: str, description_norm: str, own_names: list[str] | None = None) -> str | None:
    """Movements between the holder's own pockets: not income, not expense."""
    own = config.OWN_NAMES if own_names is None else own_names
    if any(h in history_norm for h in config.INVESTMENT_HISTORY):
        return "investment application/redemption"
    if any(p in history_norm or p in description_norm for p in config.CARD_BILL):
        return "credit-card bill payment"
    if any(p in history_norm for p in config.CASH_WITHDRAWAL):
        return "cash withdrawal"
    if any(p in history_norm for p in config.TRANSFER_HISTORY) and any(n and n in description_norm for n in own):
        return "transfer between own accounts"
    return None
