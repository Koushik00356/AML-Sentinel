"""Builds a query-specific execution plan. This is the routing layer."""
from __future__ import annotations

from agent.schemas import Intent, IntentType, Typology, ExecutionPlan

ALL_TOOLS = ["eda", "features", "structuring", "smurfing", "velocity",
             "rapid_cashout", "fan_in", "fan_out", "cycle", "layering",
             "anomaly_ml", "risk", "explain"]

TYPOLOGY_TOOL = {
    Typology.STRUCTURING: "structuring",
    Typology.SMURFING: "smurfing",
    Typology.LAYERING: "layering",
    Typology.RAPID_CASHOUT: "rapid_cashout",
    Typology.VELOCITY: "velocity",
}


def build_plan(intent: Intent) -> ExecutionPlan:
    plan = ExecutionPlan(intent=intent)
    steps: list[str] = []
    reasons: dict[str, str] = {}

    if intent.intent_type == IntentType.CAPABILITY:
        plan.steps = ["capability"]
        plan.skipped = [(t, "capability query needs no analysis")
                        for t in ALL_TOOLS]
        return plan

    # filters always precede analysis
    f = intent.filters
    if f.days_back or f.start_date or f.end_date:
        steps.append("filter_date")
        reasons["filter_date"] = "query specifies a time window"
    if intent.entity_ids:
        steps.append("filter_entities")
        reasons["filter_entities"] = f"query targets {len(intent.entity_ids)} account(s)"
    if f.min_amount is not None or f.max_amount is not None:
        steps.append("filter_amount")
        reasons["filter_amount"] = "query specifies an amount band"
    if f.currency:
        steps.append("filter_currency")
        reasons["filter_currency"] = f"query restricted to {f.currency}"

    graph_note = next((n.split(":")[1] for n in intent.notes
                       if n.startswith("graph_typology:")), None)

    if intent.intent_type == IntentType.ENTITY_LOOKUP:
        steps += ["features", "structuring", "smurfing", "rapid_cashout",
                  "fan_in", "fan_out"]
        reasons["features"] = "entity risk requires behavioural features"
        for t in ["structuring", "smurfing", "rapid_cashout", "fan_in", "fan_out"]:
            reasons[t] = "cheap detectors scoped to a single entity"
        plan.skipped += [
            ("eda", "single-entity query needs no population profiling"),
            ("cycle", "graph traversal disproportionate for one account"),
            ("layering", "graph traversal disproportionate for one account"),
            ("anomaly_ml", "population model not meaningful for one account"),
        ]

    elif intent.intent_type == IntentType.THRESHOLD_QUERY:
        steps.append("aggregate")
        reasons["aggregate"] = "explicit threshold answered by aggregation alone"
        plan.skipped += [
            ("eda", "direct question, no exploration needed"),
            ("anomaly_ml", "explicit criteria supplied; ML not required"),
        ] + [(t, "not required for a threshold query")
             for t in ["structuring", "smurfing", "velocity", "rapid_cashout",
                       "fan_in", "fan_out", "cycle", "layering"]]

    elif intent.intent_type == IntentType.PATTERN_SEARCH:
        if graph_note:
            steps += ["features", graph_note]
            reasons["features"] = "graph detection needs normalised amounts"
            reasons[graph_note] = f"query explicitly targets {graph_note}"
            plan.skipped += [(t, f"query targets {graph_note} only")
                             for t in ALL_TOOLS
                             if t not in {graph_note, "features", "risk", "explain"}]
        else:
            tool = TYPOLOGY_TOOL.get(intent.typology)
            if tool:
                steps += ["features", tool]
                reasons["features"] = "typology detection needs engineered features"
                reasons[tool] = f"query explicitly targets {intent.typology.value}"
                plan.skipped += [(t, f"query targets {intent.typology.value} only")
                                 for t in ALL_TOOLS
                                 if t not in {tool, "features", "risk", "explain"}]
            else:
                steps += ["features", "structuring", "smurfing", "rapid_cashout",
                          "fan_in", "fan_out"]
                reasons["features"] = "no specific typology named"
                plan.skipped += [
                    ("eda", "targeted search, not exploration"),
                    ("cycle", "expensive traversal reserved for explicit requests"),
                    ("layering", "expensive traversal reserved for explicit requests"),
                ]

    elif intent.intent_type == IntentType.BROAD_SCAN:
        steps += ["eda", "features", "structuring", "smurfing", "velocity",
                  "rapid_cashout", "fan_in", "fan_out", "anomaly_ml"]
        reasons["eda"] = "broad request warrants population profiling"
        reasons["anomaly_ml"] = "unsupervised layer catches unencoded patterns"
        plan.skipped += [
            ("cycle", "excluded from broad scan for runtime; request explicitly"),
            ("layering", "excluded from broad scan for runtime; request explicitly"),
        ]

    elif intent.intent_type == IntentType.EXPLAIN_FLAG:
        steps += ["recall_flags"]
        reasons["recall_flags"] = "explanation drawn from existing flags"
        plan.skipped += [(t, "no re-analysis needed to explain a prior flag")
                         for t in ALL_TOOLS if t not in {"explain"}]

    elif intent.intent_type == IntentType.DATA_SUMMARY:
        plan.steps = ["describe"]
        plan.reasons = {"describe": "factual question about the dataset; "
                                    "no detection required"}
        plan.skipped = [(t, "metadata question needs no analysis")
                        for t in ALL_TOOLS]
        return plan

    elif intent.intent_type == IntentType.GENERIC_ANALYSIS:
        plan.steps = ["generic_query"]
        plan.reasons = {"generic_query":
                        "question answered by direct aggregation over the data"}
        plan.skipped = [(t, "no typology detection required") for t in ALL_TOOLS]
        return plan

    else:
        plan.steps = ["clarify"]
        plan.skipped = [(t, "intent not recognised") for t in ALL_TOOLS]
        return plan

    steps += ["risk", "explain"]
    reasons["risk"] = "convert detector signals to risk bands"
    reasons["explain"] = "generate analyst-readable justification"

    plan.steps = steps
    plan.reasons = reasons
    return plan