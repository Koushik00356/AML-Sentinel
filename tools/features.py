import numpy as np
import pandas as pd

REPORTING_THRESHOLD = 10_000.0
NEAR_FLOOR = 0.75


def add_transaction_features(df: pd.DataFrame,
                             threshold: float = REPORTING_THRESHOLD) -> pd.DataFrame:
    out = df.copy()
    out["is_near_threshold"] = (
        (out["amount"] < threshold) & (out["amount"] >= threshold * NEAR_FLOOR)
    )
    out["is_round_amount"] = (out["amount"] % 1000 == 0)
    out["hour"] = out["timestamp"].dt.hour
    return out


def rolling_features(df: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    d = df.sort_values("timestamp").set_index("timestamp")
    grp = d.groupby("sender")["amount"]
    win = f"{window_days}D"
    d["rolling_sum"] = grp.rolling(win).sum().reset_index(level=0, drop=True)
    d["rolling_count"] = grp.rolling(win).count().reset_index(level=0, drop=True)
    return d.reset_index()


def account_features(df: pd.DataFrame,
                     threshold: float = REPORTING_THRESHOLD) -> pd.DataFrame:
    tx = add_transaction_features(df, threshold)

    sent = tx.groupby("sender").agg(
        out_count=("tx_id", "count"),
        total_sent=("amount", "sum"),
        mean_amount=("amount", "mean"),
        std_amount=("amount", "std"),
        max_amount=("amount", "max"),
        near_threshold_count=("is_near_threshold", "sum"),
        round_amount_count=("is_round_amount", "sum"),
        unique_receivers=("receiver", "nunique"),
        first_tx=("timestamp", "min"),
        last_tx=("timestamp", "max"),
    )
    sent.index.name = "account"

    recv = tx.groupby("receiver").agg(
        in_count=("tx_id", "count"),
        total_received=("amount", "sum"),
        unique_senders=("sender", "nunique"),
    )
    recv.index.name = "account"

    acct = sent.join(recv, how="outer")
    acct[["out_count", "in_count", "near_threshold_count",
          "round_amount_count"]] = acct[["out_count", "in_count",
                                         "near_threshold_count",
                                         "round_amount_count"]].fillna(0)

    span = (acct["last_tx"] - acct["first_tx"]).dt.days
    acct["active_days"] = span.fillna(1).clip(lower=1)
    acct["velocity"] = acct["out_count"] / acct["active_days"]
    acct["near_threshold_ratio"] = (
        acct["near_threshold_count"] / acct["out_count"].replace(0, np.nan)
    ).fillna(0)
    acct["flow_ratio"] = (
        acct["total_sent"].fillna(0) / acct["total_received"].replace(0, np.nan)
    ).fillna(0)
    return acct

def rapid_cashout(df, max_gap_hours=24, ratio_low=0.85, ratio_high=1.15,
                  min_amount_usd=5000, min_events=2):
    from tools.currency import to_usd
    d = to_usd(df)

    inflow = (d[["receiver", "timestamp", "amount_usd", "tx_id"]]
              .rename(columns={"receiver": "account", "timestamp": "in_time",
                               "amount_usd": "in_amount", "tx_id": "in_tx"})
              .sort_values("in_time"))
    outflow = (d[["sender", "timestamp", "amount_usd", "tx_id"]]
               .rename(columns={"sender": "account", "timestamp": "out_time",
                                "amount_usd": "out_amount", "tx_id": "out_tx"})
               .sort_values("out_time"))

    m = pd.merge_asof(
        outflow, inflow,
        left_on="out_time", right_on="in_time",
        by="account", direction="backward",
        tolerance=pd.Timedelta(hours=max_gap_hours),
    ).dropna(subset=["in_time"])

    m["gap_hours"] = (m["out_time"] - m["in_time"]).dt.total_seconds() / 3600
    m["cashout_ratio"] = m["out_amount"] / m["in_amount"]

    m = m[
        (m["cashout_ratio"].between(ratio_low, ratio_high)) &
        (m["in_amount"] >= min_amount_usd)
    ]

    # require repeated pass-through, not a single coincidence
    counts = m.groupby("account").size()
    repeat = counts[counts >= min_events].index
    return m[m["account"].isin(repeat)].reset_index(drop=True)