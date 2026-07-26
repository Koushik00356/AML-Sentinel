"""Executes a plan, recording what ran, what was skipped, and why."""

from __future__ import annotations

import json
import time

import pandas as pd

from agent.schemas import ExecutionPlan, IntentType, ToolCall
from tools import filters as F
from tools.anomaly import detect_ml_anomaly
from tools.eda import profile
from tools.explain import explain_account
from tools.graph import (detect_cycles, detect_fan_in, detect_fan_out,
                         detect_layering)
from tools.risk import score_hits
from tools.rules import (detect_rapid_cashout, detect_smurfing,
                         detect_structuring, detect_velocity)

DETECTORS = {
    "structuring": detect_structuring,
    "smurfing": detect_smurfing,
    "velocity": detect_velocity,
    "rapid_cashout": detect_rapid_cashout,
    "fan_in": detect_fan_in,
    "fan_out": detect_fan_out,
    "cycle": detect_cycles,
    "layering": detect_layering,
    "anomaly_ml": detect_ml_anomaly,
}

BROAD_SCAN_SAMPLE = 400_000
PATTERN_SEARCH_SAMPLE = 1_000_000


class Executor:
    def __init__(self, df: pd.DataFrame, on_step=None, memory=None,
                 min_confirmations: int = 1):
        self.full = df
        self.on_step = on_step
        self.memory = memory or []
        self.min_confirmations = min_confirmations

    # ------------------------------------------------------------------ #

    def _record(self, trace: list, call: ToolCall) -> ToolCall:
        trace.append(call)
        if self.on_step:
            self.on_step(call)
        return call

    def _base(self, plan, trace, **extra) -> dict:
        out = {
            "intent": plan.intent,
            "plan": plan,
            "trace": trace,
            "results": [],
            "eda": None,
            "scored": None,
            "all_hits": [],
            "aggregate": None,
            "message": None,
            "sampled": False,
            "filtered_df": self.full,
            "elapsed": 0.0,
        }
        out.update(extra)
        return out

    # ------------------------------------------------------------------ #

    def run(self, plan: ExecutionPlan) -> dict:
        intent = plan.intent
        trace: list[ToolCall] = []
        started = time.time()

        if "capability" in plan.steps:
            return self._capability(plan, trace)
        if "clarify" in plan.steps:
            return self._clarify(plan, trace)
        if "describe" in plan.steps:
            return self._describe(plan, trace)
        if "generic_query" in plan.steps:
            return self._generic(plan, trace)
        if "recall_flags" in plan.steps:
            return self._recall(plan, trace)

        df = self.full
        sampled = False

        if (intent.intent_type == IntentType.BROAD_SCAN
                and len(df) > BROAD_SCAN_SAMPLE):
            df = df.tail(BROAD_SCAN_SAMPLE)
            sampled = True
            self._record(trace, ToolCall(
                tool="budget_sample",
                reason=f"broad scan bounded to the most recent "
                       f"{BROAD_SCAN_SAMPLE:,} transactions for interactive latency",
                rows_in=len(self.full), rows_out=len(df)))

        elif (intent.intent_type == IntentType.PATTERN_SEARCH
                and len(df) > PATTERN_SEARCH_SAMPLE):
            df = df.tail(PATTERN_SEARCH_SAMPLE)
            sampled = True
            self._record(trace, ToolCall(
                tool="budget_sample",
                reason=f"pattern search bounded to the most recent "
                       f"{PATTERN_SEARCH_SAMPLE:,} transactions",
                rows_in=len(self.full), rows_out=len(df)))

        df = self._apply_filters(plan, df, trace)

        if df.empty:
            return self._base(plan, trace, filtered_df=df,
                              message="No transactions match those filters.",
                              sampled=sampled,
                              elapsed=round(time.time() - started, 2))

        eda_out = None
        hits: list[dict] = []

        for step in plan.steps:
            if step.startswith("filter_") or step in {"risk", "explain"}:
                continue

            t0 = time.time()

            if step == "eda":
                eda_out = profile(df)
                self._record(trace, ToolCall(
                    tool="eda", reason=plan.reasons.get("eda", ""),
                    rows_in=len(df), rows_out=0,
                    duration_ms=(time.time() - t0) * 1000))

            elif step == "features":
                self._record(trace, ToolCall(
                    tool="features", reason=plan.reasons.get("features", ""),
                    rows_in=len(df), rows_out=len(df),
                    duration_ms=(time.time() - t0) * 1000))

            elif step == "aggregate":
                agg = self._aggregate(df, intent)
                self._record(trace, ToolCall(
                    tool="aggregate", reason=plan.reasons.get("aggregate", ""),
                    rows_in=len(df), rows_out=len(agg),
                    duration_ms=(time.time() - t0) * 1000))
                return self._base(plan, trace, aggregate=agg, filtered_df=df,
                                  sampled=sampled,
                                  elapsed=round(time.time() - started, 2))

            elif step in DETECTORS:
                try:
                    found = DETECTORS[step](df)
                except Exception as exc:
                    found = []
                    self._record(trace, ToolCall(
                        tool=step, reason=f"failed: {exc}",
                        rows_in=len(df), rows_out=0,
                        duration_ms=(time.time() - t0) * 1000))
                    continue

                hits.extend(found)
                self._record(trace, ToolCall(
                    tool=step, reason=plan.reasons.get(step, ""),
                    rows_in=len(df), rows_out=len(found),
                    duration_ms=(time.time() - t0) * 1000))

        scored = score_hits(hits, min_confirmations=self.min_confirmations)
        results = [explain_account(row.to_dict(), query=intent.raw_query)
                   for _, row in scored.head(20).iterrows()]

        return self._base(plan, trace, results=results, eda=eda_out,
                          scored=scored, all_hits=hits, filtered_df=df,
                          sampled=sampled,
                          elapsed=round(time.time() - started, 2))

    # ------------------------------------------------------------------ #

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

            self._record(trace, ToolCall(
                tool=step, reason=plan.reasons.get(step, ""),
                rows_in=before, rows_out=len(df),
                duration_ms=(time.time() - t0) * 1000))

        return df

    def _aggregate(self, df, intent):
        f = intent.filters
        grouped = (df.groupby("sender")
                     .agg(transactions=("tx_id", "count"),
                          total=("amount", "sum"),
                          unique_counterparties=("receiver", "nunique"))
                     .reset_index()
                     .rename(columns={"sender": "account"}))

        if f.min_count:
            grouped = grouped[grouped["transactions"] >= f.min_count]

        return grouped.sort_values("transactions", ascending=False).head(50)

    # ------------------------------------------------------------------ #

    def _describe(self, plan, trace):
        d = self.full
        accounts = pd.concat([d["sender"], d["receiver"]]).nunique()
        span = (d["timestamp"].max() - d["timestamp"].min()).days
        currencies = d["currency"].value_counts().head(4)
        types = d["tx_type"].value_counts().head(4)

        lines = [
            f"**{len(d):,}** transactions across **{accounts:,}** accounts.",
            f"Covering **{span} days**, "
            f"{d['timestamp'].min():%Y-%m-%d} to {d['timestamp'].max():%Y-%m-%d}.",
            "",
            "**Currencies** — " + ", ".join(
                f"{c} ({n / len(d):.1%})" for c, n in currencies.items()),
            "**Payment types** — " + ", ".join(
                f"{t} ({n:,})" for t, n in types.items()),
        ]

        if "is_laundering" in d.columns:
            labelled = int((d["is_laundering"] == 1).sum())
            lines.append(f"**Labelled laundering** — {labelled:,} "
                         f"({labelled / len(d):.3%} of transactions)")

        self._record(trace, ToolCall(
            tool="describe",
            reason="factual question about the dataset; no detection required",
            rows_in=len(d), rows_out=1))

        return self._base(plan, trace, message="\n\n".join(lines))

    def _generic(self, plan, trace):
        from agent.query_spec import execute
        from tools.currency import to_usd

        note = next((n for n in plan.intent.notes if n.startswith("spec:")), None)
        if not note:
            return self._base(plan, trace,
                              message="I could not build a query plan for that.")

        spec = json.loads(note[5:])
        d = to_usd(self.full)

        t0 = time.time()
        try:
            result, applied = execute(d, spec)
        except Exception as exc:
            self._record(trace, ToolCall(
                tool="generic_query", reason=f"failed: {exc}",
                rows_in=len(d), rows_out=0))
            return self._base(plan, trace,
                              message=f"I could not compute that — {exc}")

        group_by = spec.get("group_by") or []
        reason = ("aggregation over "
                  + (", ".join(group_by) if group_by else "all rows"))
        if applied:
            reason += f"; filters: {applied}"

        self._record(trace, ToolCall(
            tool="generic_query", reason=reason, rows_in=len(d),
            rows_out=len(result) if hasattr(result, "__len__") else 1,
            duration_ms=(time.time() - t0) * 1000))

        if isinstance(result, (int, float)):
            value = (f"{result:,.0f}" if float(result).is_integer()
                     else f"{result:,.2f}")
            template = spec.get("answer_template") or "Result: {value}"
            try:
                message = template.format(value=value)
            except (KeyError, IndexError, ValueError):
                message = f"Result: {value}"
            return self._base(plan, trace, message=message,
                              elapsed=round(time.time() - t0, 2))

        return self._base(plan, trace, aggregate=result,
                          elapsed=round(time.time() - t0, 2))

    def _recall(self, plan, trace):
        ids = {str(x) for x in plan.intent.entity_ids}
        matched = [r for r in self.memory if not ids or str(r["account"]) in ids]

        self._record(trace, ToolCall(
            tool="recall_flags",
            reason="explanation drawn from existing flags; no re-analysis",
            rows_in=len(self.memory), rows_out=len(matched)))

        if not matched:
            return self._base(plan, trace,
                              message="No prior flags to explain. "
                                      "Run an analysis first.")

        return self._base(plan, trace, results=matched)

    def _capability(self, plan, trace):
        return self._base(plan, trace, message=(
            "I investigate transaction data for money-laundering typologies.\n\n"
            "**Detectors** — structuring, smurfing, velocity bursts, rapid "
            "cash-out, fan-in, fan-out, cycles, layering chains, and an "
            "unsupervised anomaly layer for novel patterns.\n\n"
            "**Filters I understand** — time windows (\"last 3 days\"), amount "
            "bands (\"over $50,000\"), currencies, account IDs, transaction counts.\n\n"
            "**Examples**\n"
            "- Find structuring patterns in the last 3 days\n"
            "- Which customers made 10+ transactions under $10,000?\n"
            "- Is customer 80004B890 suspicious?\n"
            "- Show me circular flows over $50,000\n"
            "- Top 10 accounts by total volume"))

    def _clarify(self, plan, trace):
        intent = plan.intent

        out_of_scope = next(
            (n[14:] for n in intent.notes if n.startswith("out of scope:")), None)
        if out_of_scope:
            return self._base(plan, trace, message=(
                f"That is outside what I can answer — {out_of_scope}. "
                f"I work only from the transaction dataset loaded here."))

        detected = []
        if intent.filters.days_back:
            detected.append(f"a {intent.filters.days_back}-day window")
        if intent.entity_ids:
            detected.append(f"account(s) {', '.join(intent.entity_ids)}")
        if intent.filters.max_amount:
            detected.append(f"amounts under {intent.filters.max_amount:,.0f}")

        message = "I could not determine what analysis you need."
        if detected:
            message += f" I did pick up {', and '.join(detected)}."
        message += ("\n\nTry naming a typology (structuring, smurfing, layering, "
                    "fan-in, cycles), asking about a specific account, or say "
                    "\"analyse this dataset for suspicious activity\".")

        return self._base(plan, trace, message=message)