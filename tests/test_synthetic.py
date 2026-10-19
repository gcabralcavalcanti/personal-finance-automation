"""The synthetic data is deterministic, reconciles, and the seed rules cover roughly two thirds of the rows."""
from finance_automation.statement import parse_statement, reconcile
from finance_automation.synthetic import write_all


def test_generation_is_deterministic_and_reconciles(tmp_path):
    a = write_all(tmp_path / "a")
    b = write_all(tmp_path / "b")
    assert a == b
    for name in a["statements"]:
        fa = (tmp_path / "a" / "data" / "statements" / name).read_bytes()
        assert fa == (tmp_path / "b" / "data" / "statements" / name).read_bytes()
        st = parse_statement(tmp_path / "a" / "data" / "statements" / name)
        assert 60 <= len(st.transactions) <= 90 and reconcile(st).ok
    assert 0.6 <= a["rule_coverage"] <= 0.7
    assert a["golden_descriptions"] >= 20
