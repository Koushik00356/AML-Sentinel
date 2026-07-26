import pandas as pd
from pathlib import Path

CANONICAL = ["timestamp", "tx_id", "sender", "receiver",
             "amount", "currency", "tx_type", "is_laundering"]

SCHEMA_MAPS = {
    "demo": {}, 
    "ibm_aml": {
        "Timestamp": "timestamp",
        "Account": "sender",
        "Account.1": "receiver",
        "Amount Paid": "amount",
        "Payment Currency": "currency",
        "Payment Format": "tx_type",
        "Is Laundering": "is_laundering",
    },
    "synthetic": {
        "ts": "timestamp",
        "tx_id": "tx_id",
        "from_acct": "sender",
        "to_acct": "receiver",
        "amount": "amount",
        "currency": "currency",
        "channel": "tx_type",
        "label": "is_laundering",
    },
}


def load(path: str | Path, schema: str = "ibm_aml",
         nrows: int | None = None) -> pd.DataFrame:
    if schema not in SCHEMA_MAPS:
        raise ValueError(f"unknown schema '{schema}'; "
                         f"available: {list(SCHEMA_MAPS)}")

    df = pd.read_csv(path, nrows=nrows)
    df = df.rename(columns=SCHEMA_MAPS[schema])

    if "tx_id" not in df.columns:
        df["tx_id"] = df.index.astype(str)

    for col in CANONICAL:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[CANONICAL].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["sender"] = df["sender"].astype(str)
    df["receiver"] = df["receiver"].astype(str)

    df = df.dropna(subset=["timestamp", "amount"])
    return df.sort_values("timestamp").reset_index(drop=True)

def _normalise(df: pd.DataFrame, schema: str) -> pd.DataFrame:
    if schema not in SCHEMA_MAPS:
        raise ValueError(f"unknown schema '{schema}'")
    df = df.rename(columns=SCHEMA_MAPS[schema])
    if "tx_id" not in df.columns:
        df["tx_id"] = df.index.astype(str)
    for col in CANONICAL:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[CANONICAL].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["sender"] = df["sender"].astype(str)
    df["receiver"] = df["receiver"].astype(str)
    df["is_laundering"] = pd.to_numeric(
        df["is_laundering"], errors="coerce").fillna(0).astype(int)
    return df.dropna(subset=["timestamp", "amount"]).sort_values(
        "timestamp").reset_index(drop=True)


def load(path, schema="ibm_aml", nrows=None):
        p = str(path)
        df = (pd.read_parquet(p) if p.endswith(".parquet")
            else pd.read_csv(p, nrows=nrows))
        return _normalise(df, schema)

def load_uploaded(file_obj, schema="demo", nrows=None):
    return _normalise(pd.read_csv(file_obj, nrows=nrows), schema)

