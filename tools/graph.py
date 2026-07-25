import networkx as nx
import pandas as pd
from tools.currency import to_usd


def build_edges(df: pd.DataFrame, min_amount_usd: float = 100) -> pd.DataFrame:
    """Collapse transactions into weighted account-to-account edges."""
    d = to_usd(df)
    d = d[d["amount_usd"] >= min_amount_usd]
    return (d.groupby(["sender", "receiver"])
              .agg(weight=("amount_usd", "sum"),
                   n_tx=("tx_id", "count"),
                   first=("timestamp", "min"),
                   last=("timestamp", "max"))
              .reset_index())


def detect_fan_in(df, min_sources=8, window_days=7, min_total_usd=10000):
    """Many accounts funnelling into one."""
    d = to_usd(df).copy()
    d["window"] = d["timestamp"].dt.floor(f"{window_days}D")
    g = (d.groupby(["receiver", "window"])
           .agg(sources=("sender", "nunique"),
                n_tx=("tx_id", "count"),
                total=("amount_usd", "sum"),
                tx_ids=("tx_id", list))
           .reset_index())
    g = g[(g["sources"] >= min_sources) & (g["total"] >= min_total_usd)]
    return [{
        "account": r["receiver"],
        "typology": "fan_in",
        "tx_ids": r["tx_ids"],
        "sources": int(r["sources"]),
        "count": int(r["n_tx"]),
        "total_usd": float(r["total"]),
        "window_days": window_days,
    } for _, r in g.iterrows()]


def detect_fan_out(df, min_targets=8, window_days=7, min_total_usd=10000):
    """One account dispersing to many."""
    d = to_usd(df).copy()
    d["window"] = d["timestamp"].dt.floor(f"{window_days}D")
    g = (d.groupby(["sender", "window"])
           .agg(targets=("receiver", "nunique"),
                n_tx=("tx_id", "count"),
                total=("amount_usd", "sum"),
                tx_ids=("tx_id", list))
           .reset_index())
    g = g[(g["targets"] >= min_targets) & (g["total"] >= min_total_usd)]
    return [{
        "account": r["sender"],
        "typology": "fan_out",
        "tx_ids": r["tx_ids"],
        "targets": int(r["targets"]),
        "count": int(r["n_tx"]),
        "total_usd": float(r["total"]),
        "window_days": window_days,
    } for _, r in g.iterrows()]


def detect_cycles(df, max_len=6, min_amount_usd=1000, max_nodes=60000):
    """Money returning to its origin through intermediaries."""
    edges = build_edges(df, min_amount_usd=min_amount_usd)

    # keep only accounts that both send and receive — cycles need both
    senders, receivers = set(edges["sender"]), set(edges["receiver"])
    both = senders & receivers
    edges = edges[edges["sender"].isin(both) & edges["receiver"].isin(both)]

    if edges["sender"].nunique() > max_nodes:
        top = (pd.concat([edges["sender"], edges["receiver"]])
                 .value_counts().head(max_nodes).index)
        edges = edges[edges["sender"].isin(top) & edges["receiver"].isin(top)]

    G = nx.DiGraph()
    for _, r in edges.iterrows():
        G.add_edge(r["sender"], r["receiver"],
                   weight=r["weight"], first=r["first"], last=r["last"])

    hits, seen = [], set()
    for cycle in nx.simple_cycles(G, length_bound=max_len):
        if len(cycle) < 3:
            continue
        key = frozenset(cycle)
        if key in seen:
            continue
        seen.add(key)

        pairs = list(zip(cycle, cycle[1:] + cycle[:1]))
        amounts = [G[a][b]["weight"] for a, b in pairs]
        times = [G[a][b]["first"] for a, b in pairs]
        span = (max(times) - min(times)).total_seconds() / 3600

        hits.append({
            "account": cycle[0],
            "typology": "cycle",
            "tx_ids": [],
            "cycle": cycle,
            "hops": len(cycle),
            "min_amount_usd": float(min(amounts)),
            "span_hours": round(span, 1),
            "count": len(cycle),
        })
    return hits


def detect_layering(df, min_hops=3, max_hops=5, min_amount_usd=5000,
                    max_gap_hours=72, retention=0.7):
    """Funds traced through a chain of intermediaries in a short window."""
    d = to_usd(df)
    d = d[d["amount_usd"] >= min_amount_usd].sort_values("timestamp")
    if d.empty:
        return []

    by_sender = {s: g for s, g in d.groupby("sender")}
    hits = []

    for _, seed in d.iterrows():
        chain = [(seed["sender"], seed["receiver"],
                  seed["amount_usd"], seed["timestamp"])]
        current, amount, t = seed["receiver"], seed["amount_usd"], seed["timestamp"]

        while len(chain) < max_hops:
            nxt = by_sender.get(current)
            if nxt is None:
                break
            window = nxt[
                (nxt["timestamp"] > t) &
                (nxt["timestamp"] <= t + pd.Timedelta(hours=max_gap_hours)) &
                (nxt["amount_usd"] >= amount * retention) &
                (nxt["amount_usd"] <= amount * 1.05)
            ]
            if window.empty:
                break
            step = window.iloc[0]
            if step["receiver"] in [c[0] for c in chain]:
                break
            chain.append((step["sender"], step["receiver"],
                          step["amount_usd"], step["timestamp"]))
            current, amount, t = step["receiver"], step["amount_usd"], step["timestamp"]

        if len(chain) >= min_hops:
            span = (chain[-1][3] - chain[0][3]).total_seconds() / 3600
            hits.append({
                "account": chain[0][0],
                "typology": "layering",
                "tx_ids": [],
                "hops": len(chain),
                "path": [c[0] for c in chain] + [chain[-1][1]],
                "amount_usd": float(chain[0][2]),
                "span_hours": round(span, 1),
                "count": len(chain),
            })
    return hits