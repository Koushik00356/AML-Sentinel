import json
from pathlib import Path
import pandas as pd
from agent.schemas import RiskLevel

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "thresholds.json"

TYPOLOGY_WEIGHT = {
    "structuring": 0.40,
    "smurfing": 0.35,
    "layering": 0.40,
    "rapid_cashout": 0.30,
    "velocity": 0.20,
    "ml_anomaly": 0.25,
}


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8-sig") as f:
        _CFG = json.load(f)
    return _CFG


def _evidence_strength(hit: dict) -> float:
    """Scale 0-1 based on how far past the minimum the evidence goes."""
    typ = hit.get("typology")
    if typ == "structuring":
        return min(hit.get("count", 0) / 10.0, 1.0)
    if typ == "smurfing":
        return min(hit.get("unique_senders", 0) / 10.0, 1.0)
    if typ == "velocity":
        base = hit.get("baseline", 0) or 1
        return min(hit.get("velocity", 0) / (base * 5), 1.0)
    if typ == "rapid_cashout":
        gap = hit.get("gap_hours", 48)
        return max(0.0, 1.0 - gap / 48.0)
    return 0.5


def score_hits(hits: list[dict]) -> pd.DataFrame:
    """Aggregate detector hits into one risk row per account."""
    if not hits:
        return pd.DataFrame(columns=["account", "score", "risk",
                                     "typologies", "hits"])

    by_account: dict[str, list[dict]] = {}
    for h in hits:
        by_account.setdefault(str(h["account"]), []).append(h)

    cfg = load_config()["risk_bands"]
    rows = []

    for account, acct_hits in by_account.items():
        score = 0.0
        for h in acct_hits:
            w = TYPOLOGY_WEIGHT.get(h.get("typology"), 0.2)
            score += w * _evidence_strength(h)

        # multiple distinct typologies compound suspicion
        typologies = sorted({h["typology"] for h in acct_hits})
        if len(typologies) > 1:
            score *= 1.0 + 0.15 * (len(typologies) - 1)

        score = round(min(score, 1.0), 3)

        if score >= cfg["high"]:
            risk = RiskLevel.HIGH
        elif score >= cfg["medium"]:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        rows.append({
            "account": account,
            "score": score,
            "risk": risk.value,
            "typologies": ", ".join(typologies),
            "hits": acct_hits,
        })

    return (pd.DataFrame(rows)
            .sort_values("score", ascending=False)
            .reset_index(drop=True))