"""Executes a plan, recording what ran, what was skipped, and why."""
from __future__ import annotations

import time
import pandas as pd

from agent.schemas import Intent, IntentType, ExecutionPlan, ToolCall
from tools import filters as F
from tools.rules import (detect_structuring, detect_smurfing,
                         detect_velocity, detect_rapid_cashout)
from tools.graph import (detect_fan_in, detect_fan_out,
                         detect_cycles, detect_layering)
from tools.risk import score_hits
from tools.explain import explain_account
from tools.eda import profile

DETECTORS = {
    "structuring": detect_structuring,
    "smurfing": detect_smurfing,
    "velocity": detect_velocity,
    "rapid_cashout": detect_rapid_cashout,
    "fan_in": detect_fan_in,
    "fan_out": detect_fan_out,
    "cycle": detect_cycles,
    "layering": detect_layering,
}

BROAD_SCAN_SAMPLE = 400_000


class Executor:
    def __init__(self, df, on_step=None, memory=None):
        self.full = df
        self.on_step = on_step
        self.memory = memory or []

    def _record(self, trace, call):
        trace.append(call)
        if self.on_step:
            self.on_step(call)
        return call

    def run(self, plan: ExecutionPlan) -> dict:
        intent = plan.intent
        trace: list[ToolCall] = []
        t_start = time.time()

        if "capability" in plan.steps:
            return self._capability(plan, trace)
        if "clarify" in plan.steps:
            return self._clarify(plan, trace)

        df = self.full
        sampled = False

        # budget: broad scans run on a recent slice, not the full corpus
        if intent.intent_type == IntentType.BROAD_SCAN and len(df) > BROAD_SCAN_SAMPLE:
            df = df.tail(BROAD_SCAN_SAMPLE)
            sampled = True
            self._record(trace, ToolCall(
                tool="budget_sample",
                reason=f"broad scan bounded to most recent {BROAD_SCAN_SAMPLE:,} "
                       f"transactions for interactive latency",
                rows_in=len(self.full), rows_out=len(df)))

        df = self._apply_filters(plan, df, trace)

        if df.empty:
            return {"intent": intent, "plan": plan, "trace": trace,
                    "results": [], "eda": None, "elapsed": 0,
                    "message": "No transactions match those filters."}

        eda_out = None
        hits: list[dict] = []

        for step in plan.steps:
            if step.startswith("filter_") or step in {"risk", "explain"}:
                continue

            t0 = time.time()

            if step == "eda":
                eda_out = profile(df)
                self._record(trace, ToolCall(tool="eda",
                                      reason=plan.reasons.get("eda", ""),
                                      rows_in=len(df), rows_out=0,
                                      duration_ms=(time.time() - t0) * 1000))

            elif step == "features":
                self._record(trace, ToolCall(tool="features",
                                      reason=plan.reasons.get("features", ""),
                                      rows_in=len(df), rows_out=len(df),
                                      duration_ms=(time.time() - t0) * 1000))

            elif step == "aggregate":
                agg = self._aggregate(df, intent)
                self._record(trace, ToolCall(tool="aggregate",
                                      reason=plan.reasons.get("aggregate", ""),
                                      rows_in=len(df), rows_out=len(agg),
                                      duration_ms=(time.time() - t0) * 1000))
                return {"intent": intent, "plan": plan, "trace": trace,
                        "results": [], "aggregate": agg, "eda": None,
                        "sampled": sampled,
                        "elapsed": round(time.time() - t_start, 2)}

            elif step in DETECTORS:
                found = DETECTORS[step](df)
                hits.extend(found)
                self._record(trace, ToolCall(tool=step,
                                      reason=plan.reasons.get(step, ""),
                                      rows_in=len(df), rows_out=len(found),
                                      duration_ms=(time.time() - t0) * 1000))

        scored = score_hits(hits)
        results = [explain_account(r.to_dict(), query=intent.raw_query)
                   for _, r in scored.head(20).iterrows()]

        return {"intent": intent, "plan": plan, "trace": trace,
                "results": results, "eda": eda_out, "sampled": sampled,
                "scored": scored, "all_hits": hits, "filtered_df": df,
                "elapsed": round(time.time() - t_start, 2)}

    def _apply_filters(self, plan, df, trace):
        f = plan.intent.filters
        for step in plan.steps:
            if not step.startswith("filter_"):
                continue
            before = len(df)
            t0 = time.time()

            if step == "filter_date":
                df = F.filter_by_date(df, start=f.start_date, end=f.end_date,
                                      days_back=f.days_back)
            elif step == "filter_entities":
                df = F.filter_by_entities(df, plan.intent.entity_ids)
            elif step == "filter_amount":
                df = F.filter_by_amount(df, min_amount=f.min_amount,
                                        max_amount=f.max_amount)
            elif step == "filter_currency":
                df = F.filter_by_currency(df, [f.currency], verbose=False)

            self._record(trace, ToolCall(tool=step,
                                  reason=plan.reasons.get(step, ""),
                                  rows_in=before, rows_out=len(df),
                                  duration_ms=(time.time() - t0) * 1000))
        return df

    def _aggregate(self, df, intent):
        f = intent.filters
        g = (df.groupby("sender")
               .agg(transactions=("tx_id", "count"),
                    total=("amount", "sum"),
                    unique_counterparties=("receiver", "nunique"))
               .reset_index()
               .rename(columns={"sender": "account"}))
        if f.min_count:
            g = g[g["transactions"] >= f.min_count]
        return g.sort_values("transactions", ascending=False).head(50)

    def _capability(self, plan, trace):
        return {"intent": plan.intent, "plan": plan, "trace": trace,
                "results": [], "eda": None, "elapsed": 0,
                "message": (
                    "I can investigate transaction data for money-laundering "
                    "typologies.\n\n"
                    "Detectors: structuring, smurfing, velocity bursts, rapid "
                    "cash-out, fan-in, fan-out, cycles, layering chains.\n\n"
                    "Filters I understand: time windows (\"last 30 days\"), "
                    "amount bands (\"over $50,000\"), currencies, specific "
                    "account IDs, transaction counts.\n\n"
                    "Examples:\n"
                    "  Find structuring patterns in the last 30 days\n"
                    "  Which customers made 10+ transactions under $10,000?\n"
                    "  Is customer 8000EBD30 suspicious?\n"
                    "  Show me circular flows over $50,000")}

    def _clarify(self, plan, trace):
        i = plan.intent
        detected = []
        if i.filters.days_back:
            detected.append(f"a {i.filters.days_back}-day window")
        if i.entity_ids:
            detected.append(f"account(s) {', '.join(i.entity_ids)}")
        if i.filters.max_amount:
            detected.append(f"amounts under {i.filters.max_amount:,.0f}")

        msg = "I couldn't determine what analysis you need."
        if detected:
            msg += f" I did pick up {', and '.join(detected)}."
        msg += ("\n\nTry naming a typology (structuring, smurfing, layering, "
                "fan-in, cycles), asking about a specific account, or say "
                "\"analyse this dataset for suspicious activity\".")

        return {"intent": i, "plan": plan, "trace": trace, "results": [],
                "eda": None, "elapsed": 0, "message": msg}