"""One command: synthetic statements, import, classification (recorded AI answers), review, reports, eval, PDF."""

import sys

from finance_automation import page
from finance_automation.cli import main

if __name__ == "__main__":
    code = main(["demo", *sys.argv[1:]])
    if not code:
        print(f"One page with everything: {page.build().relative_to(page.ROOT)}")
    sys.exit(code)
