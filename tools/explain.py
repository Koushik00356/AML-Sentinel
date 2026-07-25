from agent.schemas import RiskLevel

ACTION = {
    RiskLevel.HIGH.value: "report",
    RiskLevel.MEDIUM.value: "review",
    RiskLevel.LOW.value: "monitor",
}

ACTION_TEXT = {
    "report": "Escalate for Suspicious Activity Report filing.",
    "review": "Queue for analyst review within the standard SLA.",
    "monitor": "No immediate action; continue routine monitoring.",
}


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}"


def explain_hit(hit: dict) -> str:
    typ = hit.get("typology")

    if typ == "structuring":
        cur = hit.get("currency", "")
        return (
        f"{hit['count']} transactions totalling {_fmt(hit['total'])} {cur} "
        f"within {hit['window_days']} days, each individually below the "
        f"{_fmt(hit['threshold'])} {cur} reporting threshold. Splitting "
        f"amounts to stay under a reporting trigger is the defining "
        f"signature of structuring."
        )

    if typ == "smurfing":
        return (
            f"{hit['unique_senders']} distinct senders funnelled "
            f"{hit['count']} sub-threshold transactions totalling "
            f"{_fmt(hit['total'])} into this account. Distributing deposits "
            f"across multiple parties to disguise a single source is "
            f"characteristic of smurfing."
        )

    if typ == "velocity":
        return (
            f"Transaction rate of {hit['velocity']:.1f} per day against a "
            f"population baseline of {hit['baseline']:.1f} — roughly "
            f"{hit['velocity'] / max(hit['baseline'], 0.01):.0f}x normal "
            f"across {hit['count']} transactions. Sudden throughput spikes "
            f"often indicate an account being used as a conduit."
        )

    if typ == "rapid_cashout":
        return (
        f"{hit['events']} pass-through events: funds received and moved out "
        f"within an average of {hit['gap_hours']} hours, with outflow closely "
        f"matching inflow (total in {_fmt(hit['in_amount'])} USD-equivalent, "
        f"out {_fmt(hit['out_amount'])}). Funds transiting with no dwell time "
        f"is consistent with a funnel or pass-through account."
    )

    if typ == "layering":
        return (
            f"Funds traced through {hit.get('hops', 'multiple')} intermediate "
            f"accounts within {hit.get('span_hours', 'a short')} hours. "
            f"Chained transfers of this shape serve to obscure the origin "
            f"of funds."
        )

    if typ == "ml_anomaly":
        drivers = hit.get("top_features", [])
        driver_text = ", ".join(drivers) if drivers else "multiple features"
        return (
            f"Flagged by unsupervised anomaly detection (score "
            f"{hit.get('score', 0):.2f}); behaviour diverges from the account "
            f"population on {driver_text}. No named typology matched — this "
            f"is a novel pattern warranting analyst judgement."
        )

    

    if typ == "fan_in":
        return (f"{hit['sources']} distinct accounts sent {hit['count']} transactions "
                f"totalling {_fmt(hit['total_usd'])} USD-equivalent into this account "
                f"within {hit['window_days']} days. Convergent inflow from many unrelated "
                f"sources is a collection-point signature.")

    if typ == "fan_out":
        return (f"This account dispersed {_fmt(hit['total_usd'])} USD-equivalent across "
                f"{hit['targets']} recipients in {hit['count']} transactions over "
                f"{hit['window_days']} days. Rapid dispersal to many destinations is "
                f"characteristic of the distribution stage of laundering.")

    if typ == "cycle":
        return (f"Funds traced through a {hit['hops']}-account loop returning to the "
                f"origin within {hit['span_hours']} hours "
                f"({' → '.join(map(str, hit['cycle'][:4]))}...). Circular flows serve "
                f"no legitimate economic purpose and are used to fabricate transaction history.")

    if typ == "layering":
        return (f"{_fmt(hit['amount_usd'])} USD-equivalent traced through {hit['hops']} "
            f"successive accounts within {hit['span_hours']} hours, with each hop "
            f"retaining most of the value. Chained transfers of this shape obscure "
            f"the origin of funds.")

    return f"Flagged by {typ} detection."

    


def explain_account(row: dict, query: str | None = None) -> dict:
    reasons = [explain_hit(h) for h in row["hits"]]
    action = ACTION[row["risk"]]

    summary = (
        f"Account {row['account']} — {row['risk'].upper()} risk "
        f"(score {row['score']}). Detected: {row['typologies']}."
    )
    if query:
        summary = f"In response to: \"{query}\"\n{summary}"

    return {
        "account": row["account"],
        "risk": row["risk"],
        "score": row["score"],
        "summary": summary,
        "reasons": reasons,
        "action": action,
        "action_text": ACTION_TEXT[action],
    }