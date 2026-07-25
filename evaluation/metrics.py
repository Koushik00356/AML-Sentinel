"""Validate detectors against labelled ground truth."""
import argparse
import pandas as pd

from tools.loader import load
from tools.filters import filter_analyzable
from tools.rules import (detect_structuring, detect_smurfing,
                         detect_velocity, detect_rapid_cashout)
from tools.graph import (detect_fan_in, detect_fan_out,
                         detect_cycles, detect_layering)

DETECTORS = {
    "structuring":   detect_structuring,
    "smurfing":      detect_smurfing,
    "velocity":      detect_velocity,
    "rapid_cashout": detect_rapid_cashout,
    "fan_in":        detect_fan_in,
    "fan_out":       detect_fan_out,
    "cycle":         detect_cycles,
    "layering":      detect_layering,
}


def evaluate(df: pd.DataFrame) -> pd.DataFrame:
    laundering = df[df["is_laundering"] == 1]
    truth = {str(a) for a in
             set(laundering["sender"]) | set(laundering["receiver"])}

    print(f"transactions      : {len(df):,}")
    print(f"laundering txns   : {len(laundering):,} "
          f"({len(laundering)/len(df):.3%})")
    print(f"accounts involved : {len(truth):,}\n")

    rows = []
    for name, fn in DETECTORS.items():
        import time
        t0 = time.time()
        try:
            hits = fn(df)
        except Exception as e:
            print(f"{name:<14} ERROR: {e}")
            continue
        elapsed = time.time() - t0

        flagged = {str(h["account"]) for h in hits}
        tp = len(flagged & truth)
        precision = tp / len(flagged) if flagged else 0.0
        recall = tp / len(truth) if truth else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall else 0.0)

        rows.append({
            "detector": name, "hits": len(hits), "accounts": len(flagged),
            "tp": tp, "precision": precision, "recall": recall,
            "f1": f1, "seconds": round(elapsed, 1),
        })
        print(f"{name:<14} accounts={len(flagged):<7} TP={tp:<6} "
              f"P={precision:.2%}  R={recall:.2%}  F1={f1:.3f}  "
              f"[{elapsed:.1f}s]")

    # ensemble: accounts flagged by N or more distinct detectors
    from collections import Counter
    all_hits = []
    for name, fn in DETECTORS.items():
        try:
            all_hits.extend((str(h["account"]), name) for h in fn(df))
        except Exception:
            pass

    counts = Counter()
    for acct, det in set(all_hits):
        counts[acct] += 1

    print("\nensemble (accounts flagged by N+ independent detectors):")
    for n in (1, 2, 3, 4):
        flagged = {a for a, c in counts.items() if c >= n}
        tp = len(flagged & truth)
        p = tp / len(flagged) if flagged else 0
        r = tp / len(truth) if truth else 0
        print(f"  N>={n}: accounts={len(flagged):<7} TP={tp:<5} "
              f"P={p:.2%} ({p/0.011:.1f}x baseline)  R={r:.2%}")

    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/HI-Small_Trans.csv")
    p.add_argument("--schema", default="ibm_aml")
    p.add_argument("--nrows", type=int, default=None)
    p.add_argument("--no-filter", action="store_true")
    args = p.parse_args()

    df = load(args.data, schema=args.schema, nrows=args.nrows)
    if not args.no_filter:
        before = df
        df, hubs = filter_analyzable(df)
        lb = (before["is_laundering"] == 1).sum()
        la = (df["is_laundering"] == 1).sum()
        print(f"dropped {len(hubs)} hubs | laundering retained "
              f"{la}/{lb} ({la/max(lb,1):.1%})\n")

    results = evaluate(df)
    results.to_csv("evaluation/results.csv", index=False)
    print("\nsaved -> evaluation/results.csv")


if __name__ == "__main__":
    main()