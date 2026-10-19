"""Classification loop: rules -> LLM (unique descriptions) -> review -> new rule -> reclassify; and report totals."""

import pytest

from finance_automation import review
from finance_automation.classifier import classify_ledger
from finance_automation.ledger import Ledger
from finance_automation.llm import LLM
from finance_automation.report import build, to_markdown
from finance_automation.rules import Rule, RuleBook, load_rules
from finance_automation.statement import parse_text

from .conftest import fake_llm, statement_csv

AUG = [
    ("01/08/2026", "Pix recebido", "ACME SERVICOS DIGITAIS LTDA", 9600.0),
    ("02/08/2026", "Compra no débito", "SUPERMERCADO BOM PRECO", -200.0),
    ("03/08/2026", "Compra no débito", "CAFETERIA GRAO NOBRE", -12.5),
    ("04/08/2026", "Compra no débito", "CAFETERIA GRAO NOBRE", -9.9),
    ("05/08/2026", "Compra no débito", "PET SHOP AMIGO FIEL", -80.0),
    ("06/08/2026", "Pix enviado", "ANA EXEMPLO", -500.0),
    ("07/08/2026", "Aplicação", "CDB LIQUIDEZ DIARIA", -1000.0),
    ("08/08/2026", "Pix enviado", "PEDRO H LIMA", -60.0),
]
SEP = [
    ("02/09/2026", "Compra no débito", "PET SHOP AMIGO FIEL", -95.0),
    ("03/09/2026", "Compra no débito", "PEDRO H LIMA LANCHES", -20.0),
]
TABLE = {
    "CAFETERIA GRAO NOBRE": ("Restaurants & Delivery", 0.95, "CAFETERIA GRAO NOBRE"),
    "PET SHOP AMIGO FIEL": ("Shopping", 0.6, "PET SHOP AMIGO FIEL"),
    "PEDRO H LIMA": ("Other", 0.4, "PEDRO H LIMA"),
    "PEDRO H LIMA LANCHES": ("Restaurants & Delivery", 0.9, "LIMA LANCHES"),
}


def setup(ledger, rules_path, tmp_path):
    ledger.add_statement(parse_text(statement_csv(AUG), "aug.csv"))
    llm = fake_llm(tmp_path, table=TABLE)
    stats = classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm)
    return llm, stats


def methods(ledger):
    return {r["description"]: (r["method"], r["category"]) for r in ledger.transactions()}


def test_rules_first_then_llm_on_unique_descriptions(ledger, rules_path, tmp_path):
    llm, stats = setup(ledger, rules_path, tmp_path)
    assert llm.calls == 1 and stats["descriptions_needing_llm"] == 3  # cafeteria counted once
    m = methods(ledger)
    assert m["SUPERMERCADO BOM PRECO"] == ("rule", "Groceries")
    assert m["ANA EXEMPLO"][0] == "internal" and m["CDB LIQUIDEZ DIARIA"][0] == "internal"
    assert m["CAFETERIA GRAO NOBRE"] == ("llm", "Restaurants & Delivery")  # 0.95 >= 0.8
    assert m["PET SHOP AMIGO FIEL"] == ("review", None)  # 0.6 < 0.8
    classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm)  # a second pass asks nothing new
    assert llm.calls == 1


def test_demo_mode_replays_the_same_classification(ledger, rules_path, tmp_path):
    setup(ledger, rules_path, tmp_path)
    expected = ledger.snapshot()
    fresh = Ledger(":memory:")
    fresh.add_statement(parse_text(statement_csv(AUG), "aug.csv"))
    demo = LLM(mode="demo", recordings=tmp_path / "rec", log_dir=tmp_path / "logs")
    classify_ledger(fresh, RuleBook(load_rules(rules_path)), demo)
    assert demo.calls == 0 and demo.cache_hits == 1 and fresh.snapshot() == expected


def test_no_recording_leaves_rows_unclassified(ledger, rules_path, tmp_path):
    ledger.add_statement(parse_text(statement_csv(AUG), "aug.csv"))
    demo = LLM(mode="demo", recordings=tmp_path / "empty", log_dir=tmp_path / "logs")
    stats = classify_ledger(ledger, RuleBook(load_rules(rules_path)), demo)
    assert "No recorded answer" in stats["stopped"] and stats["by_method"]["unclassified"] == 4


def test_review_approval_creates_rule_and_next_month_costs_nothing(ledger, rules_path, tmp_path):
    llm, _ = setup(ledger, rules_path, tmp_path)
    q = {it["description"]: it for it in review.queue(ledger)}
    assert set(q) == {"PET SHOP AMIGO FIEL", "PEDRO H LIMA"}
    res = review.approve(ledger, q["PET SHOP AMIGO FIEL"]["id"], rules_path=rules_path)
    assert res["rule_added"] == "PET SHOP AMIGO FIEL"
    new_rule = load_rules(rules_path)[-1]
    assert (new_rule.keyword, new_rule.category, new_rule.source) == ("PET SHOP AMIGO FIEL", "Shopping", "review")
    assert methods(ledger)["PET SHOP AMIGO FIEL"] == ("learned_rule", "Shopping")
    # human override of the category
    review.approve(ledger, q["PEDRO H LIMA"]["id"], category="Restaurants & Delivery", rules_path=rules_path)
    assert methods(ledger)["PEDRO H LIMA"] == ("learned_rule", "Restaurants & Delivery")
    assert review.queue(ledger) == []
    # next month: the learned rules catch both descriptions with zero API calls
    calls_before = llm.calls
    ledger.add_statement(parse_text(statement_csv(SEP, period="01/09/2026 a 30/09/2026"), "sep.csv"))
    classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm)
    sep = {r["description"]: r["method"] for r in ledger.transactions("2026-09")}
    assert sep["PET SHOP AMIGO FIEL"] == "learned_rule"
    assert sep["PEDRO H LIMA LANCHES"] == "learned_rule"  # contains the learned keyword 'PEDRO H LIMA'
    assert llm.calls == calls_before


def test_invalid_keyword_is_approved_without_rule(ledger, rules_path, tmp_path):
    setup(ledger, rules_path, tmp_path)
    lab = ledger.label_for("PET SHOP AMIGO FIEL")
    ledger.db.execute("UPDATE labels SET suggested_keyword='SUPERMERCADO' WHERE id=?", (lab["id"],))
    res = review.approve(ledger, lab["id"], rules_path=rules_path)
    assert res["rule_added"] is None and "not part of the description" in res["note"]
    assert methods(ledger)["PET SHOP AMIGO FIEL"] == ("human", "Shopping")


def test_keyword_validation():
    existing = [Rule("SUPERMERCADO", "Groceries")]
    assert review.keyword_problem("AB", "ABC", []) is not None
    assert review.keyword_problem("XYZ", "ABC DEF", []) is not None
    assert review.keyword_problem("SUPERMERCADO", "SUPERMERCADO X", existing) is not None
    assert review.keyword_problem("abc", "ABC DEF", []) is None


def test_approve_all_and_errors(ledger, rules_path, tmp_path):
    setup(ledger, rules_path, tmp_path)
    with pytest.raises(ValueError):
        review.approve(ledger, 999, rules_path=rules_path)
    with pytest.raises(ValueError):
        review.approve(ledger, ledger.label_for("PEDRO H LIMA")["id"], category="Pets", rules_path=rules_path)
    out = review.approve_all_suggested(ledger, rules_path)
    assert len([r for r in out if "id" in r]) == 1  # the "Other" guess is skipped
    assert [q["description"] for q in review.queue(ledger)] == ["PEDRO H LIMA"]


def test_report_totals_add_up(ledger, rules_path, tmp_path):
    setup(ledger, rules_path, tmp_path)
    d = build(ledger, "2026-08")
    assert d["income"] == pytest.approx(9600.0)
    assert d["expenses"] == pytest.approx(-(200 + 12.5 + 9.9 + 80 + 60))  # internal excluded
    assert sum(c["total"] for c in d["categories"]) == pytest.approx(d["income"] + d["expenses"])
    assert sum(c["rows"] for c in d["categories"]) == d["rows"] - 2
    assert sum(m["rows"] for m in d["methods"]) == d["rows"]
    assert {c["category"] for c in d["categories"]} >= {"Income", "Groceries", "(in review)"}
    assert d["reconciled"] is True and len(d["in_review"]) == 2
    assert d["top_expenses"][0]["amount"] == -200.0
    assert "## Totals by category" in to_markdown(d)
    with pytest.raises(ValueError):
        build(ledger, "2030-01")
