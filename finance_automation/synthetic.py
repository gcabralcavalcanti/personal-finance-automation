"""Deterministic synthetic data: three monthly bank statements, the seed rules and the golden labels.

Every merchant, person and amount here is invented. The statements follow the common Brazilian
checking-account CSV layout (semicolons, '1.234,56' numbers, header lines before the table).
"""

from __future__ import annotations

import csv
import random
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config
from .rules import Rule, RuleBook, internal_reason, save_rules
from .text import format_brl, normalize

SEED = 2026
MONTHS = [(2026, 7), (2026, 8), (2026, 9)]
ENCODING_BY_MONTH = {(2026, 7): "utf-8-sig", (2026, 8): "latin-1", (2026, 9): "utf-8-sig"}
OPENING_BALANCE = 6870.35
OWN_NAME = "ANA EXEMPLO"  # the synthetic account holder (matches config.OWN_NAMES)

GROC, REST, TRAN, HOUS, UTIL, SUBS = (
    "Groceries",
    "Restaurants & Delivery",
    "Transport",
    "Housing",
    "Utilities",
    "Subscriptions",
)
HLTH, EDUC, SHOP, TRAV, INC, FEES, OTH = "Health", "Education", "Shopping", "Travel", "Income", "Fees & Taxes", "Other"

DEB, PIX_OUT, PIX_IN, BILL, AUTO = (
    "Compra no débito",
    "Pix enviado",
    "Pix recebido",
    "Pagamento efetuado",
    "Débito automático",
)

# Seed rules: keyword, category, origin, min, max, value_category, cents
SEED_RULES = [
    Rule("ACME SERVICOS", INC, "in"),
    Rule("IMOBILIARIA HORIZONTE", HOUS),
    Rule("CONDOMINIO RESIDENCIAL", HOUS),
    Rule("LUZ E FORCA", UTIL),
    Rule("AGUAS DO VALE", UTIL),
    Rule("NETVELOZ", UTIL),
    Rule("ALO MOVEL", UTIL),
    Rule("STREAMFLIX", SUBS),
    Rule("SONORA MUSIC", SUBS),
    Rule("NUVEMDRIVE", SUBS),
    Rule("FALA FACIL", EDUC),
    Rule("ACADEMIA CORPO ATIVO", HLTH),
    Rule("TARIFA PACOTE", FEES),
    Rule("SUPERMERCADO", GROC),
    Rule("HORTIFRUTI", GROC),
    Rule("PADARIA", GROC),
    Rule("ATACADAO", GROC),
    Rule("RANGOJA", REST),
    Rule("RANGOJA*MERCADINHO", GROC),  # longer keyword wins over RANGOJA
    Rule("RESTAURANTE", REST),
    Rule("VAIJA", TRAN),
    Rule("AUTO POSTO", TRAN, cents="non-round", value_category=GROC),  # fuel is paid in round values
    Rule("METRO RECARGA", TRAN),
    Rule("DROGARIA", HLTH),
    Rule("LIVRARIA", SHOP, min=100.0, value_category=EDUC),  # big purchases there are course books
    Rule("PAGAFACIL", SHOP, "out"),  # same keyword, split by direction
    Rule("PAGAFACIL", INC, "in"),
]


@dataclass
class Event:
    day: int
    history: str
    description: str
    amount: float
    category: str | None  # expected category (None for internal movements)


def _amt(rng, lo, hi, round_cents=False):
    v = round(rng.uniform(lo, hi), 2)
    if round_cents:
        return float(round(v))
    if round(v * 100) % 100 == 0:
        v += 0.37
    return round(v, 2)


def _days(rng, n, last):
    return [rng.randint(1, last) for _ in range(n)]


def month_events(rng: random.Random, year: int, month: int, idx: int) -> list[Event]:
    last = monthrange(year, month)[1]
    ev: list[Event] = []
    add = lambda d, h, desc, a, c: ev.append(Event(min(d, last), h, desc, a, c))

    # fixed monthly items (rules)
    add(5, PIX_IN, "ACME SERVICOS DIGITAIS LTDA", 9600.00, INC)
    add(8, BILL, "IMOBILIARIA HORIZONTE ALUGUEL", -2150.00, HOUS)
    add(10, BILL, "CONDOMINIO RESIDENCIAL JACARANDAS", -634.90, HOUS)
    add(15, AUTO, "COMPANHIA LUZ E FORCA", -_amt(rng, 140, 230), UTIL)
    add(18, AUTO, "AGUAS DO VALE SANEAMENTO", -_amt(rng, 70, 110), UTIL)
    add(12, AUTO, "NETVELOZ INTERNET FIBRA", -119.90, UTIL)
    add(20, AUTO, "ALO MOVEL TELEFONIA", -59.99, UTIL)
    add(3, DEB, "STREAMFLIX ASSINATURA", -39.90, SUBS)
    add(9, DEB, "SONORA MUSIC PREMIUM", -21.90, SUBS)
    add(22, DEB, "NUVEMDRIVE ARMAZENAMENTO", -9.90, SUBS)
    add(10, BILL, "ESCOLA DE IDIOMAS FALA FACIL", -389.00, EDUC)
    add(6, DEB, "ACADEMIA CORPO ATIVO", -119.90, HLTH)
    add(28, "Tarifa", "TARIFA PACOTE DE SERVICOS", -32.90, FEES)

    # variable items (rules)
    for d in _days(rng, rng.randint(5, 7), last):
        add(d, DEB, "SUPERMERCADO BOM PRECO", -_amt(rng, 45, 280), GROC)
    for d in _days(rng, rng.randint(2, 3), last):
        add(d, DEB, "HORTIFRUTI FOLHA VERDE", -_amt(rng, 18, 75), GROC)
    for d in _days(rng, rng.randint(4, 6), last):
        add(d, DEB, "PADARIA TRIGO DOURADO", -_amt(rng, 8, 38), GROC)
    if rng.random() < 0.5:
        add(rng.randint(1, last), DEB, "ATACADAO DO POVO", -_amt(rng, 180, 420), GROC)
    shops = ["PIZZARIA NAPOLI", "SUSHI KAZU", "BURGUER DO BAIRRO", "MARMITA DA VO", "ACAI TROPICAL"]
    for d in _days(rng, rng.randint(4, 6), last):
        add(d, DEB, f"RANGOJA*{rng.choice(shops)}", -_amt(rng, 32, 95), REST)
    add(rng.randint(1, last), DEB, "RANGOJA*MERCADINHO EXPRESSO", -_amt(rng, 40, 120), GROC)
    for d in _days(rng, rng.randint(2, 3), last):
        add(d, DEB, "RESTAURANTE SABOR CASEIRO", -_amt(rng, 28, 70), REST)
    for d in _days(rng, rng.randint(5, 8), last):
        code = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
        add(d, DEB, f"VAIJA *VIAGEM {code}", -_amt(rng, 9, 48), TRAN)
    for d in _days(rng, 2, last):
        add(d, DEB, "AUTO POSTO ESTRELA", -float(rng.choice([100, 120, 150, 200])), TRAN)
    add(rng.randint(1, last), DEB, "AUTO POSTO ESTRELA", -_amt(rng, 6, 25), GROC)
    add(rng.randint(1, last), DEB, "METRO RECARGA CARTAO TRANSPORTE", -float(rng.choice([50, 100])), TRAN)
    for d in _days(rng, rng.randint(1, 2), last):
        add(d, DEB, "DROGARIA SAO BENTO", -_amt(rng, 12, 140), HLTH)
    add(rng.randint(1, last), DEB, "LIVRARIA PAGINA CERTA", -_amt(rng, 35, 80), SHOP)
    if idx != 1:
        add(rng.randint(1, last), DEB, "LIVRARIA PAGINA CERTA", -_amt(rng, 120, 260), EDUC)
    sellers = ["LOJA ESTILO URBANO", "CASA E DECOR", "TECH ACESSORIOS"]
    add(rng.randint(1, last), DEB, f"PAGAFACIL*{sellers[idx]}", -_amt(rng, 40, 250), SHOP)
    if idx != 0:
        add(rng.randint(1, last), PIX_IN, "PAGAFACIL REPASSE VENDAS", _amt(rng, 80, 300), INC)

    # internal movements (skipped by the classifier)
    add(6, PIX_OUT, OWN_NAME, -float(rng.choice([500, 800, 1000])), None)
    add(7, "Aplicação", "CDB LIQUIDEZ DIARIA", -float(rng.choice([700, 1000])), None)
    if idx == 1:
        add(25, "Resgate", "CDB LIQUIDEZ DIARIA", 600.00, None)
    add(12, "Pagamento fatura", "PAGAMENTO FATURA CARTAO", -_amt(rng, 450, 900), None)
    if idx != 2:
        add(rng.randint(1, last), "Saque", "SAQUE BANCO 24 HORAS", -float(rng.choice([100, 200])), None)

    # not covered by the rules: recurring every month
    for d in _days(rng, rng.randint(3, 4), last):
        add(d, DEB, "CAFETERIA GRAO NOBRE", -_amt(rng, 9, 28), REST)
    for d in _days(rng, rng.randint(2, 3), last):
        add(d, DEB, "LANCHONETE DA ESQUINA", -_amt(rng, 12, 35), REST)
    for d in _days(rng, rng.randint(1, 2), last):
        add(d, DEB, "ESTACIONAMENTO CENTRAL PARK", -_amt(rng, 12, 30), TRAN)
    add(rng.randint(1, last), DEB, "PET SHOP AMIGO FIEL", -_amt(rng, 45, 160), SHOP)
    add(last, "Rendimento", "RENDIMENTO CONTA REMUNERADA", _amt(rng, 8, 25), INC)

    # not covered by the rules: one-offs (some are deliberately ambiguous)
    one_offs = {
        0: [
            (DEB, "POUSADA MAR AZUL", 380, 620, TRAV),
            (DEB, "VOEBEM LINHAS AEREAS", 640, 980, TRAV),
            (DEB, "LABORATORIO ANALISES VIDA", 60, 180, HLTH),
            (DEB, "CALCADOS PASSO FIRME", 150, 320, SHOP),
            (DEB, "CHURRASCARIA BRASA VIVA", 90, 210, REST),
            (PIX_OUT, "CHAVEIRO SEGURO 24H", 80, 160, HOUS),
            (BILL, "GUIA IPVA 2026 COTA 3", 280, 420, FEES),
            (PIX_OUT, "PEDRO H LIMA", 50, 150, OTH),
        ],
        1: [
            (PIX_OUT, "CLINICA ODONTO SORRISO", 200, 450, HLTH),
            (DEB, "MAGAZINE ELETRO LAR", 300, 900, SHOP),
            (DEB, "CURSO ONLINE APRENDA MAIS", 97, 197, EDUC),
            (DEB, "PEDAGIO RODOVIA DAS FLORES", 8, 22, TRAN),
            (DEB, "MATERIAL DE CONSTRUCAO TIJOLAO", 120, 380, HOUS),
            (BILL, "CARTORIO 2 OFICIO DE NOTAS", 40, 120, FEES),
            (PIX_IN, "MARCOS A ROCHA", 300, 600, INC),
            (PIX_OUT, "INSTITUTO ESPERANCA DOACAO", 30, 100, OTH),
            (DEB, "PAG*GAMEPLAY STORE", 25, 120, SHOP),
        ],
        2: [
            (DEB, "OTICA VISAO CLARA", 250, 600, HLTH),
            (DEB, "EXPRESSO SUL RODOVIARIA", 90, 210, TRAV),
            (DEB, "FLORICULTURA JARDIM SECRETO", 60, 140, SHOP),
            (DEB, "BORRACHARIA DO ZE", 30, 90, TRAN),
            ("Juros", "JUROS CHEQUE ESPECIAL", 5, 30, FEES),
            (PIX_IN, "CARLA M SOUZA", 40, 180, INC),
            (DEB, "PAPELARIA MATERIAL ESCOLAR", 35, 120, EDUC),
            (PIX_OUT, "JOSE ELETRICISTA REPAROS", 120, 300, HOUS),
            (DEB, "VIDEOAULAS PREMIUM MENSAL", 29, 59, EDUC),
        ],
    }
    for hist, desc, lo, hi, cat in one_offs[idx]:
        a = _amt(rng, lo, hi)
        add(rng.randint(1, last), hist, desc, a if hist == PIX_IN else -a, cat)
    return ev


def build(seed: int = SEED):
    """Returns [(year, month, [Event with balance])] in chronological order."""
    rng = random.Random(seed)
    balance = OPENING_BALANCE
    out = []
    for idx, (y, m) in enumerate(MONTHS):
        evs = month_events(rng, y, m, idx)
        rng.shuffle(evs)
        evs.sort(key=lambda e: e.day)  # stable: same-day order stays shuffled
        rows = []
        for e in evs:
            balance = round(balance + e.amount, 2)
            rows.append((e, balance))
        out.append((y, m, rows))
    return out


def statement_text(y: int, m: int, rows) -> str:
    last = monthrange(y, m)[1]
    closing = rows[-1][1]
    lines = [
        "Extrato Conta Corrente",
        "Conta ;0001234-5",
        f"Período ;01/{m:02d}/{y} a {last:02d}/{m:02d}/{y}",
        f"Saldo ;{format_brl(closing)}",
        "",
        "Data Lançamento;Histórico;Descrição;Valor;Saldo",
    ]
    for e, bal in reversed(rows):  # banks list the newest row first
        lines.append(
            f"{date(y, m, e.day):%d/%m/%Y};{e.history};{e.description};{format_brl(e.amount)};{format_brl(bal)}"
        )
    return "\n".join(lines) + "\n"


def write_all(root: Path = config.ROOT, seed: int = SEED) -> dict:
    data = build(seed)
    statements = root / "data" / "statements"
    statements.mkdir(parents=True, exist_ok=True)
    files = []
    for y, m, rows in data:
        p = statements / f"statement-{y}-{m:02d}.csv"
        p.write_bytes(statement_text(y, m, rows).encode(ENCODING_BY_MONTH[(y, m)]))
        files.append(p)
    save_rules(SEED_RULES, root / "data" / "rules.csv")

    # golden set: every unique description the seed rules do not catch, with its expected category
    book = RuleBook(SEED_RULES)
    golden: dict[str, tuple[str, str, str]] = {}
    total = covered = internal = 0
    for _, _, rows in data:
        for e, _ in rows:
            total += 1
            h, d = normalize(e.history), normalize(e.description)
            if internal_reason(h, d, [OWN_NAME]):
                internal += 1
                continue
            m = book.match(d, h, e.amount)
            if m:
                covered += 1
                assert m[1] == e.category, (d, m[1], e.category)  # the seed rules are right by construction
                continue
            golden.setdefault(d, (h, "in" if e.amount > 0 else "out", e.category))
    gdir = root / "golden"
    gdir.mkdir(parents=True, exist_ok=True)
    with open(gdir / "labels.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["description", "history", "direction", "expected_category"])
        for d in sorted(golden):
            w.writerow([d, *golden[d]])
    return {
        "statements": [p.name for p in files],
        "rows": total,
        "rows_per_month": [len(r) for _, _, r in data],
        "covered_by_rules": covered,
        "internal": internal,
        "left_for_llm": total - covered - internal,
        "rule_coverage": round(covered / total, 3),
        "golden_descriptions": len(golden),
    }
