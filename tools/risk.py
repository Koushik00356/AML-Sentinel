"""Convert detector hits into risk bands.

Confirmation is the primary signal: an account flagged by several independent
detectors is far more likely to be genuine than one flagged by a single weak
signal. Weighting by confirmation count is how alert noise is suppressed
without discarding recall.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from agent.schemas import RiskLevel

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "thresholds.json"

TYPOLOGY_WEIGHT = {
    "structuring": 0.40,
    "smurfing": 0.35,
    "layering": 0.40,
    "cycle": 0.45,
    "fan_in": 0.35,
    "fan_out": 0.35,
    "rapid_cashout": 0.30,
    "velocity": 0.20,
    "ml_anomaly": 0.25,
}

CONFIRMATION_MULTIPLIER = {1: 0.55, 2: 1.00, 3: 1.35, 4: 1.60}


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _evidence_strength(hit: dict) -> float:
    """0-1 scale of how far the evidence exceeds the detector's minimum."""
    typ = hit.get("typology")

    if typ == "structuring":
        return min(hit.get("count", 0) / 10.0, 1.0)
    if typ == "smurfing":
        return min(hit.get("unique_senders", 0) / 12.0, 1.0)
    if typ == "velocity":
        baseline = hit.get("baseline", 0) or 1
        return min(hit.get("velocity", 0) / (baseline * 5), 1.0)
    if typ == "rapid_cashout":
        return min(hit.get("events", 1) / 5.0, 1.0)
    if typ == "fan_in":
        return min(hit.get("sources", 0) / 20.0, 1.0)
    if typ == "fan_out":
        return min(hit.get("targets", 0) / 20.0, 1.0)
    if typ == "cycle":
        return min(hit.get("hops", 3) / 6.0, 1.0)
    if typ == "layering":
        return min(hit.get("hops", 3) / 5.0, 1.0)
    if typ == "ml_anomaly":
        return float(hit.get("score", 0.5))

    return 0.5


def score_hits(hits: list[dict], min_confirmations: int = 1) -> pd.DataFrame:
    """Aggregate detector hits into one scored row per account."""
    columns = ["account", "score", "risk", "typologies", "confirmations", "hits"]

    if not hits:
        return pd.DataFrame(columns=columns)

    by_account: dict[str, list[dict]] = {}
    for hit in hits:
        by_account.setdefault(str(hit["account"]), []).append(hit)

    bands = load_config()["risk_bands"]
    rows = []

    for account, account_hits in by_account.items():
        typologies = sorted({h["typology"] for h in account_hits})
        confirmations = len(typologies)

        if confirmations < min_confirmations:
            continue

        score = sum(
            TYPOLOGY_WEIGHT.get(h.get("typology"), 0.20) * _evidence_strength(h)
            for h in account_hits
        )
        score *= CONFIRMATION_MULTIPLIER.get(min(confirmations, 4), 1.60)
        score = round(min(score, 1.0), 3)

        if score >= bands["high"]:
            risk = RiskLevel.HIGH
        elif score >= bands["medium"]:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        rows.append({
            "account": account,
            "score": score,
            "risk": risk.value,
            "typologies": ", ".join(typologies),
            "confirmations": confirmations,
            "hits": account_hits,
        })

    if not rows:
        return pd.DataFrame(columns=columns)

    return (pd.DataFrame(rows)
            .sort_values(["score", "confirmations"], ascending=False)
            .reset_index(drop=True))