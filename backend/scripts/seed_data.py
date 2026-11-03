"""Seed the configured database with the clean batch, or run one scenario.

    python scripts/seed_data.py                 # reset + clean batch
    python scripts/seed_data.py missing         # run one scenario on top of existing data
    python scripts/seed_data.py --export FILE   # write the 1,000 clean source rows as JSON

Run from the backend/ folder with the virtual environment active.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.services import synthetic  # noqa: E402
from app.services.demo import SCENARIOS, run_scenario, seed_demo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scenario", nargs="?", choices=SCENARIOS, help="scenario to run instead of seeding")
    parser.add_argument("--export", metavar="FILE", help="write the clean source batch to a JSON file")
    args = parser.parse_args()

    if args.export:
        rows = synthetic.generate_transactions(seed=settings.seed)
        Path(args.export).write_text(json.dumps(rows, default=str, indent=2))
        summary = synthetic.expected_summary(rows)
        print(f"Wrote {summary['count']} rows, sum {summary['sum_cents']} cents to {args.export}")
        return

    with SessionLocal() as session:
        if args.scenario:
            outcome = run_scenario(session, args.scenario, seed=settings.seed)
            print(json.dumps(outcome.to_dict(), indent=2, default=str))
        else:
            result = seed_demo(session, engine, seed=settings.seed)
            print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
