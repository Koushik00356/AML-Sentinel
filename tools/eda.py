import pandas as pd
from tools.currency import to_usd


def profile(df: pd.DataFrame) -> dict:
    d = to_usd(df)
    span = (d["timestamp"].max() - d["timestamp"].min()).days or 1
    accounts = pd.concat([d["sender"], d["receiver"]]).nunique()

    return {
        "transactions": len(d),
        "accounts": accounts,
        "date_range": (d["timestamp"].min(), d["timestamp"].max()),
        "days": span,
        "total_usd": float(d["amount_usd"].sum()),
        "median_usd": float(d["amount_usd"].median()),
        "p99_usd": float(d["amount_usd"].quantile(0.99)),
        "currencies": d["currency"].value_counts().head(6).to_dict(),
        "tx_types": d["tx_type"].value_counts().to_dict(),
        "daily_volume": (d.set_index("timestamp")
                          .resample("D")["amount_usd"].sum()),
        "hourly": d["timestamp"].dt.hour.value_counts().sort_index(),
    }