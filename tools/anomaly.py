"""Unsupervised anomaly detection.

Rules and graph traversal encode typologies we already know about. This layer
catches accounts whose behaviour diverges from the population without matching
any named pattern — the novel cases a rule engine structurally cannot see.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from tools.features import account_features

FEATURE_COLUMNS = [
    "out_count",
    "in_count",
    "total_sent",
    "mean_amount",
    "max_amount",
    "unique_receivers",
    "unique_senders",
    "velocity",
    "near_threshold_ratio",
    "round_amount_count",
    "flow_ratio",
]

FRIENDLY = {
    "out_count": "outgoing transaction count",
    "in_count": "incoming transaction count",
    "total_sent": "total value sent",
    "mean_amount": "average transaction size",
    "max_amount": "largest single transaction",
    "unique_receivers": "number of distinct recipients",
    "unique_senders": "number of distinct senders",
    "velocity": "transaction rate",
    "near_threshold_ratio": "share of near-threshold amounts",
    "round_amount_count": "count of round-number amounts",
    "flow_ratio": "outflow to inflow ratio",
}


def _top_drivers(row: pd.Series, medians: pd.Series, n: int = 3) -> list[str]:
    """Which features deviate most from the population median."""
    deviations = {}
    for col in FEATURE_COLUMNS:
        med = medians.get(col, 0)
        val = row.get(col, 0)
        if pd.isna(val):
            continue
        scale = abs(med) if abs(med) > 1e-9 else 1.0
        deviations[col] = abs(val - med) / scale

    ranked = sorted(deviations.items(), key=lambda kv: kv[1], reverse=True)
    return [FRIENDLY.get(col, col) for col, _ in ranked[:n]]


def detect_ml_anomaly(df: pd.DataFrame,
                      contamination: float = 0.01,
                      min_activity: int = 3,
                      max_accounts: int = 200_000,
                      random_state: int = 42) -> list[dict]:
    """Score accounts with IsolationForest and return the anomalous ones."""
    acct = account_features(df)
    acct = acct[acct["out_count"] >= min_activity]

    if len(acct) < 50:
        return []

    if len(acct) > max_accounts:
        acct = acct.nlargest(max_accounts, "out_count")

    matrix = acct.reindex(columns=FEATURE_COLUMNS).astype(float)
    matrix = matrix.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    scaled = StandardScaler().fit_transform(matrix)

    model = IsolationForest(
        n_estimators=120,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    labels = model.fit_predict(scaled)
    raw_scores = model.score_samples(scaled)

    # score_samples: lower is more anomalous. Map to 0-1 where 1 = most anomalous.
    lo, hi = raw_scores.min(), raw_scores.max()
    span = (hi - lo) or 1.0
    normalised = 1.0 - (raw_scores - lo) / span

    acct = acct.assign(anomaly_score=normalised, is_outlier=labels == -1)
    outliers = acct[acct["is_outlier"]]

    medians = matrix.median()

    hits = []
    for account, row in outliers.iterrows():
        hits.append({
            "account": str(account),
            "typology": "ml_anomaly",
            "tx_ids": [],
            "score": round(float(row["anomaly_score"]), 3),
            "top_features": _top_drivers(row, medians),
            "count": int(row["out_count"]),
        })

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits