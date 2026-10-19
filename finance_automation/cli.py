"""python -m finance_automation <command>

  generate                          write synthetic statements, seed rules and golden labels
  import FILE [FILE ...]            parse, reconcile, dedup into the ledger, classify (rules, then LLM)
  classify                          re-run classification over the whole ledger
  review [--approve ID [--category X]] [--approve-all-suggested]
  report --month YYYY-MM            write reports/<month>.md and .json
  eval                              score the LLM classifier on golden/labels.csv
  demo [--live]                     generate -> import 3 months -> re-import month 1 -> approve -> report -> eval

LLM mode: --demo replays recorded answers only (no API call); --live requires a key; default 'auto'
(live when a key exists, but recorded answers are always used first). 'demo' defaults to --demo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, evaluate, report, review, synthetic
from .classifier import classify_ledger
from .ledger import Ledger
from .llm import LLM
from .rules import RuleBook, load_rules
from .statement import parse_statement


def _llm(args, default: str = "auto") -> LLM | None:
    if getattr(args, "no_llm", False):
        return None
    mode = "demo" if args.demo else "live" if args.live else default
    return LLM(mode, args.max_calls)


def _summary(llm: LLM | None) -> None:
    info = llm.summary() if llm else {"mode": "no-llm", "api_calls": 0, "estimated_cost_usd": 0.0}
    print("LLM summary: " + json.dumps(info))


def do_import(ledger: Ledger, files, llm: LLM | None, rules_path: Path) -> list[dict]:
    out = []
    for f in files:
        st = parse_statement(f)
        res = ledger.add_statement(st)
        stats = classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm)
        res["classification"] = stats
        out.append(res)
        print(f"{res['file']}: {res['rows_in_file']} rows, {res['new_rows']} new, {res['duplicates']} duplicates "
              f"skipped | balance check {'OK' if res['reconciled'] else 'FAILED'} ({res['reconciliation']}) | "
              f"encoding {res['encoding']}")
        print(f"  unique descriptions needing the LLM: {stats['descriptions_needing_llm']}, classified now: "
              f"{stats['descriptions_classified_now']} | ledger by method: {stats['by_method']}"
              + (f"; stopped: {stats['stopped']}" if stats["stopped"] else ""))
    return out


def print_queue(ledger: Ledger) -> None:
    q = review.queue(ledger)
    if not q:
        print("Review queue is empty.")
        return
    print(f"Review queue ({len(q)}):")
    for it in q:
        print(f"  [{it['id']}] {it['description']} | {it['rows']} row(s), {it['total']:.2f} | LLM: "
              f"{it['llm_category']} ({it['confidence']:.2f}) - {it['reason']} | keyword: {it['suggested_keyword']}")


def run_demo(args) -> int:
    llm = LLM("live" if args.live else "demo", args.max_calls)
    try:
        print("1. generate synthetic data")
        print("   " + json.dumps(synthetic.write_all()))
        ledger_path = Path(args.ledger)
        if ledger_path.exists():
            ledger_path.unlink()
        ledger = Ledger(ledger_path)
        files = sorted(config.STATEMENTS.glob("statement-*.csv"))
        print("2. import the three months")
        do_import(ledger, files, llm, Path(args.rules))
        print("3. import month 1 again (idempotency)")
        do_import(ledger, files[:1], llm, Path(args.rules))
        print("4. review: approve the suggestions with a concrete category (\"Other\" waits for a person)")
        print_queue(ledger)
        for r in review.approve_all_suggested(ledger, Path(args.rules)):
            if "reclassified" in r:
                print(f"   reclassified: {r['reclassified']['by_method']}")
            else:
                print(f"   [{r['id']}] {r['description']} -> {r['category']}: {r['note']}")
        print("5. reports")
        for f in files:
            month = f.stem.replace("statement-", "")
            print(f"   {report.write(ledger, month).relative_to(config.ROOT).as_posix()}")
        ledger.close()
        print("6. eval on the golden set")
        res = evaluate.run(llm)
        (config.REPORTS / "eval.md").write_text(evaluate.to_markdown(res), encoding="utf-8")
        print(evaluate.to_text(res))
    finally:
        _summary(llm)
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(prog="finance_automation", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ledger", default=str(config.LEDGER))
    p.add_argument("--rules", default=str(config.RULES))
    sub = p.add_subparsers(dest="cmd", required=True)

    def llm_flags(sp):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--demo", action="store_true", help="replay recorded answers only (no API call)")
        g.add_argument("--live", action="store_true", help="require an API key")
        sp.add_argument("--max-calls", type=int, default=config.MAX_CALLS_PER_RUN)

    sub.add_parser("generate")
    sp = sub.add_parser("import")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--no-llm", action="store_true", help="rules only; leave the rest unclassified")
    llm_flags(sp)
    sp = sub.add_parser("classify")
    sp.add_argument("--no-llm", action="store_true")
    llm_flags(sp)
    sp = sub.add_parser("review")
    sp.add_argument("--approve", type=int, metavar="ID")
    sp.add_argument("--category", choices=config.CATEGORY_LIST)
    sp.add_argument("--approve-all-suggested", action="store_true")
    sp = sub.add_parser("report")
    sp.add_argument("--month", required=True, help="YYYY-MM")
    sp.add_argument("--no-json", action="store_true")
    sp = sub.add_parser("eval")
    llm_flags(sp)
    sp = sub.add_parser("demo")
    sp.add_argument("--live", action="store_true", help="call the API for answers that are not recorded yet")
    sp.add_argument("--max-calls", type=int, default=config.MAX_CALLS_PER_RUN)
    args = p.parse_args(argv)

    if args.cmd == "demo":
        return run_demo(args)
    if args.cmd == "generate":
        print(json.dumps(synthetic.write_all(), indent=1))
        return 0

    llm = _llm(args) if args.cmd in ("import", "classify", "eval") else None
    try:
        if args.cmd == "eval":
            res = evaluate.run(llm)
            print(evaluate.to_text(res))
            return 0
        ledger = Ledger(args.ledger)
        rules_path = Path(args.rules)
        if args.cmd == "import":
            do_import(ledger, args.files, llm, rules_path)
        elif args.cmd == "classify":
            print(json.dumps(classify_ledger(ledger, RuleBook(load_rules(rules_path)), llm)))
        elif args.cmd == "review":
            if args.approve is not None:
                r = review.approve(ledger, args.approve, args.category, rules_path)
                print(f"[{r['id']}] {r['description']} -> {r['category']}: {r['note']}")
            elif args.approve_all_suggested:
                for r in review.approve_all_suggested(ledger, rules_path):
                    if "reclassified" not in r:
                        print(f"[{r['id']}] {r['description']} -> {r['category']}: {r['note']}")
            print_queue(ledger)
        elif args.cmd == "report":
            path = report.write(ledger, args.month, as_json=not args.no_json)
            print(f"wrote {path.relative_to(config.ROOT).as_posix() if path.is_relative_to(config.ROOT) else path}")
        ledger.close()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        _summary(llm)
    return 0
