"""Build a small, self-contained demo slice preserving whole account histories."""
import pandas as pd
import sys
import os

# Adds "D:\Sentinel" to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.loader import load
from tools.filters import filter_analyzable

TARGET_ACCOUNTS = 1200


def main():
    df, _ = filter_analyzable(load("data/raw/HI-Small_Trans.csv",
                                   schema="ibm_aml"), verbose=False)

    laundering = df[df["is_laundering"] == 1]
    dirty = set(laundering["sender"]) | set(laundering["receiver"])

    # keep active clean accounts so patterns have context
    counts = df["sender"].value_counts()
    clean_pool = [a for a in counts[counts.between(5, 60)].index
                  if a not in dirty]

    keep = set(list(dirty)[:400]) | set(clean_pool[:TARGET_ACCOUNTS])

    # whole histories, not fragments
    slice_ = df[df["sender"].isin(keep) | df["receiver"].isin(keep)]

    # bound size while preserving every laundering row
    if len(slice_) > 60_000:
        laund = slice_[slice_["is_laundering"] == 1]
        rest = slice_[slice_["is_laundering"] == 0].sample(
            60_000 - len(laund), random_state=42)
        slice_ = pd.concat([laund, rest]).sort_values("timestamp")

    out = "data/sample/demo_transactions.csv"
    slice_.to_csv(out, index=False)

    print(f"{len(slice_):,} transactions -> {out}")
    print(f"laundering: {(slice_['is_laundering']==1).sum()} "
          f"({(slice_['is_laundering']==1).mean():.2%})")
    print(f"accounts: {pd.concat([slice_['sender'], slice_['receiver']]).nunique():,}")
    print(f"size: {pd.read_csv(out).memory_usage(deep=True).sum()/1e6:.1f} MB")


if __name__ == "__main__":
    main()