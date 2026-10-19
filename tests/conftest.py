"""Shared fixtures. Nothing here touches the network or the API."""
import json
import re
from types import SimpleNamespace

import pytest

from finance_automation.ledger import Ledger
from finance_automation.llm import LLM
from finance_automation.rules import Rule, save_rules

LINE = re.compile(r"^(\d+) \| (in|out) \| (.*?) \| (.*)$")


class FakeMessages:
    """Stands in for client.messages. Either replays fixed texts, or answers a classification batch
    from a table {description: (category, confidence, keyword)}."""

    def __init__(self, answers=None, table=None):
        self.answers = list(answers or [])
        self.table = table or {}
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self.answers:
            text = self.answers.pop(0)
        else:
            items = []
            for line in kw["messages"][0]["content"].splitlines():
                m = LINE.match(line)
                if m:
                    cat, conf, keyword = self.table.get(m.group(4), ("Other", 0.5, m.group(4)))
                    items.append({"index": int(m.group(1)), "category": cat, "confidence": conf,
                                  "reason": "fake", "suggested_keyword": keyword})
            text = json.dumps({"items": items})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=10))


def fake_llm(tmp_path, answers=None, table=None, max_calls=10) -> LLM:
    m = LLM(mode="demo", max_calls=max_calls, recordings=tmp_path / "rec", log_dir=tmp_path / "logs")
    m.mode = "live"
    m._client = SimpleNamespace(messages=FakeMessages(answers, table))
    return m


def statement_csv(rows, period="01/08/2026 a 31/08/2026", declared=None, opening=1000.0, newest_first=True):
    """rows: [(dd/mm/yyyy, history, description, amount)] in chronological order -> CSV text with balances."""
    bal, out = opening, []
    for d, h, desc, amount in rows:
        bal = round(bal + amount, 2)
        out.append((d, h, desc, amount, bal))
    fmt = lambda v: (f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."))  # noqa: E731
    header = ["Extrato Conta Corrente", f"Período ;{period}",
              f"Saldo ;{fmt(declared if declared is not None else out[-1][4])}", "",
              "Data Lançamento;Histórico;Descrição;Valor;Saldo"]
    body = [f"{d};{h};{desc};{fmt(a)};{fmt(b)}" for d, h, desc, a, b in (reversed(out) if newest_first else out)]
    return "\n".join(header + body) + "\n"


@pytest.fixture
def ledger():
    lg = Ledger(":memory:")
    yield lg
    lg.close()


@pytest.fixture
def rules_path(tmp_path):
    p = tmp_path / "rules.csv"
    save_rules([Rule("SUPERMERCADO", "Groceries"), Rule("RANGOJA", "Restaurants & Delivery"),
                Rule("ACME SERVICOS", "Income", "in")], p)
    return p
