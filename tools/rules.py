import pandas as pd
from tools.features import REPORTING_THRESHOLD, NEAR_FLOOR, account_features, rapid_cashout


def detect_structuring(df: pd.DataFrame,
                       threshold: float = REPORTING_THRESHOLD,
                       window_days: int = 5,
                       min_count: int = 3,
                       near_floor: float = NEAR_FLOOR) -> list[dict]:
    sub = df[(df["amount"] < threshold) &
             (df["amount"] >= threshold * near_floor)]
    hits = []
    window = pd.Timedelta(days=window_days)

    for account, grp in sub.groupby("sender"):
        grp = grp.sort_values("timestamp")
        times = grp["timestamp"]
        for i in range(len(grp)):
            in_window = (times >= times.iloc[i]) & (times <= times.iloc[i] + window)
            if in_window.sum() >= min_count:
                rows = grp[in_window]
                hits.append({
                    "account": account,
                    "typology": "structuring",
                    "tx_ids": rows["tx_id"].tolist(),
                    "count": int(len(rows)),
                    "total": float(rows["amount"].sum()),
                    "window_days": window_days,
                    "threshold": threshold,
                    "start": rows["timestamp"].min(),
                    "end": rows["timestamp"].max(),
                })
                break
    return hits


def detect_smurfing(df: pd.DataFrame,
                    threshold: float = REPORTING_THRESHOLD,
                    min_senders: int = 3,
                    window_days: int = 5) -> list[dict]:
    sub = df[df["amount"] < threshold].copy()
    sub["window"] = sub["timestamp"].dt.floor(f"{window_days}D")
    grouped = sub.groupby(["receiver", "window"]).agg(
        senders=("sender", "nunique"),
        count=("tx_id", "count"),
        total=("amount", "sum"),
        tx_ids=("tx_id", list),
    ).reset_index()

    flagged = grouped[grouped["senders"] >= min_senders]
    return [{
        "account": r["receiver"],
        "typology": "smurfing",
        "tx_ids": r["tx_ids"],
        "count": int(r["count"]),
        "unique_senders": int(r["senders"]),
        "total": float(r["total"]),
    } for _, r in flagged.iterrows()]


def detect_velocity(df: pd.DataFrame, sigma: float = 3.0) -> list[dict]:
    acct = account_features(df)
    mu, sd = acct["velocity"].mean(), acct["velocity"].std()
    if not sd or pd.isna(sd):
        return []
    spikes = acct[acct["velocity"] > mu + sigma * sd]
    return [{
        "account": idx,
        "typology": "velocity",
        "tx_ids": [],
        "velocity": float(r["velocity"]),
        "baseline": float(mu),
        "count": int(r["out_count"]),
    } for idx, r in spikes.iterrows()]


def detect_rapid_cashout(df: pd.DataFrame, max_gap_hours: int = 48) -> list[dict]:
    pairs = rapid_cashout(df, max_gap_hours=max_gap_hours)
    return [{
        "account": r["account"],
        "typology": "rapid_cashout",
        "tx_ids": [r["in_tx"], r["out_tx"]],
        "in_amount": float(r["in_amount"]),
        "out_amount": float(r["out_amount"]),
        "gap_hours": round(float(r["gap_hours"]), 1),
        "count": 2,
    } for _, r in pairs.iterrows()]