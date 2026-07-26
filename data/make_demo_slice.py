"""Build a self-contained demo slice preserving whole account histories.

A random sample of a 4.5M-row transaction file is useless: every account's
history is fragmented, so multi-transaction typologies cannot appear. This
selects whole accounts instead, keeps every labelled laundering transaction,
and writes Parquet so a meaningful volume fits inside the repository.
"""

import argparse
from pathlib import Path

import pandas as pd

from tools.filters import filter_analyzable
from tools.loader import load

SOURCE = "data/raw/HI-Small_Trans.csv"
OUT_DIR = Path("data/sample")


def build(source: str, target_rows: int, dirty_accounts: int,
          clean_accounts: int, fmt: str, seed: int = 42):
    df, _ = filter_analyzable(load(source, schema="ibm_aml"), verbose=False)

    laundering = df[df["is_laundering"] == 1]
    dirty = list(dict.fromkeys(
        list(laundering["sender"]) + list(laundering["receiver"])))

    counts = df["sender"].value_counts()
    clean_pool = [a for a in counts[counts.between(3, 200)].index
                  if a not in set(dirty)]

    keep = set(dirty[:dirty_accounts]) | set(clean_pool[:clean_accounts])
    print(f"selected {len(keep):,} accounts "
          f"({min(len(dirty), dirty_accounts):,} laundering-involved)")

    sliced = df[df["sender"].isin(keep) | df["receiver"].isin(keep)]
    print(f"whole histories: {len(sliced):,} transactions")

    # bound size, but never drop a labelled laundering row
    if len(sliced) > target_rows:
        laund = sliced[sliced["is_laundering"] == 1]
        room = max(target_rows - len(laund), 0)
        rest = sliced[sliced["is_laundering"] == 0]
        if room and len(rest) > room:
            rest = rest.sample(room, random_state=seed)
        sliced = pd.concat([laund, rest])

    sliced = sliced.sort_values("timestamp").reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"demo_transactions.{fmt}"

    if fmt == "parquet":
        sliced.to_parquet(out, index=False, compression="snappy")
    else:
        sliced.to_csv(out, index=False)

    accounts = pd.concat([sliced["sender"], sliced["receiver"]]).nunique()
    laund_n = int((sliced["is_laundering"] == 1).sum())
    size_mb = out.stat().st_size / 1e6

    print(f"\nwrote {out}")
    print(f"  transactions : {len(sliced):,}")
    print(f"  accounts     : {accounts:,}")
    print(f"  laundering   : {laund_n:,} ({laund_n / len(sliced):.2%})")
    print(f"  date range   : {sliced['timestamp'].min():%Y-%m-%d} to "
          f"{sliced['timestamp'].max():%Y-%m-%d}")
    print(f"  file size    : {size_mb:.1f} MB")

    if size_mb > 40:
        print("\n  WARNING: over 40 MB — reduce --rows before committing.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default=SOURCE)
    p.add_argument("--rows", type=int, default=400_000,
                   help="maximum transactions in the slice")
    p.add_argument("--dirty", type=int, default=2_000,
                   help="laundering-involved accounts to include")
    p.add_argument("--clean", type=int, default=8_000,
                   help="clean accounts to include for context")
    p.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    args = p.parse_args()

    build(args.source, args.rows, args.dirty, args.clean, args.format)


if __name__ == "__main__":
    main()