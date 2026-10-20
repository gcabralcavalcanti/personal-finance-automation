"""Paths, categories, model choice and cost limits. Everything that costs money is capped here."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATEMENTS = DATA / "statements"  # synthetic monthly bank statements (versioned)
RULES = DATA / "rules.csv"  # keyword rules; review appends learned rules here (versioned)
LEDGER = DATA / "ledger.sqlite"  # local ledger (not versioned)
GOLDEN = ROOT / "tests" / "golden"  # expected categories for the rows the rules do not catch
RECORDINGS = DATA / "recorded"  # recorded LLM answers: response cache + demo mode (versioned)
FINAL_REPORT = ROOT / "final-report.pdf"
OUTPUT = ROOT / "output"  # generated monthly reports and eval (versioned, so the repo shows real output)
DOCS = ROOT / "docs"
LOGS = OUTPUT / "logs"  # one JSON line per LLM call (not versioned)

# Fixed category list. The one-line definitions go into the system prompt.
CATEGORIES = {
    "Groceries": "supermarkets, bakeries, produce markets, butchers, wholesale clubs: food and supplies for home",
    "Restaurants & Delivery": "restaurants, cafes, snack bars, bars and food-delivery apps",
    "Transport": "ride-hailing, public transit, fuel, parking, tolls, tyre and car repair",
    "Housing": "rent, condominium fee, home repairs, locksmith, electrician, building materials",
    "Utilities": "electricity, water, gas, internet and phone bills",
    "Subscriptions": "recurring digital services billed monthly: streaming, music, cloud storage, apps",
    "Health": "pharmacies, doctors, dentists, labs, opticians, gyms, health insurance",
    "Education": "schools, courses, tuition, study books and school supplies",
    "Shopping": "retail goods: clothes, shoes, electronics, appliances, gifts, flowers, pets, games, marketplaces",
    "Travel": "flights, hotels, inns, intercity buses and other costs of trips away from home",
    "Income": "salary, payments and reimbursements received, sales, interest and cashback received",
    "Fees & Taxes": "bank fees, interest charged, IOF, vehicle and property taxes, notary and government fees",
    "Other": "transfers to people with no stated purpose, donations, anything that fits no other category",
}
CATEGORY_LIST = list(CATEGORIES)

# Movements between the holder's own pockets are not income or expense: they are skipped.
OWN_NAMES = [n.strip().upper() for n in os.environ.get("FINANCE_OWN_NAMES", "ANA EXEMPLO").split(",") if n.strip()]
INVESTMENT_HISTORY = ("APLICACAO", "RESGATE")  # investment application / redemption
CARD_BILL = ("PAGAMENTO FATURA", "PAGAMENTO DE FATURA")  # credit-card bill paid from the account
CASH_WITHDRAWAL = ("SAQUE",)
TRANSFER_HISTORY = ("PIX", "TED", "TRANSFERENCIA")  # combined with OWN_NAMES in the description

# Cheapest model that handles short structured classification.
MODEL = os.environ.get("FINANCE_MODEL", "claude-haiku-5-5")
PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # USD (input, output), Anthropic price list

# Hard limits per run.
MAX_CALLS_PER_RUN = int(os.environ.get("FINANCE_MAX_CALLS", "10"))
BATCH_SIZE = 20  # unique descriptions per call
TOKENS_PER_ITEM = 90  # measured live: ~45-65 output tokens per item; margin against truncation
TOKENS_BASE = 150
TIMEOUT_S = 45.0
SDK_RETRIES = 2  # network/429/5xx retries done by the SDK
SCHEMA_RETRIES = 1  # one extra call if the answer fails our own checks

CONFIDENCE_THRESHOLD = float(os.environ.get("FINANCE_CONFIDENCE", "0.8"))
MIN_KEYWORD_LEN = 3


def max_tokens_for(n_items: int) -> int:
    """Output budget for a batch: 20 items -> 1950 tokens. Only tokens actually produced are billed."""
    return TOKENS_BASE + TOKENS_PER_ITEM * n_items
