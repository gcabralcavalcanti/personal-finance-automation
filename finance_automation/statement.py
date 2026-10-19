"""Read a Brazilian bank-statement CSV and check its running balance.

Format (semicolon separated, Brazilian numbers), with free header lines before the table:

    Extrato Conta Corrente
    Período ;01/08/2026 a 31/08/2026
    Saldo ;4.512,33
    <blank>
    Data Lançamento;Histórico;Descrição;Valor;Saldo
    31/08/2026;Pix enviado;PADARIA ...;-12,50;4.512,33
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .text import cents, normalize, parse_brl

ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")
HEADER = re.compile(r"^\s*data\s+lan", re.IGNORECASE)


@dataclass
class Transaction:
    date: date
    history: str
    description: str
    amount: float
    balance: float | None

    @property
    def history_norm(self) -> str:
        return normalize(self.history)

    @property
    def description_norm(self) -> str:
        return normalize(self.description)

    @property
    def direction(self) -> str:
        return "in" if self.amount > 0 else "out"

    def natural_key(self) -> str:
        """(date, history, description, amount, balance). The balance separates two equal purchases on the same day."""
        bal = "" if self.balance is None else str(cents(self.balance))
        return "|".join([self.date.isoformat(), self.history_norm, self.description_norm,
                         str(cents(self.amount)), bal])


@dataclass
class Reconciliation:
    ok: bool
    order: str                 # 'newest-first', 'oldest-first' or 'n/a'
    breaks: list[int] = field(default_factory=list)   # row numbers (1-based, table order) where the chain breaks
    declared_ok: bool | None = None                   # header balance equals the closing balance
    detail: str = ""


@dataclass
class Statement:
    name: str
    transactions: list[Transaction]
    period: tuple[date, date] | None
    declared_balance: float | None
    encoding: str


def read_text(path: Path) -> tuple[str, str]:
    data = Path(path).read_bytes()
    for enc in ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{Path(path).name}: could not decode the file")  # latin-1 never fails; kept for safety


def _parse_date(s: str) -> date | None:
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_period(s: str) -> tuple[date, date] | None:
    found = re.findall(r"\d{2}/\d{2}/\d{4}", s)
    if len(found) == 2:
        a, b = _parse_date(found[0]), _parse_date(found[1])
        if a and b:
            return a, b
    return None


def parse_text(text: str, name: str = "statement.csv", encoding: str = "utf-8") -> Statement:
    lines = text.splitlines()
    start = None
    period = declared = None
    for i, line in enumerate(lines):
        if HEADER.match(line):
            start = i + 1
            break
        low = normalize(line)
        value = line.split(";", 1)[1].strip() if ";" in line else ""
        if low.startswith("PERIODO") and value:
            period = _parse_period(value)
        elif low.startswith("SALDO") and value:
            declared = parse_brl(value)
    if start is None:
        raise ValueError(f"{name}: table header 'Data Lançamento;...' not found")

    rows = []
    for line in lines[start:]:
        if not line.strip():
            continue
        p = line.split(";")
        if len(p) < 4:
            continue
        d = _parse_date(p[0])
        amount = parse_brl(p[3])
        if d is None or amount is None:
            continue
        balance = parse_brl(p[4]) if len(p) >= 5 and p[4].strip() else None
        rows.append(Transaction(d, p[1].strip(), p[2].strip(), round(amount, 2),
                                round(balance, 2) if balance is not None else None))
    return Statement(name, rows, period, declared, encoding)


def parse_statement(path) -> Statement:
    text, enc = read_text(path)
    return parse_text(text, Path(path).name, enc)


def _breaks(txs: list[Transaction], newest_first: bool) -> list[int]:
    out = []
    for i in range(len(txs) - 1):
        a, b = txs[i], txs[i + 1]
        if newest_first:   # a is later than b: bal(a) = bal(b) + amount(a)
            ok = cents(a.balance) == cents(b.balance) + cents(a.amount)
        else:              # b is later than a: bal(b) = bal(a) + amount(b)
            ok = cents(b.balance) == cents(a.balance) + cents(b.amount)
        if not ok:
            out.append(i + 2)
    return out


def reconcile(st: Statement) -> Reconciliation:
    """Every row's balance must equal the previous balance plus the row's amount (either table order)."""
    txs = [t for t in st.transactions if t.balance is not None]
    if len(txs) < 2:
        return Reconciliation(ok=True, order="n/a", detail="fewer than 2 rows with balance: nothing to check")
    newest, oldest = _breaks(txs, True), _breaks(txs, False)
    order, breaks = ("newest-first", newest) if len(newest) <= len(oldest) else ("oldest-first", oldest)
    closing = txs[0].balance if order == "newest-first" else txs[-1].balance
    declared_ok = None
    if st.declared_balance is not None:
        declared_ok = cents(st.declared_balance) == cents(closing)
    parts = []
    if breaks:
        parts.append(f"running balance breaks at row(s) {', '.join(map(str, breaks[:5]))}")
    else:
        parts.append(f"running balance consistent over {len(txs)} rows")
    if declared_ok is False:
        parts.append(f"header balance {st.declared_balance:.2f} differs from closing balance {closing:.2f}")
    elif declared_ok:
        parts.append("header balance matches the closing balance")
    return Reconciliation(ok=not breaks and declared_ok is not False, order=order, breaks=breaks,
                          declared_ok=declared_ok, detail="; ".join(parts))
