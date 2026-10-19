"""Classification: internal movements -> keyword rules -> LLM (unique descriptions only) -> review queue.

Order of precedence for a row:
  1. internal movement (own transfers, investments, card bill, cash withdrawal): skipped
  2. keyword rule (seed rules, then rules learned in review; longest keyword first)
  3. a human decision from review that did not produce a rule
  4. an LLM label: confidence >= threshold -> applied ('llm'); below -> review queue ('review')
  5. nothing yet -> the description is sent to the LLM (once, however many rows share it)
"""
from __future__ import annotations

from collections import Counter

from . import config
from .ledger import Ledger
from .llm import LLM, BudgetExceeded, NoRecording
from .rules import RuleBook, internal_reason
from .text import normalize

SYSTEM_PROMPT = (
    "You classify lines of a Brazilian personal checking-account statement into spending categories.\n"
    "Each line has: index, direction ('in' = money received, 'out' = money spent), history (the bank's "
    "transaction type, in Portuguese: COMPRA NO DEBITO = debit-card purchase, PIX ENVIADO / PIX RECEBIDO = "
    "instant transfer sent / received, PAGAMENTO EFETUADO = bill paid, DEBITO AUTOMATICO = direct debit, "
    "TARIFA = bank fee, JUROS = interest charged) and description (merchant or counterpart, uppercase, "
    "accents removed; may carry a payment-processor prefix such as 'PAG*').\n\n"
    "Categories (use exactly one of these names):\n"
    + "\n".join(f"- {name}: {definition}" for name, definition in config.CATEGORIES.items())
    + "\n\nFor every line return:\n"
    "- index: the line's index, each index exactly once;\n"
    "- category: one name from the list;\n"
    "- confidence: 0 to 1, how likely your category is right. Use less than 0.8 when the description "
    "could fit two categories, when it is only a person's name, or when you are guessing from a generic word;\n"
    "- reason: at most 8 words;\n"
    "- suggested_keyword: the merchant core of the description, copied exactly from it (uppercase, no "
    "accents), at least 3 characters, without processor prefixes, dates or reference numbers. It will "
    "become a substring rule for future months, so it must identify this merchant and not others.\n"
)


def answer_schema() -> dict:
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["index", "category", "confidence", "reason", "suggested_keyword"],
        "properties": {
            "index": {"type": "integer"},
            "category": {"type": "string", "enum": config.CATEGORY_LIST},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
            "suggested_keyword": {"type": "string"},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": ["items"],
            "properties": {"items": {"type": "array", "items": item}}}


def batch_prompt(items: list[dict]) -> str:
    lines = [f"{i} | {it['direction']} | {it['history']} | {it['description']}" for i, it in enumerate(items)]
    return (f"Classify these {len(items)} statement lines (index | direction | history | description):\n"
            + "\n".join(lines))


def make_check(items: list[dict]):
    """Semantic checks the JSON Schema cannot express."""
    def check(answer: dict) -> list[str]:
        problems = []
        seen = Counter(a["index"] for a in answer["items"])
        missing = [i for i in range(len(items)) if seen[i] == 0]
        if missing:
            problems.append(f"missing indexes: {missing}")
        repeated = [i for i, n in seen.items() if n > 1]
        if repeated:
            problems.append(f"indexes answered more than once: {repeated}")
        extra = [i for i in seen if not 0 <= i < len(items)]
        if extra:
            problems.append(f"indexes that do not exist: {extra}")
        for a in answer["items"]:
            if not 0 <= a["index"] < len(items):
                continue
            if a["category"] not in config.CATEGORIES:
                problems.append(f"index {a['index']}: unknown category {a['category']!r}")
            if not 0 <= a["confidence"] <= 1:
                problems.append(f"index {a['index']}: confidence must be between 0 and 1")
            kw = normalize(a["suggested_keyword"])
            if len(kw) < config.MIN_KEYWORD_LEN or kw not in items[a["index"]]["description"]:
                problems.append(f"index {a['index']}: suggested_keyword {a['suggested_keyword']!r} must be a "
                                f"substring of {items[a['index']]['description']!r} with at least "
                                f"{config.MIN_KEYWORD_LEN} characters")
        return problems
    return check


def classify_descriptions(llm: LLM, items: list[dict], task: str = "classify",
                          batch_size: int = config.BATCH_SIZE) -> tuple[dict[str, dict], str | None]:
    """items: [{'description','history','direction'}] with normalized text, unique descriptions.
    Returns ({description: answer}, stop_reason). Stops cleanly at the call cap or a missing recording."""
    items = sorted(items, key=lambda it: it["description"])
    out: dict[str, dict] = {}
    schema = answer_schema()
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        try:
            answer = llm.ask(task, SYSTEM_PROMPT, batch_prompt(batch), schema, make_check(batch),
                             max_tokens=config.max_tokens_for(len(batch)))
        except (BudgetExceeded, NoRecording) as e:
            return out, str(e)
        for a in answer["items"]:
            it = batch[a["index"]]
            out[it["description"]] = {**a, "suggested_keyword": normalize(a["suggested_keyword"])}
    return out, None


def _apply(ledger: Ledger, book: RuleBook) -> list:
    """Classify every row from what is already known. Returns the rows that still need the LLM."""
    needs = []
    with ledger.db:
        for r in ledger.transactions():
            hist, desc, amount = r["history_norm"], r["description_norm"], r["amount_cents"] / 100
            reason = internal_reason(hist, desc)
            if reason:
                ledger.set_classification(r["id"], None, "internal", reason)
                continue
            m = book.match(desc, hist, amount)
            if m:
                rule, cat = m
                ledger.set_classification(r["id"], cat, "learned_rule" if rule.source == "review" else "rule",
                                          rule.keyword)
                continue
            lab = ledger.label_for(desc)
            if lab is None:
                ledger.set_classification(r["id"], None, "unclassified", "")
                needs.append(r)
            elif lab["status"] == "approved":
                ledger.set_classification(r["id"], lab["final_category"], "human", "approved in review")
            elif lab["status"] == "auto":
                ledger.set_classification(r["id"], lab["final_category"], "llm",
                                          f"confidence {lab['confidence']:.2f}")
            else:
                ledger.set_classification(r["id"], None, "review",
                                          f"LLM suggests {lab['llm_category']} ({lab['confidence']:.2f})")
    return needs


def classify_ledger(ledger: Ledger, book: RuleBook, llm: LLM | None,
                    threshold: float = config.CONFIDENCE_THRESHOLD) -> dict:
    needs = _apply(ledger, book)
    unique: dict[str, dict] = {}
    for r in needs:  # first occurrence (date order) gives the history/direction shown to the model
        unique.setdefault(r["description_norm"], {"description": r["description_norm"],
                                                  "history": r["history_norm"],
                                                  "direction": "in" if r["amount_cents"] > 0 else "out"})
    stop = None
    sent = 0
    if unique and llm is not None:
        answers, stop = classify_descriptions(llm, list(unique.values()))
        sent = len(answers)
        for desc, a in answers.items():
            it = unique[desc]
            status = "auto" if a["confidence"] >= threshold else "review"
            ledger.add_label(desc, it["history"], it["direction"], a, status)
        needs = _apply(ledger, book)
    elif unique:
        stop = "LLM disabled"
    methods = Counter(r["method"] for r in ledger.transactions())
    return {"rows": sum(methods.values()), "by_method": dict(sorted(methods.items())),
            "descriptions_needing_llm": len(unique), "descriptions_classified_now": sent,
            "still_unclassified_rows": len(needs), "stopped": stop}
