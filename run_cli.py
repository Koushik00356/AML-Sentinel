import argparse
from tools.loader import load
from tools.rules import (detect_structuring, detect_smurfing,
                         detect_velocity, detect_rapid_cashout)
from tools.risk import score_hits
from tools.explain import explain_account
from dotenv import load_dotenv
load_dotenv()
DETECTORS = {
    "structuring": detect_structuring,
    "smurfing": detect_smurfing,
    "velocity": detect_velocity,
    "rapid_cashout": detect_rapid_cashout,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/sample/sample_transactions.csv")
    p.add_argument("--schema", default="synthetic")
    p.add_argument("--nrows", type=int, default=None)
    p.add_argument("--top", type=int, default=5)
    args = p.parse_args()

    df = load(args.data, schema=args.schema, nrows=args.nrows)
    print(f"Loaded {len(df):,} transactions "
          f"({df['timestamp'].min().date()} to {df['timestamp'].max().date()})\n")

    hits = []
    for name, fn in DETECTORS.items():
        found = fn(df)
        print(f"  {name:<16} {len(found)} hits")
        hits.extend(found)

    results = score_hits(hits)
    print(f"\n{len(results)} accounts flagged. Top {args.top}:\n")

    for _, row in results.head(args.top).iterrows():
        out = explain_account(row.to_dict())
        print(out["summary"])
        for r in out["reasons"]:
            print(f"  - {r}")
        print(f"  ACTION: {out['action'].upper()} — {out['action_text']}\n")

    
if __name__ == "__main__":
    main()