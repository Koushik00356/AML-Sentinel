"""Population filters.

Institutional hub accounts (banks, exchanges, settlement nodes) sit outside
the scope of customer-level AML monitoring and would otherwise dominate every
detector: they legitimately show extreme velocity, hundreds of counterparties
and constant pass-through behaviour. They are handled by separate
correspondent-banking controls in a real compliance programme.

Every filter here reports how much labelled ground truth it removes, so
narrowing the population can never silently destroy the ability to evaluate.
"""

from __future__ import annotations

import pandas as pd

DEFAULT_MAX_OUT = 5000
DEFAULT_MAX_IN = 5000
DEFAULT_MIN_ACTIVITY = 2


def identify_hubs(df: pd.DataFrame,
                  max_out: int = DEFAULT_MAX_OUT,
                  max_in: int = DEFAULT_MAX_IN) -> set[str]:
    """Accounts whose throughput marks them as institutional rather than retail."""
    out_counts = df["sender"].value_counts()
    in_counts = df["receiver"].value_counts()
    return (set(out_counts[out_counts > max_out].index)
            | set(in_counts[in_counts > max_in].index))


def retention_report(before: pd.DataFrame,
                     after: pd.DataFrame,
                     label: str = "filter") -> dict:
    """Report transaction and labelled-laundering retention across a filter."""
    tx_before, tx_after = len(before), len(after)

    if "is_laundering" in before.columns:
        lb = int((before["is_laundering"] == 1).sum())
        la = int((after["is_laundering"] == 1).sum())
    else:
        lb = la = 0

    stats = {
        "filter": label,
        "tx_before": tx_before,
        "tx_after": tx_after,
        "tx_retained": tx_after / tx_before if tx_before else 0.0,
        "laundering_before": lb,
        "laundering_after": la,
        "laundering_retained": la / lb if lb else 0.0,
    }

    print(f"{label}: {tx_after:,}/{tx_before:,} transactions "
          f"({stats['tx_retained']:.1%})", end="")
    if lb:
        print(f" | laundering {la}/{lb} ({stats['laundering_retained']:.1%} retained)")
    else:
        print()

    return stats


def filter_analyzable(df: pd.DataFrame,
                      max_out: int = DEFAULT_MAX_OUT,
                      max_in: int = DEFAULT_MAX_IN,
                      min_activity: int = DEFAULT_MIN_ACTIVITY,
                      verbose: bool = True) -> tuple[pd.DataFrame, set[str]]:
    """Drop institutional hubs and accounts too sparse to analyse.

    Returns the filtered frame and the set of hub accounts removed.
    """
    hubs = identify_hubs(df, max_out=max_out, max_in=max_in)

    d = df[~df["sender"].isin(hubs) & ~df["receiver"].isin(hubs)]
    if verbose:
        retention_report(df, d, f"hub removal ({len(hubs)} accounts)")

    if min_activity > 1:
        active = d["sender"].value_counts()
        keep = set(active[active >= min_activity].index)
        d2 = d[d["sender"].isin(keep) | d["receiver"].isin(keep)]
        if verbose:
            retention_report(d, d2, f"activity floor (>={min_activity} sent)")
        d = d2

    return d.reset_index(drop=True), hubs


def filter_by_currency(df: pd.DataFrame,
                       currencies: list[str],
                       verbose: bool = True) -> pd.DataFrame:
    """Restrict to specific currencies. Use sparingly and document the reason."""
    out = df[df["currency"].isin(currencies)]
    if verbose:
        retention_report(df, out, f"currency in {currencies}")
    return out.reset_index(drop=True)


def filter_by_date(df: pd.DataFrame,
                   start: str | pd.Timestamp | None = None,
                   end: str | pd.Timestamp | None = None,
                   days_back: int | None = None,
                   verbose: bool = False) -> pd.DataFrame:
    """Time-window filter used by the agent when a query carries a date range."""
    out = df

    if days_back is not None:
        cutoff = out["timestamp"].max() - pd.Timedelta(days=days_back)
        out = out[out["timestamp"] >= cutoff]
    if start is not None:
        out = out[out["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["timestamp"] <= pd.Timestamp(end)]

    if verbose:
        retention_report(df, out, "date window")
    return out.reset_index(drop=True)


def filter_by_entities(df: pd.DataFrame,
                       account_ids: list[str],
                       verbose: bool = False) -> pd.DataFrame:
    """Restrict to transactions touching specific accounts (single-entity queries)."""
    ids = {str(a) for a in account_ids}
    out = df[df["sender"].astype(str).isin(ids)
             | df["receiver"].astype(str).isin(ids)]
    if verbose:
        retention_report(df, out, f"entities {sorted(ids)[:3]}")
    return out.reset_index(drop=True)


def filter_by_amount(df: pd.DataFrame,
                     min_amount: float | None = None,
                     max_amount: float | None = None,
                     use_usd: bool = True,
                     verbose: bool = False) -> pd.DataFrame:
    """Amount-band filter. Compares in USD-equivalent by default."""
    out = df
    col = "amount"

    if use_usd:
        if "amount_usd" not in out.columns:
            from tools.currency import to_usd
            out = to_usd(out)
        col = "amount_usd"

    if min_amount is not None:
        out = out[out[col] >= min_amount]
    if max_amount is not None:
        out = out[out[col] <= max_amount]

    if verbose:
        retention_report(df, out, "amount band")
    return out.reset_index(drop=True)