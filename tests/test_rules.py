"""Rule matching: longest keyword first, origin filter, value/cents condition, internal movements."""
import pytest

from finance_automation.rules import Rule, RuleBook, internal_reason, load_rules, save_rules
from finance_automation.text import normalize

BOOK = RuleBook([
    Rule("RANGOJA", "Restaurants & Delivery"),
    Rule("RANGOJA*MERCADINHO", "Groceries"),
    Rule("PAGAFACIL", "Shopping", "out"),
    Rule("PAGAFACIL", "Income", "in"),
    Rule("ESTORNO", "Shopping", "Pix recebido"),
    Rule("AUTO POSTO", "Transport", cents="non-round", value_category="Groceries"),
    Rule("LIVRARIA", "Shopping", min=100, value_category="Education"),
    Rule("FARMACIA", "Health", max=20, value_category="Groceries"),
    Rule("LOJA", "Shopping"),
    Rule("LOJA ESPECIAL", "Travel", "in"),
])


def cat(desc, amount=-10.0, hist="COMPRA NO DEBITO"):
    m = BOOK.match(normalize(desc), normalize(hist), amount)
    return m[1] if m else None


def test_longest_keyword_wins_regardless_of_file_order():
    assert cat("RANGOJA*PIZZARIA") == "Restaurants & Delivery"
    assert cat("RANGOJA*MERCADINHO EXPRESSO") == "Groceries"


def test_origin_direction_and_history():
    assert cat("PAGAFACIL*LOJA X", -50) == "Shopping"
    assert cat("PAGAFACIL REPASSE", 50, "Pix recebido") == "Income"
    assert cat("ESTORNO COMPRA", 30, "Pix recebido") == "Shopping"
    assert cat("ESTORNO COMPRA", 30, "Crédito") is None


def test_blocked_origin_falls_back_to_shorter_keyword():
    assert cat("LOJA ESPECIAL", -20) == "Shopping"
    assert cat("LOJA ESPECIAL", 20, "Pix recebido") == "Travel"


def test_value_conditions():
    assert cat("AUTO POSTO ESTRELA", -150.00) == "Transport"
    assert cat("AUTO POSTO ESTRELA", -12.37) == "Groceries"
    assert cat("LIVRARIA PAGINA", -99.99) == "Shopping"
    assert cat("LIVRARIA PAGINA", -100.00) == "Education"
    assert cat("FARMACIA", -15) == "Groceries"
    assert cat("FARMACIA", -25) == "Health"


def test_round_condition():
    book = RuleBook([Rule("PIX FULANO", "Other", cents="round", value_category="Housing")])
    assert book.match("PIX FULANO", "PIX ENVIADO", -2000.0)[1] == "Housing"
    assert book.match("PIX FULANO", "PIX ENVIADO", -35.5)[1] == "Other"


def test_no_match():
    assert cat("SOMETHING ELSE") is None


@pytest.mark.parametrize("hist,desc,expected", [
    ("APLICACAO", "CDB LIQUIDEZ DIARIA", "investment application/redemption"),
    ("RESGATE", "CDB LIQUIDEZ DIARIA", "investment application/redemption"),
    ("PAGAMENTO FATURA", "PAGAMENTO FATURA CARTAO", "credit-card bill payment"),
    ("SAQUE", "SAQUE BANCO 24 HORAS", "cash withdrawal"),
    ("PIX ENVIADO", "ANA EXEMPLO", "transfer between own accounts"),
    ("PIX ENVIADO", "PEDRO H LIMA", None),
    ("COMPRA NO DEBITO", "SUPERMERCADO", None),
])
def test_internal_movements(hist, desc, expected):
    assert internal_reason(hist, desc, ["ANA EXEMPLO"]) == expected


def test_rules_csv_roundtrip_and_brazilian_amounts(tmp_path):
    p = tmp_path / "r.csv"
    save_rules([Rule("LIVRARIA", "Shopping", min=100, value_category="Education")], p)
    assert load_rules(p)[0].min == 100
    p.write_text("keyword,category,origin,min,max,value_category,cents,source\n"
                 "posto,Transport,,\"1.000,50\",,Groceries,redondo,\n", encoding="utf-8")
    r = load_rules(p)[0]
    assert (r.keyword, r.min, r.cents, r.source) == ("POSTO", 1000.5, "round", "seed")
