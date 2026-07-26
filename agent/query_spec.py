"""Constrained analytical query spec. The LLM fills it; pandas executes it.

The model never sees transaction rows — only the schema, column types and
category values. It proposes a spec; this module validates it against an
allowlist and executes it deterministically with pandas.
"""

from __future__ import annotations

import json
import os

import pandas as pd

ALLOWED_COLUMNS = {"timestamp", "tx_id", "sender", "receiver",
                   "amount", "amount_usd", "currency", "tx_type",
                   "is_laundering"}
ALLOWED_AGGS = {"count", "sum", "mean", "median", "min", "max", "nunique"}
ALLOWED_OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "contains"}

MODEL = "llama-3.3-70b-versatile"
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

SPEC_PROMPT = """Translate the analyst's question into a JSON query spec.
Return JSON only, no prose, no markdown fences.

DATASET FACTS (use these exact category values, never invent others):
%(context)s

Available columns: timestamp, tx_id, sender, receiver, amount, amount_usd,
currency, tx_type, is_laundering

IMPORTANT — 'timestamp' is a datetime, not a number. For a specific date use
two filters with ISO date strings:
  {"column": "timestamp", "op": ">=", "value": "2022-09-10"}
  {"column": "timestamp", "op": "<",  "value": "2022-09-11"}
"day 10" means the 10th day of the month covered by the data.
Never compare timestamp to a bare integer.

'sender' and 'receiver' are account ID strings. To rank accounts, group by
'sender' alone unless the question is explicitly about counterparty pairs.

Use 'amount_usd' when comparing values across different currencies.

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

'answer_template' is one sentence containing {value} for a scalar result.
'sort_by' must be an alias from 'aggregations'.

If the question cannot be answered from these columns, return
{"unsupported": true, "reason": "<short reason>"}

Question: %(question)s"""


def build_context(df: pd.DataFrame) -> str:
    """Compact factual summary of the data — schema, ranges, categories."""
    accounts = pd.concat([df["sender"], df["receiver"]]).nunique()
    lines = [
        f"Rows: {len(df):,}",
        f"timestamp: datetime, {df['timestamp'].min():%Y-%m-%d} to "
        f"{df['timestamp'].max():%Y-%m-%d}",
        f"amount: numeric, median {df['amount'].median():,.0f}, "
        f"max {df['amount'].max():,.0f}",
        "amount_usd: numeric, USD-normalised equivalent of amount",
        "currency: categorical — "
        + ", ".join(df["currency"].value_counts().head(6).index.astype(str)),
        "tx_type: categorical — "
        + ", ".join(df["tx_type"].value_counts().head(8).index.astype(str)),
        f"sender / receiver: account ID strings, {accounts:,} unique",
    ]
    if "is_laundering" in df.columns:
        lines.append(f"is_laundering: 0 or 1 label, "
                     f"{int((df['is_laundering'] == 1).sum()):,} positives")
    return "\n".join(lines)


def request_spec(question: str, context: str = "", debug: bool = False):
    """Ask the LLM for a query spec. Returns None if unavailable or malformed."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None

    prompt = SPEC_PROMPT % {
        "question": question,
        "context": context or "No additional context available.",
    }

    try:
        import requests

        response = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=12,
        )
        payload = response.json()

        if "choices" not in payload:
            if debug:
                print("SPEC API ERROR:", payload)
            return None

        content = payload["choices"][0]["message"]["content"].strip()
        content = (content
                   .removeprefix("```json")
                   .removeprefix("```")
                   .removesuffix("```")
                   .strip())
        return json.loads(content)

    except Exception as exc:
        if debug:
            print("SPEC ERROR:", repr(exc))
        return None


def validate(spec: dict) -> tuple[bool, str]:
    """Check a spec against the allowlist before it is allowed near the data."""
    if not isinstance(spec, dict):
        return False, "spec is not an object"

    if spec.get("unsupported"):
        return False, spec.get("reason", "not answerable from this data")

    for f in spec.get("filters", []) or []:
        if f.get("column") not in ALLOWED_COLUMNS:
            return False, f"unknown column '{f.get('column')}'"
        if f.get("op") not in ALLOWED_OPS:
            return False, f"unsupported operator '{f.get('op')}'"

    for col in spec.get("group_by", []) or []:
        if col not in ALLOWED_COLUMNS:
            return False, f"unknown column '{col}'"

    aggs = spec.get("aggregations") or []
    if not aggs:
        return False, "no aggregation requested"

    for a in aggs:
        if a.get("column") not in ALLOWED_COLUMNS:
            return False, f"unknown column '{a.get('column')}'"
        if a.get("agg") not in ALLOWED_AGGS:
            return False, f"unsupported aggregation '{a.get('agg')}'"
        if not a.get("alias"):
            a["alias"] = f"{a['agg']}_{a['column']}"

    return True, ""


def _apply_timestamp_filter(d: pd.DataFrame, op: str, val):
    """Handle timestamp filters, coercing bare integers to a day of the month."""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        base = d["timestamp"].min()
        try:
            val = pd.Timestamp(year=base.year, month=base.month, day=int(val))
        except (ValueError, AttributeError):
            return d, None
    else:
        try:
            val = pd.Timestamp(val)
        except (ValueError, TypeError):
            return d, None

    if op == "==":
        return d[d["timestamp"].dt.date == val.date()], f"timestamp on {val:%Y-%m-%d}"
    if op == ">=":
        return d[d["timestamp"] >= val], f"timestamp >= {val:%Y-%m-%d}"
    if op == ">":
        return d[d["timestamp"] > val], f"timestamp > {val:%Y-%m-%d}"
    if op == "<=":
        return d[d["timestamp"] <= val], f"timestamp <= {val:%Y-%m-%d}"
    if op == "<":
        return d[d["timestamp"] < val], f"timestamp < {val:%Y-%m-%d}"
    if op == "!=":
        return d[d["timestamp"].dt.date != val.date()], f"timestamp not {val:%Y-%m-%d}"

    return d, None


def execute(df: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame | float, str]:
    """Run a validated spec against the data. Returns (result, filters applied)."""
    d = df
    applied: list[str] = []

    for f in spec.get("filters", []) or []:
        col, op, val = f["column"], f["op"], f["value"]

        if col not in d.columns:
            continue

        if col == "timestamp":
            d, note = _apply_timestamp_filter(d, op, val)
            if note:
                applied.append(note)
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

    group_by = [c for c in (spec.get("group_by") or []) if c in d.columns]
    aggs = spec["aggregations"]

    if group_by:
        agg_map = {a["alias"]: (a["column"], a["agg"]) for a in aggs}
        out = d.groupby(group_by).agg(**agg_map).reset_index()

        sort_by = spec.get("sort_by")
        if sort_by in out.columns:
            out = out.sort_values(sort_by,
                                  ascending=bool(spec.get("ascending", False)))

        limit = min(int(spec.get("limit", 20) or 20), 50)
        return out.head(limit), "; ".join(applied)

    agg = aggs[0]
    series = d[agg["column"]]
    value = {
        "count": series.count,
        "sum": series.sum,
        "mean": series.mean,
        "median": series.median,
        "min": series.min,
        "max": series.max,
        "nunique": series.nunique,
    }[agg["agg"]]()

    return float(value), "; ".join(applied)