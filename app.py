"""AML Sentinel — agentic investigation assistant for AML analysts."""

import argparse
import io
import os
import sys
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent.executor import DETECTORS, Executor
from agent.intent_parser import parse
from agent.planner import build_plan
from agent.schemas import IntentType
from assets.style import CSS, EMPTY_STATE, case_card, funnel
from tools import viz
from tools.eda import profile
from tools.explain import explain_account
from tools.filters import filter_analyzable
from tools.loader import SCHEMA_MAPS, load, load_uploaded
from tools.risk import score_hits

load_dotenv()

st.set_page_config(page_title="AML Sentinel", page_icon="🛡",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)

EXAMPLES = [
    "what can you do?",
    "Is customer 80004B890 suspicious?",
    "Find structuring patterns in the last 3 days",
    "Which customers made 10+ transactions under $10,000?",
    "Show me circular flows over $50,000",
    "Top 10 accounts by total volume",
]

from pathlib import Path

PRESETS = {
    "Demo slice (250k, bundled)": ("data/sample/demo_transactions.csv", "demo"),
    "IBM HI-Small (high illicit rate)": ("data/raw/HI-Small_Trans.csv", "ibm_aml"),
    "IBM LI-Small (low illicit rate)": ("data/raw/LI-Small_Trans.csv", "ibm_aml"),
}
# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #

def cli_args():
    p = argparse.ArgumentParser(conflict_handler="resolve")
    p.add_argument("--data", default="data/sample/demo_transactions.csv")
    p.add_argument("--schema", default="demo")
    known, _ = p.parse_known_args(sys.argv[1:])
    return known


@st.cache_data(show_spinner="Loading transactions…")
def get_data(path: str, schema: str):
    df = load(path, schema=schema)
    df, hubs = filter_analyzable(df, verbose=False)
    return df, len(hubs)


@st.cache_data(show_spinner="Reading upload…")
def get_uploaded(raw: bytes, schema: str):
    df = load_uploaded(io.BytesIO(raw), schema=schema)
    df, hubs = filter_analyzable(df, verbose=False)
    return df, len(hubs)


@st.cache_data(show_spinner=False)
def data_context(_df: pd.DataFrame) -> str:
    from agent.query_spec import build_context
    return build_context(_df)


@st.cache_data(show_spinner="Running all detectors…")
def run_all_detectors(_df: pd.DataFrame, cache_key: str):
    hits, rows = [], []
    for name, fn in DETECTORS.items():
        t0 = time.time()
        try:
            found = fn(_df)
        except Exception as exc:
            found = []
            rows.append({"detector": name, "accounts": 0, "hits": 0,
                         "seconds": 0.0, "status": f"failed: {exc}"})
            continue
        hits.extend(found)
        rows.append({
            "detector": name,
            "accounts": len({str(h["account"]) for h in found}),
            "hits": len(found),
            "seconds": round(time.time() - t0, 1),
            "status": "ok",
        })
    return hits, pd.DataFrame(rows)


def init_state():
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("last_results", [])
    st.session_state.setdefault("query", "")


# --------------------------------------------------------------------------- #
# chrome
# --------------------------------------------------------------------------- #

def sidebar(args):
    with st.sidebar:
        st.markdown("<div class='eyebrow'>Mode</div>", unsafe_allow_html=True)
        if os.getenv("GROQ_API_KEY"):
            st.caption("LLM parsing active — free-form questions supported.")
        else:
            st.caption("Deterministic mode — no API key detected. All detection "
                       "works; free-form analytical questions need a key "
                       "(see README).")

        st.markdown("<div class='eyebrow'>Data</div>", unsafe_allow_html=True)
        source = st.radio("Source", ["Preset", "Local path", "Upload CSV"],
                          label_visibility="collapsed")

        path, schema, upload = args.data, args.schema, None

        if source == "Preset":
            choice = st.selectbox("Dataset", list(PRESETS.keys()),
                                  label_visibility="collapsed")
            path, schema = PRESETS[choice]
            if not Path(path).exists():
                st.caption("Not present locally — see README for download "
                           "instructions. Falling back to the bundled slice.")
                path, schema = PRESETS["Demo slice (250k, bundled)"]

        elif source == "Local path":
            path = st.text_input("Path", args.data, label_visibility="collapsed")
            schema = st.selectbox("Schema", list(SCHEMA_MAPS.keys()))

        elif source == "Upload CSV":
            upload = st.file_uploader("CSV", type=["csv"],
                                      label_visibility="collapsed")
            schema = st.selectbox("Schema", list(SCHEMA_MAPS.keys()))
        st.markdown("<div class='eyebrow'>Sensitivity</div>",
                    unsafe_allow_html=True)
        min_conf = st.select_slider(
            "Confirmations", options=[1, 2, 3], value=1,
            help="Independent typologies an account must trigger before being "
                 "flagged. Higher suppresses false positives at the cost of recall.",
            label_visibility="collapsed")
        st.caption(f"Requiring {min_conf} independent "
                   f"{'typology' if min_conf == 1 else 'typologies'}")

        st.markdown("<div class='eyebrow'>Try a query</div>",
                    unsafe_allow_html=True)
        for q in EXAMPLES:
            if st.button(q, use_container_width=True, key=f"ex_{q[:14]}"):
                st.session_state.query = q

        if st.session_state.history:
            st.markdown("<div class='eyebrow'>Session</div>",
                        unsafe_allow_html=True)
            for h in reversed(st.session_state.history[-6:]):
                st.caption(f"`{h['intent']}` · {h['query'][:38]}")

    return path, schema, upload, min_conf


def header(df, n_hubs):
    st.title("AML Sentinel")
    st.caption("Agentic investigation assistant for anti-money-laundering analysts")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{len(df):,}")
    c2.metric("Accounts",
              f"{pd.concat([df['sender'], df['receiver']]).nunique():,}")
    c3.metric("Days covered",
              f"{(df['timestamp'].max() - df['timestamp'].min()).days}")
    c4.metric("Hubs excluded", n_hubs)


# --------------------------------------------------------------------------- #
# tab 1 — query-driven investigation
# --------------------------------------------------------------------------- #

def render_evidence(df, out, intent):
    scoped = out.get("filtered_df")
    if scoped is None or len(scoped) == 0:
        scoped = df

    st.markdown("<div class='eyebrow'>Supporting evidence</div>",
                unsafe_allow_html=True)

    if intent.intent_type == IntentType.ENTITY_LOOKUP and intent.entity_ids:
        account = intent.entity_ids[0]
        c1, c2 = st.columns(2)
        timeline = viz.account_timeline(df, account)
        network = viz.network_graph(df, account)
        if timeline:
            c1.plotly_chart(timeline, use_container_width=True)
        if network:
            c2.plotly_chart(network, use_container_width=True)
        return

    c1, c2 = st.columns(2)
    c1.plotly_chart(viz.amount_distribution(scoped), use_container_width=True)
    c2.plotly_chart(viz.daily_volume(scoped), use_container_width=True)

    scored = out.get("scored")
    if scored is not None and len(scored):
        c3, c4 = st.columns(2)
        c3.plotly_chart(viz.risk_breakdown(scored), use_container_width=True)
        typ = viz.typology_breakdown(out.get("all_hits") or [])
        if typ:
            c4.plotly_chart(typ, use_container_width=True)


def render_query_tab(df, min_conf):
    query = st.text_input("Ask a question", value=st.session_state.query,
                          placeholder="Find structuring patterns in the last 3 days")

    if not query:
        st.markdown("<div class='eyebrow'>What you can ask</div>",
                    unsafe_allow_html=True)
        st.markdown(EMPTY_STATE, unsafe_allow_html=True)
        return

    intent = parse(query)
    plan = build_plan(intent)

    st.markdown("<div class='eyebrow'>Agent</div>", unsafe_allow_html=True)
    st.markdown(
        f"Parsed intent **{intent.intent_type.value}** "
        f"({intent.confidence:.0%} confidence, via {intent.parser_used}) · "
        f"planned **{len(plan.steps)} steps**, skipping {len(plan.skipped)} tools")

    trace_slot = st.empty()
    progress = st.progress(0.0)
    partial = []

    def on_step(call):
        partial.append(call)
        trace_slot.markdown(funnel(partial, []), unsafe_allow_html=True)
        progress.progress(min(len(partial) / max(len(plan.steps), 1), 1.0))

    out = Executor(df, on_step=on_step,
                   memory=st.session_state.last_results,
                   min_confirmations=min_conf).run(plan)
    progress.empty()

    trace_slot.markdown(funnel(out["trace"], plan.skipped), unsafe_allow_html=True)
    st.caption(f"Completed in {out['elapsed']}s")

    if out.get("sampled"):
        st.caption("Bounded to a recent slice for interactive latency — "
                   "see the trace above.")

    def remember(flagged: int):
        st.session_state.history.append({
            "query": query, "intent": intent.intent_type.value, "flagged": flagged})

    if out.get("message"):
        st.markdown("<div class='eyebrow'>Answer</div>", unsafe_allow_html=True)
        st.success(out["message"])
        remember(0)
        return

    if out.get("aggregate") is not None:
        st.markdown("<div class='eyebrow'>Result</div>", unsafe_allow_html=True)
        st.dataframe(out["aggregate"], hide_index=True, use_container_width=True)
        render_evidence(df, out, intent)
        remember(0)
        return

    results = out["results"]
    st.markdown(f"<div class='eyebrow'>Flagged accounts — {len(results)}</div>",
                unsafe_allow_html=True)

    if not results:
        st.success("No suspicious activity detected for this query.")
    else:
        for r in results:
            st.markdown(case_card(r), unsafe_allow_html=True)

    render_evidence(df, out, intent)
    st.session_state.last_results = results
    remember(len(results))


# --------------------------------------------------------------------------- #
# tab 2 — batch scan
# --------------------------------------------------------------------------- #

def render_scan_tab(df, min_conf):
    st.markdown("<div class='eyebrow'>Batch scan — all detectors</div>",
                unsafe_allow_html=True)
    st.caption("Runs the complete detector suite over the loaded dataset. "
               "The Investigate tab is the query-driven path; this is the "
               "exhaustive one.")

    if not st.button("Run full scan", type="primary"):
        st.info("Runs structuring, smurfing, velocity, rapid cash-out, fan-in, "
                "fan-out, cycles, layering and the unsupervised anomaly layer.")
        return

    hits, summary = run_all_detectors(df, f"{len(df)}")

    st.markdown("<div class='eyebrow'>Detector output</div>",
                unsafe_allow_html=True)
    st.dataframe(summary, hide_index=True, use_container_width=True)

    scored = score_hits(hits, min_confirmations=min_conf)

    if scored.empty:
        st.info(f"No accounts met the {min_conf}-confirmation threshold. "
                f"Lower the sensitivity in the sidebar.")
        return

    st.markdown(f"<div class='eyebrow'>Flagged accounts — {len(scored)}</div>",
                unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("High risk", int((scored["risk"] == "high").sum()))
    c2.metric("Medium risk", int((scored["risk"] == "medium").sum()))
    c3.metric("Low risk", int((scored["risk"] == "low").sum()))
    c4.metric("Multi-typology", int((scored["confirmations"] >= 2).sum()))

    c1, c2 = st.columns(2)
    c1.plotly_chart(viz.risk_breakdown(scored), use_container_width=True)
    typ = viz.typology_breakdown(hits)
    if typ:
        c2.plotly_chart(typ, use_container_width=True)

    table = scored[["account", "score", "risk", "confirmations", "typologies"]]
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.download_button("Download flagged accounts (CSV)",
                       table.to_csv(index=False),
                       "flagged_accounts.csv", mime="text/csv")

    st.markdown("<div class='eyebrow'>Top cases</div>", unsafe_allow_html=True)
    for _, row in scored.head(10).iterrows():
        st.markdown(case_card(explain_account(row.to_dict())),
                    unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# tab 3 — metrics
# --------------------------------------------------------------------------- #

def render_metrics_tab():
    st.markdown("<div class='eyebrow'>Detector performance</div>",
                unsafe_allow_html=True)
    st.caption("Precision and recall against labelled laundering transactions. "
               "Reproduce with `python -m evaluation.metrics`.")

    try:
        results = pd.read_csv("evaluation/results.csv")
        display = results.copy()
        for col in ("precision", "recall", "f1"):
            if col in display.columns:
                display[col] = display[col].map(lambda v: f"{v:.2%}")
        st.dataframe(display, hide_index=True, use_container_width=True)
    except Exception:
        st.info("Run `python -m evaluation.metrics --data "
                "data/sample/demo_transactions.csv --schema demo` "
                "to generate results.")

    st.markdown("<div class='eyebrow'>Confirmation ensemble</div>",
                unsafe_allow_html=True)
    st.markdown("""
Accounts flagged by multiple *independent* detectors are far more likely to be
genuine. Precision rises monotonically with confirmation count — the sensitivity
control in the sidebar moves along this curve.

| Confirmations | Accounts | True positives | Precision | Lift over base rate |
|---|---|---|---|---|
| 1+ | 1,077 | 88 | 8.2% | 1.2x |
| 2+ | 269 | 26 | 9.7% | 1.4x |
| 3+ | 34 | 10 | 29.4% | 4.3x |
| 4+ | 5 | 4 | **80.0%** | **11.6x** |

Measured on the bundled demo slice, which over-samples laundering accounts to
keep the demo dense. On the full dataset the base rate is far lower, so
real-world lift is correspondingly higher.
""")


# --------------------------------------------------------------------------- #
# tab 4 — dataset profile
# --------------------------------------------------------------------------- #

def render_profile_tab(df):
    st.markdown("<div class='eyebrow'>Population profile</div>",
                unsafe_allow_html=True)
    st.caption("Automated exploratory analysis of the loaded dataset.")

    p = profile(df)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total value (USD eq.)", f"{p['total_usd']:,.0f}")
    c2.metric("Median transaction", f"{p['median_usd']:,.0f}")
    c3.metric("99th percentile", f"{p['p99_usd']:,.0f}")

    c1, c2 = st.columns(2)
    c1.plotly_chart(viz.amount_distribution(df), use_container_width=True)
    c2.plotly_chart(viz.daily_volume(df), use_container_width=True)

    c1, c2 = st.columns(2)
    c1.markdown("**Currencies**")
    c1.dataframe(pd.Series(p["currencies"]).rename("transactions"),
                 use_container_width=True)
    c2.markdown("**Payment types**")
    c2.dataframe(pd.Series(p["tx_types"]).rename("transactions"),
                 use_container_width=True)

    if "is_laundering" in df.columns:
        labelled = int((df["is_laundering"] == 1).sum())
        st.caption(f"Labelled laundering transactions: {labelled:,} "
                   f"({labelled / len(df):.3%})")


# --------------------------------------------------------------------------- #

def main():
    init_state()
    args = cli_args()
    path, schema, upload, min_conf = sidebar(args)

    try:
        if upload is not None:
            df, n_hubs = get_uploaded(upload.getvalue(), schema)
        else:
            df, n_hubs = get_data(path, schema)
    except Exception as exc:
        st.error(f"Could not load the dataset — {exc}")
        st.caption("Check the path and schema in the sidebar, or follow the "
                   "download instructions in the README.")
        st.stop()

    header(df, n_hubs)

    tab_q, tab_scan, tab_metrics, tab_profile = st.tabs(
        ["Investigate", "Full scan", "Detector metrics", "Dataset profile"])

    with tab_q:
        render_query_tab(df, min_conf)
    with tab_scan:
        render_scan_tab(df, min_conf)
    with tab_metrics:
        render_metrics_tab()
    with tab_profile:
        render_profile_tab(df)


if __name__ == "__main__":
    main()