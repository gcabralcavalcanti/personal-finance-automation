"""One command: synthetic statements, import, classification (recorded AI answers), review, reports, eval, PDF."""

import sys

from finance_automation.cli import main

if __name__ == "__main__":
    sys.exit(main(["demo", *sys.argv[1:]]))
