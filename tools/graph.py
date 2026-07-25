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


def detect_layering(df, min_hops=3, max_hops=5, min_amount_usd=10000,
                    max_gap_hours=72, retention=0.7, max_seeds=50000):
    """Follow value through successive accounts using vectorised self-joins."""
    d = to_usd(df)
    d = d[d["amount_usd"] >= min_amount_usd][
        ["tx_id", "sender", "receiver", "amount_usd", "timestamp"]
    ].sort_values("amount_usd", ascending=False).head(max_seeds)

    if d.empty:
        return []

    chains = d.rename(columns={
        "sender": "origin", "receiver": "current",
        "amount_usd": "amount", "timestamp": "t",
    }).copy()
    chains["hops"] = 1
    chains["t0"] = chains["t"]
    chains["path"] = [[o, c] for o, c in zip(chains["origin"], chains["current"])]

    completed = []

    for _ in range(max_hops - 1):
        if chains.empty:
            break

        nxt = chains.merge(
            d, left_on="current", right_on="sender",
            suffixes=("", "_n"),
        )
        if nxt.empty:
            completed.append(chains)
            break

        gap = (nxt["timestamp"] - nxt["t"]).dt.total_seconds() / 3600
        valid = (
            (gap > 0) & (gap <= max_gap_hours)
            & (nxt["amount_usd"] >= nxt["amount"] * retention)
            & (nxt["amount_usd"] <= nxt["amount"] * 1.05)
        )
        nxt = nxt[valid]

        # drop revisits
        keep = [rec not in p for rec, p in zip(nxt["receiver"], nxt["path"])]
        nxt = nxt[keep]

        extended_ids = set(nxt["tx_id"])
        stalled = chains[~chains["tx_id"].isin(extended_ids)]
        if not stalled.empty:
            completed.append(stalled)

        if nxt.empty:
            break

        # keep one continuation per chain
        nxt = nxt.sort_values("timestamp").groupby("tx_id", as_index=False).first()

        chains = pd.DataFrame({
            "tx_id": nxt["tx_id"],
            "origin": nxt["origin"],
            "current": nxt["receiver"],
            "amount": nxt["amount_usd"],
            "t": nxt["timestamp"],
            "t0": nxt["t0"],
            "hops": nxt["hops"] + 1,
            "path": [p + [r] for p, r in zip(nxt["path"], nxt["receiver"])],
        })

    if not chains.empty:
        completed.append(chains)
    if not completed:
        return []

    final = pd.concat(completed, ignore_index=True)
    final = final[final["hops"] >= min_hops]

    return [{
        "account": r["origin"],
        "typology": "layering",
        "tx_ids": [r["tx_id"]],
        "hops": int(r["hops"]),
        "path": r["path"],
        "amount_usd": float(r["amount"]),
        "span_hours": round((r["t"] - r["t0"]).total_seconds() / 3600, 1),
        "count": int(r["hops"]),
    } for _, r in final.iterrows()]