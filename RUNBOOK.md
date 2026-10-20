# Runbook

## Run

```
pip install -r requirements.txt
python demo.py            # full example on the synthetic statements, no API key needed
python -m pytest -q       # offline tests
```

## Monthly use with a new statement

1. Export the statement as CSV (format in [docs/how-it-works.md](docs/how-it-works.md#statement-format)) and save it anywhere.
2. Load it: `python -m finance_automation import path/to/statement.csv`
   It prints how many lines were new, how many were already in the database, and whether the balances add up.
   Loading the same file again is safe: nothing is added.
3. See what waits for you: `python -m finance_automation review`
4. Confirm or correct each item: `python -m finance_automation review --approve 12 --category Groceries`
   (without `--category` the AI's suggestion is kept). Each confirmation becomes a rule in `data/rules.csv`.
5. Write the report: `python -m finance_automation report --month 2026-10` (goes to `output/2026-10.md` and `.json`).

To call Claude for shops the rules do not know, set `ANTHROPIC_API_KEY` (or copy `.env.example` to `.env`). Without
a key, only recorded answers are used and unknown shops stay unclassified.

The database is `data/ledger.sqlite`. To start over, delete that file; the next import creates it again.

## When something breaks

| Message or symptom | What to do |
|---|---|
| `table header 'Data Lançamento;...' not found` | The file is not in the expected layout. Open it, compare with the example in `docs/how-it-works.md`, or adapt `statement.py` (same file, "Using another bank") |
| `balance check FAILED` | A line is missing or was edited in the export. Export the statement again; the report says which rows break the chain |
| `could not decode the file` | Save the CSV as UTF-8 and import again |
| `No recorded answer ... run once with an API key` | A shop is new and there is no key. Set `ANTHROPIC_API_KEY`, or classify it with `review` |
| `Call cap reached` | The run stopped at the limit of AI calls (`FINANCE_MAX_CALLS`, default 10). Import again to continue; answers already given are not paid twice |
| A shop keeps getting the wrong category | Approve it with the right `--category`, or edit its line in `data/rules.csv` |
| Totals look doubled | They cannot be, because every transaction is stored once; check that two different accounts were not exported into the same file |
| Tests fail after a change | Run `python -m pytest -q -x` and read the first failure; the tests never call the network |

Each AI call is logged as one line in `output/logs/` with tokens and estimated cost.
