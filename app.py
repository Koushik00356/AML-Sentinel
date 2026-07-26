"""AML Sentinel — agentic investigation assistant for AML analysts."""

import argparse
import os
import sys

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from agent.executor import Executor
from agent.intent_parser import parse
from agent.planner import build_plan
from agent.schemas import IntentType
from assets.style import CSS, case_card, funnel
from tools import viz
from tools.filters import filter_analyzable
from tools.loader import SCHEMA_MAPS, load, load_uploaded
from assets.style import CSS, case_card, funnel, EMPTY_STATE

    
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


def cli_args():
    p = argparse.ArgumentParser()
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
    import io
    df = load_uploaded(io.BytesIO(raw), schema=schema)
    df, hubs = filter_analyzable(df, verbose=False)
    return df, len(hubs)

@st.cache_data
def data_context(_df):
    from agent.query_spec import build_context
    return build_context(_df)



def init_state():
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("last_results", [])
    st.session_state.setdefault("query", "")


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
        source = st.radio("Source", ["Bundled demo", "Local path", "Upload CSV"],
                          label_visibility="collapsed")

        path, schema, upload = args.data, args.schema, None

        if source == "Local path":
            path = st.text_input("Path", args.data, label_visibility="collapsed")
            schema = st.selectbox("Schema", list(SCHEMA_MAPS.keys()))
        elif source == "Upload CSV":
            upload = st.file_uploader("CSV", type=["csv"],
                                      label_visibility="collapsed")
            schema = st.selectbox("Schema", list(SCHEMA_MAPS.keys()))

        st.markdown("<div class='eyebrow'>Sensitivity</div>",
                    unsafe_allow_html=True)
        min_conf = st.select_slider(
            "Confirmations required", options=[1, 2, 3], value=1,
            help="Independent typologies an account must trigger before it is "
                 "flagged. Higher suppresses false positives at the cost of recall.",
            label_visibility="collapsed")

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

    executor = Executor(df, on_step=on_step,
                        memory=st.session_state.last_results,
                        min_confirmations=min_conf)
    out = executor.run(plan)
    progress.empty()

    trace_slot.markdown(funnel(out["trace"], plan.skipped),
                        unsafe_allow_html=True)
    st.caption(f"Completed in {out['elapsed']}s")

    if out.get("sampled"):
        st.caption("Bounded to a recent slice for interactive latency — "
                   "see the trace above.")

    def remember(flagged: int):
        st.session_state.history.append({
            "query": query,
            "intent": intent.intent_type.value,
            "flagged": flagged,
        })

    # ---- direct answer (capability, describe, generic scalar, clarify) ----
    if out.get("message"):
        st.markdown("<div class='eyebrow'>Answer</div>", unsafe_allow_html=True)
        st.success(out["message"])
        remember(0)
        return

    # ---- tabular answer (aggregation or generic grouped query) ----
    if out.get("aggregate") is not None:
        st.markdown("<div class='eyebrow'>Result</div>", unsafe_allow_html=True)
        st.dataframe(out["aggregate"], hide_index=True, use_container_width=True)
        render_evidence(df, out, intent)
        remember(0)
        return

    # ---- flagged accounts ----
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


if __name__ == "__main__":
    main()