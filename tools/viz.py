import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

INK, SIGNAL, RULE = "#16202B", "#1F5C8C", "#D8D5CE"
RISK = {"high": "#A62B1F", "medium": "#B0761C", "low": "#6B7280"}

LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="IBM Plex Mono, monospace", size=11, color=INK),
    margin=dict(l=40, r=20, t=36, b=36), height=260,
)


def amount_distribution(df, threshold=10000):
    """Amount histogram with the reporting threshold marked — shows clustering."""
    d = df[df["amount"] < threshold * 3]
    fig = px.histogram(d, x="amount", nbins=60,
                       color_discrete_sequence=[SIGNAL])
    fig.add_vline(x=threshold, line_dash="dash", line_color=RISK["high"],
                  annotation_text=f"reporting threshold {threshold:,.0f}",
                  annotation_position="top right")
    fig.update_layout(title="Transaction amounts vs reporting threshold",
                      xaxis_title="amount", yaxis_title="count", **LAYOUT)
    return fig


def daily_volume(df, flagged_accounts=None):
    d = df.set_index("timestamp").resample("D").agg(
        volume=("amount", "sum"), count=("tx_id", "count")).reset_index()
    fig = go.Figure(go.Bar(x=d["timestamp"], y=d["count"],
                           marker_color=SIGNAL, name="transactions"))
    fig.update_layout(title="Daily transaction volume",
                      xaxis_title="", yaxis_title="transactions", **LAYOUT)
    return fig


def risk_breakdown(scored):
    counts = scored["risk"].value_counts()
    fig = go.Figure(go.Bar(
        x=counts.index, y=counts.values,
        marker_color=[RISK.get(r, INK) for r in counts.index]))
    fig.update_layout(title="Flagged accounts by risk tier",
                      xaxis_title="", yaxis_title="accounts", **LAYOUT)
    return fig


def typology_breakdown(hits):
    if not hits:
        return None
    counts = pd.Series([h["typology"] for h in hits]).value_counts()
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h",
                           marker_color=SIGNAL))
    fig.update_layout(title="Detections by typology",
                      xaxis_title="accounts", yaxis_title="", **LAYOUT)
    return fig


def account_timeline(df, account):
    """Per-account transaction timeline — the evidence view for entity queries."""
    d = df[(df["sender"] == account) | (df["receiver"] == account)].copy()
    if d.empty:
        return None
    d["direction"] = d["sender"].eq(account).map({True: "out", False: "in"})
    fig = px.scatter(d, x="timestamp", y="amount", color="direction",
                     size="amount", size_max=18,
                     color_discrete_map={"out": RISK["high"], "in": SIGNAL})
    fig.update_layout(title=f"Transaction timeline — {account}",
                      xaxis_title="", yaxis_title="amount", **LAYOUT)
    return fig


def network_graph(df, account, max_nodes=25):
    """Counterparty network around one account — the graph evidence view."""
    import networkx as nx
    d = df[(df["sender"] == account) | (df["receiver"] == account)]
    if d.empty:
        return None

    G = nx.DiGraph()
    for _, r in d.head(max_nodes).iterrows():
        G.add_edge(str(r["sender"]), str(r["receiver"]), weight=r["amount"])

    pos = nx.spring_layout(G, seed=42)
    ex, ey = [], []
    for a, b in G.edges():
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines",
                             line=dict(width=1, color=RULE), hoverinfo="none"))
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in G.nodes()], y=[pos[n][1] for n in G.nodes()],
        mode="markers+text", text=[n[-5:] for n in G.nodes()],
        textposition="top center", textfont=dict(size=9),
        marker=dict(size=[26 if n == account else 13 for n in G.nodes()],
                    color=[RISK["high"] if n == account else SIGNAL
                           for n in G.nodes()])))
    fig.update_layout(title=f"Counterparty network — {account}",
                      showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      **{k: v for k, v in LAYOUT.items() if k != "margin"},
                      margin=dict(l=0, r=0, t=36, b=0))
    return fig