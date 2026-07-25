import pandas as pd
from tools.features import REPORTING_THRESHOLD, NEAR_FLOOR, account_features, rapid_cashout
from tools.currency import threshold_for, NO_THRESHOLD


def detect_structuring(df, window_days=5, min_count=3, near_floor=0.75):
    hits = []
    window = pd.Timedelta(days=window_days)

    for currency, cur_df in df.groupby("currency"):
        if currency in NO_THRESHOLD:
            continue
        threshold = threshold_for(currency)
        if threshold is None:
            continue

        sub = cur_df[(cur_df["amount"] < threshold) &
                     (cur_df["amount"] >= threshold * near_floor)]

        for account, grp in sub.groupby("sender"):
            grp = grp.sort_values("timestamp")
            times = grp["timestamp"]
            for i in range(len(grp)):
                in_win = (times >= times.iloc[i]) & (times <= times.iloc[i] + window)
                if in_win.sum() >= min_count:
                    rows = grp[in_win]
                    hits.append({
                        "account": account,
                        "typology": "structuring",
                        "tx_ids": rows["tx_id"].tolist(),
                        "count": int(len(rows)),
                        "total": float(rows["amount"].sum()),
                        "currency": currency,
                        "threshold": threshold,
                        "window_days": window_days,
                        "start": rows["timestamp"].min(),
                        "end": rows["timestamp"].max(),
                    })
                    break
    return hits

def detect_smurfing(df, min_senders=5, window_days=3, min_total_usd=20000,
                    max_sender_reuse=2):
    from tools.currency import threshold_for, NO_THRESHOLD, to_usd
    out = []
    d = to_usd(df)

    for currency, cur_df in d.groupby("currency"):
        if currency in NO_THRESHOLD:
            continue
        threshold = threshold_for(currency)
        if threshold is None:
            continue

        sub = cur_df[cur_df["amount"] < threshold].copy()
        sub["window"] = sub["timestamp"].dt.floor(f"{window_days}D")

        for (receiver, win), grp in sub.groupby(["receiver", "window"]):
            senders = grp["sender"].nunique()
            if senders < min_senders:
                continue
            total_usd = grp["amount_usd"].sum()
            if total_usd < min_total_usd:
                continue
            # each sender contributing only once or twice = distributed deposit
            if grp.groupby("sender").size().mean() > max_sender_reuse:
                continue

            out.append({
                "account": receiver,
                "typology": "smurfing",
                "tx_ids": grp["tx_id"].tolist(),
                "count": int(len(grp)),
                "unique_senders": int(senders),
                "total": float(grp["amount"].sum()),
                "total_usd": float(total_usd),
                "currency": currency,
            })
    return out

def detect_velocity(df, window_hours=24, min_burst=8, sigma_mult=4.0):
    """Flag accounts with an abnormal transaction burst in a short window."""
    d = df.sort_values("timestamp")
    hits = []

    for account, grp in d.groupby("sender"):
        if len(grp) < min_burst:
            continue
        times = grp["timestamp"].values
        window = pd.Timedelta(hours=window_hours).to_timedelta64()

        best = 0
        best_slice = None
        for i in range(len(times)):
            j = times.searchsorted(times[i] + window, side="right")
            if j - i > best:
                best = j - i
                best_slice = grp.iloc[i:j]

        if best >= min_burst:
            hits.append({
                "account": account,
                "typology": "velocity",
                "tx_ids": best_slice["tx_id"].tolist(),
                "velocity": float(best),
                "baseline": float(len(grp) / max(
                    (grp["timestamp"].max() - grp["timestamp"].min()).days, 1)),
                "window_hours": window_hours,
                "count": int(best),
            })
    return hits

def detect_rapid_cashout(df, max_gap_hours=24):
    pairs = rapid_cashout(df, max_gap_hours=max_gap_hours)
    out = []
    for account, grp in pairs.groupby("account"):
        out.append({
            "account": account,
            "typology": "rapid_cashout",
            "tx_ids": grp["in_tx"].tolist() + grp["out_tx"].tolist(),
            "events": int(len(grp)),
            "in_amount": float(grp["in_amount"].sum()),
            "out_amount": float(grp["out_amount"].sum()),
            "gap_hours": round(float(grp["gap_hours"].mean()), 1),
            "count": int(len(grp) * 2),
        })
    return out