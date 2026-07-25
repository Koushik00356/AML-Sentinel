import argparse
import sys
import pandas as pd
import streamlit as st

from tools.loader import load
from tools.filters import filter_analyzable
from agent.intent_parser import parse
from agent.planner import build_plan
from agent.executor import Executor
from assets.style import CSS, funnel, case_card


def cli_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/sample/sample_transactions.csv")
    p.add_argument("--schema", default="synthetic")
    known, _ = p.parse_known_args(sys.argv[1:])
    return known


@st.cache_data(show_spinner="Loading transactions…")
def get_data(path: str, schema: str):
    df = load(path, schema=schema)
    df, hubs = filter_analyzable(df, verbose=False)
    return df, len(hubs)


def main():
    args = cli_args()

    st.title("AML Sentinel")
    st.caption("Agentic investigation assistant for anti-money-laundering analysts")

    with st.sidebar:
        st.subheader("Dataset")
        path = st.text_input("Path", args.data)
        schema = st.selectbox("Schema", ["synthetic", "ibm_aml"],
                              index=0 if args.schema == "synthetic" else 1)
        st.divider()
        st.subheader("Example queries")
        for q in ["what can you do?",
                  "Is customer 80004B890 suspicious?",
                  "Find structuring patterns in the last 3 days",
                  "Which customers made 10+ transactions under $10,000?",
                  "Show me circular flows over $50,000"]:
            if st.button(q, use_container_width=True):
                st.session_state["query"] = q

    try:
        df, n_hubs = get_data(path, schema)
    except Exception as e:
        st.error(f"Could not load `{path}`: {e}")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transactions", f"{len(df):,}")
    c2.metric("Accounts", f"{pd.concat([df['sender'], df['receiver']]).nunique():,}")
    c3.metric("Date range", f"{(df['timestamp'].max() - df['timestamp'].min()).days} days")
    c4.metric("Hubs excluded", n_hubs)

    query = st.text_input("Ask a question",
                          value=st.session_state.get("query", ""),
                          placeholder="Find structuring patterns in the last 3 days")

    if not query:
        st.info("Enter a query above, or pick an example from the sidebar.")
        return

    intent = parse(query)
    plan = build_plan(intent)

    with st.spinner("Investigating…"):
        out = Executor(df).run(plan)

    # ---- execution summary: the agentic evidence ----
    st.subheader("Execution summary")
    a, b = st.columns([1, 1])

    with a:
        st.markdown("**Interpretation**")
        st.write(f"Intent: `{intent.intent_type.value}` "
                 f"(confidence {intent.confidence:.0%}, via {intent.parser_used})")
        if intent.typology.value != "any":
            st.write(f"Typology: `{intent.typology.value}`")
        if intent.entity_ids:
            st.write(f"Entities: `{', '.join(intent.entity_ids)}`")
        f = intent.filters
        applied = [x for x in [
            f"last {f.days_back} days" if f.days_back else None,
            f"under {f.max_amount:,.0f}" if f.max_amount else None,
            f"over {f.min_amount:,.0f}" if f.min_amount else None,
            f"{f.min_count}+ transactions" if f.min_count else None,
            f.currency,
        ] if x]
        st.write(f"Filters: {', '.join(applied) if applied else 'none'}")
        st.caption(f"Completed in {out['elapsed']}s")

    with b:
        st.markdown("**Tools invoked**")
        if out["trace"]:
            st.dataframe(pd.DataFrame([{
                "tool": t.tool, "in": f"{t.rows_in:,}",
                "out": f"{t.rows_out:,}", "ms": int(t.duration_ms),
                "why": t.reason,
            } for t in out["trace"]]), hide_index=True, use_container_width=True)

    if plan.skipped:
        with st.expander(f"Tools deliberately skipped ({len(plan.skipped)})"):
            for tool, reason in plan.skipped:
                st.write(f"**{tool}** — {reason}")

    st.divider()

    if out.get("message"):
        st.info(out["message"])
        return

    if out.get("aggregate") is not None:
        st.subheader("Matching accounts")
        st.dataframe(out["aggregate"], hide_index=True, use_container_width=True)
        return

    if out.get("eda"):
        e = out["eda"]
        st.subheader("Population profile")
        g1, g2 = st.columns(2)
        g1.bar_chart(e["daily_volume"])
        g2.bar_chart(pd.Series(e["tx_types"]))

    results = out["results"]
    st.subheader(f"Flagged accounts ({len(results)})")

    if not results:
        st.success("No suspicious activity detected for this query.")
        return

    if out.get("sampled"):
        st.caption("Analysis bounded to a recent slice for interactive latency — "
                   "see execution summary.")

    for r in results:
        color = RISK_COLOR[r["risk"]]
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            h1.markdown(f"### `{r['account']}`")
            h2.markdown(
                f"<div style='text-align:right'>"
                f"<span style='color:{color};font-weight:700;font-size:1.1rem'>"
                f"{r['risk'].upper()}</span><br>"
                f"<span style='color:#888'>score {r['score']}</span></div>",
                unsafe_allow_html=True)
            for reason in r["reasons"]:
                st.write(f"• {reason}")
            st.markdown(f"**Recommended action — {r['action'].upper()}:** "
                        f"{r['action_text']}")

    
        st.markdown(CSS, unsafe_allow_html=True)

        # replace the trace dataframe block
        st.markdown("<div class='eyebrow'>Execution trace</div>", unsafe_allow_html=True)
        st.markdown(funnel(out["trace"], plan.skipped), unsafe_allow_html=True)

        # replace the results loop
        st.markdown(f"<div class='eyebrow'>Flagged accounts — {len(results)}</div>",
                    unsafe_allow_html=True)
        for r in results:
            st.markdown(case_card(r), unsafe_allow_html=True)

        st.set_page_config(page_title="AML Sentinel", page_icon="🛡", layout="wide")

        RISK_COLOR = {"high": "#c0392b", "medium": "#d68910", "low": "#7f8c8d"}




if __name__ == "__main__":
    main()

