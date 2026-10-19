"""Local SQLite ledger. Import is append-with-dedup on the natural key, so it is idempotent:
importing the same file twice, or two statements with overlapping periods, never duplicates a row."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .statement import Reconciliation, Statement, reconcile
from .text import cents

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY,
    nkey TEXT UNIQUE NOT NULL,            -- natural key: date|history|description|amount|balance
    date TEXT NOT NULL, history TEXT, description TEXT,
    amount_cents INTEGER NOT NULL, balance_cents INTEGER,
    history_norm TEXT, description_norm TEXT,
    source_file TEXT,
    category TEXT,                         -- NULL while internal, in review or unclassified
    method TEXT,                           -- internal | rule | learned_rule | llm | human | review | unclassified
    detail TEXT                            -- rule keyword, LLM confidence or internal reason
);
CREATE TABLE IF NOT EXISTS labels(         -- one row per unique description sent to the LLM
    id INTEGER PRIMARY KEY,
    description_norm TEXT UNIQUE NOT NULL,
    history_norm TEXT, direction TEXT,
    llm_category TEXT, confidence REAL, reason TEXT, suggested_keyword TEXT,
    status TEXT NOT NULL,                  -- auto (>= threshold) | review | approved
    final_category TEXT, rule_added TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS imports(
    id INTEGER PRIMARY KEY,
    file TEXT, imported_at TEXT, period_start TEXT, period_end TEXT, encoding TEXT,
    rows_in_file INTEGER, new_rows INTEGER, duplicates INTEGER,
    reconciled INTEGER, recon_detail TEXT
);
"""


class Ledger:
    def __init__(self, path: Path | str = config.LEDGER):
        self.path = Path(path) if str(path) != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------ import
    def add_statement(self, st: Statement) -> dict:
        rec: Reconciliation = reconcile(st)
        new = dup = 0
        with self.db:
            for t in st.transactions:
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO transactions(nkey,date,history,description,amount_cents,balance_cents,"
                    "history_norm,description_norm,source_file) VALUES(?,?,?,?,?,?,?,?,?)",
                    (t.natural_key(), t.date.isoformat(), t.history, t.description, cents(t.amount),
                     None if t.balance is None else cents(t.balance), t.history_norm, t.description_norm,
                     st.name))
                if cur.rowcount == 1:
                    new += 1
                else:
                    dup += 1
            self.db.execute(
                "INSERT INTO imports(file,imported_at,period_start,period_end,encoding,rows_in_file,new_rows,"
                "duplicates,reconciled,recon_detail) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (st.name, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 st.period[0].isoformat() if st.period else None, st.period[1].isoformat() if st.period else None,
                 st.encoding, len(st.transactions), new, dup, int(rec.ok), rec.detail))
        return {"file": st.name, "rows_in_file": len(st.transactions), "new_rows": new, "duplicates": dup,
                "reconciled": rec.ok, "reconciliation": rec.detail, "encoding": st.encoding}

    # ------------------------------------------------------------------ queries
    def transactions(self, month: str | None = None) -> list[sqlite3.Row]:
        if month:
            return self.db.execute("SELECT * FROM transactions WHERE substr(date,1,7)=? ORDER BY date, id",
                                   (month,)).fetchall()
        return self.db.execute("SELECT * FROM transactions ORDER BY date, id").fetchall()

    def set_classification(self, tx_id: int, category: str | None, method: str, detail: str = ""):
        self.db.execute("UPDATE transactions SET category=?, method=?, detail=? WHERE id=?",
                        (category, method, detail, tx_id))

    def labels(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.db.execute("SELECT * FROM labels WHERE status=? ORDER BY id", (status,)).fetchall()
        return self.db.execute("SELECT * FROM labels ORDER BY id").fetchall()

    def label_for(self, description_norm: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM labels WHERE description_norm=?", (description_norm,)).fetchone()

    def label(self, label_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM labels WHERE id=?", (label_id,)).fetchone()

    def add_label(self, description_norm, history_norm, direction, answer: dict, status: str):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO labels(description_norm,history_norm,direction,llm_category,confidence,"
                "reason,suggested_keyword,status,final_category) VALUES(?,?,?,?,?,?,?,?,?)",
                (description_norm, history_norm, direction, answer["category"], float(answer["confidence"]),
                 answer["reason"], answer["suggested_keyword"], status,
                 answer["category"] if status == "auto" else None))

    def approve_label(self, label_id: int, category: str, rule_added: str | None, note: str):
        with self.db:
            self.db.execute("UPDATE labels SET status='approved', final_category=?, rule_added=?, note=? WHERE id=?",
                            (category, rule_added, note, label_id))

    def imports(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM imports ORDER BY id").fetchall()

    def snapshot(self) -> list[tuple]:
        """Comparable content of the ledger (used by the idempotency tests)."""
        return [tuple(r) for r in self.db.execute(
            "SELECT nkey, category, method FROM transactions ORDER BY nkey").fetchall()]

