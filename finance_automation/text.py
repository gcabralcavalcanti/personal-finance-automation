"""Text and number helpers shared by every step."""
from __future__ import annotations

import re
import unicodedata


def normalize(s) -> str:
    """Uppercase, accents stripped, 'R$' removed, whitespace collapsed: the form every match runs on."""
    s = str(s or "").upper().replace("R$", "")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def parse_brl(s) -> float | None:
    """'1.234,56' -> 1234.56 ; '-12,00' -> -12.0 ; '' -> 0.0 ; garbage -> None."""
    s = str(s or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return 0.0
    neg = s.startswith("-")
    s = s.lstrip("-+").replace(".", "").replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_amount(s) -> float:
    """Amount cell of rules.csv: accepts '100', '100.50' or '100,50'. Empty or text -> 0 (no condition)."""
    s = str(s or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return 0.0
    if "," in s:
        v = parse_brl(s)
    else:
        try:
            v = float(s)
        except ValueError:
            v = None
    return abs(v) if v is not None else 0.0


def format_brl(v: float) -> str:
    """1234.5 -> '1.234,50' (the statement format)."""
    s = f"{abs(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("-" if v < 0 else "") + s


def money(v: float) -> str:
    """Report format: 'R$ 1,234.50' / '-R$ 12.00'."""
    return ("-" if v < 0 else "") + f"R$ {abs(v):,.2f}"


def cents(v: float) -> int:
    return int(round(v * 100))


def is_round(v: float) -> bool:
    """Exactly zero cents, e.g. 230,00."""
    return cents(abs(v)) % 100 == 0
