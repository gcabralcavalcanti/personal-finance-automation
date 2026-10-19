"""CSV parsing (Brazilian numbers, encodings, header detection) and the running-balance check."""

from datetime import date

import pytest

from finance_automation.statement import parse_statement, parse_text, reconcile
from finance_automation.text import format_brl, normalize, parse_brl

from .conftest import statement_csv

ROWS = [
    ("01/08/2026", "Pix recebido", "ACME SERVICOS DIGITAIS LTDA", 9600.0),
    ("02/08/2026", "Compra no débito", "SUPERMERCADO BOM PREÇO", -1234.56),
    ("02/08/2026", "Compra no débito", "PADARIA", -12.0),
]


def test_brazilian_numbers():
    assert parse_brl("1.234,56") == 1234.56
    assert parse_brl("-12,00") == -12.0
    assert parse_brl("R$ 3,10") == 3.10
    assert parse_brl("") == 0.0
    assert parse_brl("abc") is None
    assert format_brl(-1234.5) == "-1.234,50"


def test_normalize_strips_accents_and_case():
    assert normalize("  Compra  no débito R$ ") == "COMPRA NO DEBITO"


def test_header_lines_are_skipped_and_metadata_read():
    st = parse_text("Some bank\nConta ;123\n" + statement_csv(ROWS), "x.csv")
    assert len(st.transactions) == 3
    assert st.period == (date(2026, 8, 1), date(2026, 8, 31))
    assert st.declared_balance == pytest.approx(1000 + 9600 - 1234.56 - 12)
    newest = st.transactions[0]
    assert newest.amount == -12.0 and newest.date == date(2026, 8, 2)


def test_missing_table_header_raises():
    with pytest.raises(ValueError):
        parse_text("Extrato\nnothing here\n", "bad.csv")


@pytest.mark.parametrize("encoding", ["utf-8-sig", "latin-1"])
def test_encodings(tmp_path, encoding):
    p = tmp_path / "s.csv"
    p.write_bytes(statement_csv(ROWS).encode(encoding))
    st = parse_statement(p)
    assert st.encoding == encoding
    assert st.transactions[1].description == "SUPERMERCADO BOM PREÇO"
    assert st.transactions[1].history == "Compra no débito"


def test_reconciliation_ok_both_orders():
    for newest_first in (True, False):
        rec = reconcile(parse_text(statement_csv(ROWS, newest_first=newest_first)))
        assert rec.ok and rec.declared_ok
        assert rec.order == ("newest-first" if newest_first else "oldest-first")


def test_reconciliation_detects_a_broken_balance():
    text = statement_csv(ROWS).replace("9.600,00;10.600,00", "9.600,00;10.700,00")
    rec = reconcile(parse_text(text))
    assert not rec.ok and rec.breaks


def test_reconciliation_detects_header_mismatch():
    rec = reconcile(parse_text(statement_csv(ROWS, declared=1.0)))
    assert not rec.ok and rec.declared_ok is False and not rec.breaks
