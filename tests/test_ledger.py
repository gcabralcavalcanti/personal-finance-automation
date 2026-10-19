"""Dedup by natural key: importing the same file twice, or overlapping periods, never duplicates."""

from finance_automation.statement import parse_text

from .conftest import statement_csv

DAYS = [(f"{d:02d}/08/2026", "Compra no débito", f"LOJA {d}", -10.0 - d) for d in range(1, 16)]


def test_import_twice_is_idempotent(ledger):
    st = parse_text(statement_csv(DAYS), "a.csv")
    first = ledger.add_statement(st)
    snap = ledger.snapshot()
    second = ledger.add_statement(st)
    assert first["new_rows"] == 15 and first["duplicates"] == 0
    assert second["new_rows"] == 0 and second["duplicates"] == 15
    assert ledger.snapshot() == snap
    assert len(ledger.imports()) == 2 and first["reconciled"]


def test_overlapping_periods_only_add_new_rows(ledger):
    # same account: B starts where A's running balance stands on day 6
    a = parse_text(statement_csv(DAYS[:10]), "a.csv")
    opening_b = 1000 + sum(r[3] for r in DAYS[:5])
    b = parse_text(statement_csv(DAYS[5:], opening=opening_b), "b.csv")
    ledger.add_statement(a)
    res = ledger.add_statement(b)
    assert res["new_rows"] == 5 and res["duplicates"] == 5
    assert len(ledger.transactions()) == 15


def test_same_day_same_amount_kept_when_balance_differs(ledger):
    rows = [("05/08/2026", "Compra no débito", "PADARIA", -8.5)] * 2
    res = ledger.add_statement(parse_text(statement_csv(rows)))
    assert res["new_rows"] == 2
