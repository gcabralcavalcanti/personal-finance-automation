"""Write the synthetic statements, the seed rules and the golden labels (deterministic, seeded).

    python generate_data.py [--seed 2026]
"""
import argparse
import json

from finance_automation.synthetic import SEED, write_all

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=SEED)
    print(json.dumps(write_all(seed=p.parse_args().seed), indent=1))
