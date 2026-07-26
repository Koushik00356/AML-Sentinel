"""Constrained analytical query spec. The LLM fills it; pandas executes it."""
from __future__ import annotations

import json
import os
import pandas as pd

ALLOWED_COLUMNS = {"timestamp", "tx_id", "sender", "receiver",
                   "amount", "amount_usd", "currency", "tx_type",
                   "is_laundering"}
ALLOWED_AGGS = {"count", "sum", "mean", "median", "min", "max", "nunique"}
ALLOWED_OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "contains"}

SPEC_PROMPT = """Translate the analyst's question into a JSON query spec.
Return JSON only, no prose, no markdown fences.

Available columns: timestamp, tx_id, sender, receiver, amount, amount_usd,
currency, tx_type, is_laundering

IMPORTANT — 'timestamp' is a datetime, not a number. The dataset covers
%(start)s to %(end)s. For a specific date use two filters with ISO strings:
  {"column":"timestamp","op":">=","value":"2022-09-10"}
  {"column":"timestamp","op":"<","value":"2022-09-11"}
"day 10" means the 10th day of that month. Never compare timestamp to a bare integer.

'tx_type' values include: Cheque, Credit Card, ACH, Cash, Reinvestment, Wire, Bitcoin.
'sender' and 'receiver' are account IDs — to rank accounts group by 'sender' alone.

Spec format:
{
  "filters": [{"column": str, "op": "==|!=|>|>=|<|<=|in|contains", "value": any}],
  "group_by": [column, ...],
  "aggregations": [{"column": str, "agg": "count|sum|mean|median|min|max|nunique",
                    "alias": str}],
  "sort_by": str or null,
  "ascending": bool,
  "limit": int,
  "answer_template": str
}

If it cannot be answered from these columns, return
{"unsupported": true, "reason": "<short reason>"}

Question: %(question)s"""


def request_spec(question: str, date_range: tuple | None = None) -> dict | None:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None

    start, end = date_range or ("2022-09-01", "2022-09-18")
    prompt = SPEC_PROMPT % {"question": question, "start": start, "end": end}
    
    
    try:
        import requests
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user",
                                "content": SPEC_PROMPT % question}],
                  "temperature": 0,
                  "response_format": {"type": "json_object"}},
            timeout=12)
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


def validate(spec: dict) -> tuple[bool, str]:
    if spec.get("unsupported"):
        return False, spec.get("reason", "not answerable from this data")

    for f in spec.get("filters", []):
        if f.get("column") not in ALLOWED_COLUMNS:
            return False, f"unknown column '{f.get('column')}'"
        if f.get("op") not in ALLOWED_OPS:
            return False, f"unsupported operator '{f.get('op')}'"

    for c in spec.get("group_by", []):
        if c not in ALLOWED_COLUMNS:
            return False, f"unknown column '{c}'"

    aggs = spec.get("aggregations", [])
    if not aggs:
        return False, "no aggregation requested"
    for a in aggs:
        if a.get("column") not in ALLOWED_COLUMNS:
            return False, f"unknown column '{a.get('column')}'"
        if a.get("agg") not in ALLOWED_AGGS:
            return False, f"unsupported aggregation '{a.get('agg')}'"

    return True, ""


def execute(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame | float, str]:
    d = df
    applied = []

    for f in spec.get("filters", []):
        col, op, val = f["column"], f["op"], f["value"]

        if col not in d.columns:
            continue

        if col == "timestamp":
            if isinstance(val, (int, float)):
                # "day 10" arrived as a number — resolve to that day of the month
                base = d["timestamp"].min()
                try:
                    val = pd.Timestamp(year=base.year, month=base.month,
                                       day=int(val))
                except ValueError:
                    continue
                if op == "==":
                    d = d[d["timestamp"].dt.date == val.date()]
                    applied.append(f"timestamp on {val:%Y-%m-%d}")
                    continue
            else:
                val = pd.Timestamp(val)
            if op == "==":
                d = d[d["timestamp"].dt.date == val.date()]
                applied.append(f"timestamp on {val:%Y-%m-%d}")
                continue    

        if op == "==":
            d = d[d[col] == val]
        elif op == "!=":
            d = d[d[col] != val]
        elif op == ">":
            d = d[d[col] > val]
        elif op == ">=":
            d = d[d[col] >= val]
        elif op == "<":
            d = d[d[col] < val]
        elif op == "<=":
            d = d[d[col] <= val]
        elif op == "in":
            d = d[d[col].isin(val if isinstance(val, list) else [val])]
        elif op == "contains":
            d = d[d[col].astype(str).str.contains(str(val), case=False, na=False)]
        applied.append(f"{col} {op} {val}")

    group_by = [c for c in spec.get("group_by", []) if c in d.columns]
    aggs = spec["aggregations"]

    if group_by:
        agg_map = {a["alias"]: (a["column"], a["agg"]) for a in aggs}
        out = d.groupby(group_by).agg(**agg_map).reset_index()
        sort_by = spec.get("sort_by")
        if sort_by in out.columns:
            out = out.sort_values(sort_by, ascending=spec.get("ascending", False))
        return out.head(min(int(spec.get("limit", 20)), 50)), "; ".join(applied)

    # scalar result
    a = aggs[0]
    series = d[a["column"]]
    value = {"count": series.count, "sum": series.sum, "mean": series.mean,
             "median": series.median, "min": series.min, "max": series.max,
             "nunique": series.nunique}[a["agg"]]()
    return float(value), "; ".join(applied)

def build_context(df: pd.DataFrame) -> str:
    """Compact factual summary of the data — schema, ranges, categories."""
    lines = [
        f"Rows: {len(df):,}",
        f"timestamp: datetime, {df['timestamp'].min():%Y-%m-%d} to "
        f"{df['timestamp'].max():%Y-%m-%d}",
        f"amount: numeric, median {df['amount'].median():,.0f}, "
        f"max {df['amount'].max():,.0f}",
        f"amount_usd: numeric, USD-normalised equivalent of amount",
        f"currency: categorical — {', '.join(df['currency'].value_counts().head(6).index)}",
        f"tx_type: categorical — {', '.join(df['tx_type'].value_counts().head(8).index)}",
        f"sender / receiver: account ID strings, "
        f"{pd.concat([df['sender'], df['receiver']]).nunique():,} unique",
        f"is_laundering: 0 or 1 label, {int((df['is_laundering']==1).sum()):,} positives",
    ]
    return "\n".join(lines)

## dda