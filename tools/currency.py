import json
from pathlib import Path
import pandas as pd

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "thresholds.json"

with open(CONFIG_PATH) as f:
    _CFG = json.load(f)

FX = _CFG["fx_to_usd"]
CURRENCY_THRESHOLDS = _CFG["currency_thresholds"]
NO_THRESHOLD = set(_CFG["no_threshold_currencies"])
DEFAULT_USD = _CFG["default_threshold_usd"]


def to_usd(df: pd.DataFrame) -> pd.DataFrame:
    """Add amount_usd for cross-currency comparison."""
    out = df.copy()
    rates = out["currency"].map(FX).fillna(1.0)
    out["amount_usd"] = out["amount"] * rates
    out["fx_rate"] = rates
    return out


def threshold_for(currency: str) -> float | None:
    """Statutory reporting threshold in native currency. None if not applicable."""
    if currency in NO_THRESHOLD:
        return None
    if currency in CURRENCY_THRESHOLDS:
        return CURRENCY_THRESHOLDS[currency]
    rate = FX.get(currency, 1.0)
    return DEFAULT_USD / rate if rate else DEFAULT_USD


def threshold_series(df: pd.DataFrame) -> pd.Series:
    return df["currency"].map(threshold_for)