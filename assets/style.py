CSS = """
<style>
.stApp { border-top: 5px solid red !important; }
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --paper:#F7F6F3; --card:#FFFDFA; --ink:#16202B; --rule:#E2DFD8;
  --muted:#6E7681; --signal:#1F5C8C; --signal-soft:#E8EFF5;
  --high:#A62B1F; --med:#B0761C; --low:#6B7280;
}

.stApp { background: var(--paper); }
html, body, [class*="css"], p, li, label, .stMarkdown {
  font-family:'Archivo',sans-serif !important; color:var(--ink);
}

h1 {
  font-family:'Archivo',sans-serif !important;
  font-size:1.9rem !important; font-weight:700 !important;
  letter-spacing:0.03em !important; text-transform:uppercase;
  margin-bottom:0 !important; padding-bottom:10px;
  border-bottom:2px solid var(--ink);
}
h2, h3 { font-family:'Archivo',sans-serif !important; font-weight:600 !important; }

.eyebrow {
  font-size:0.68rem; font-weight:600; text-transform:uppercase;
  letter-spacing:0.14em; color:var(--muted);
  border-bottom:1px solid var(--rule); padding-bottom:6px; margin:26px 0 14px;
}

/* metrics as cards */
[data-testid="stMetric"] {
  background:var(--card); border:1px solid var(--rule);
  padding:14px 16px; border-radius:2px;
}
[data-testid="stMetricValue"] {
  font-family:'IBM Plex Mono',monospace !important;
  font-size:1.45rem !important; font-weight:600 !important;
}
[data-testid="stMetricLabel"] {
  font-size:0.64rem !important; text-transform:uppercase;
  letter-spacing:0.1em; color:var(--muted) !important;
}

/* query box */
.stTextInput input {
  font-family:'IBM Plex Mono',monospace !important; font-size:0.95rem !important;
  background:var(--card) !important; border:1px solid var(--rule) !important;
  border-radius:2px !important; padding:14px 16px !important;
}
.stTextInput input:focus { border-color:var(--signal) !important; box-shadow:none !important; }

/* example cards for the empty state */
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:6px; }
.qcard {
  background:var(--card); border:1px solid var(--rule); border-left:2px solid var(--signal);
  padding:14px 16px; border-radius:0;
}
.qcard-k {
  font-size:0.62rem; text-transform:uppercase; letter-spacing:0.1em;
  color:var(--signal); font-weight:600; margin-bottom:6px;
}
.qcard-q { font-family:'IBM Plex Mono',monospace; font-size:0.82rem; line-height:1.45; }

/* funnel trace */
.trace-row { display:flex; align-items:center; gap:12px; margin:4px 0; }
.trace-name {
  font-family:'IBM Plex Mono',monospace; font-size:0.75rem;
  width:130px; text-align:right; font-weight:500;
}
.trace-bar { height:18px; background:var(--signal); border-radius:1px; min-width:3px; }
.trace-val { font-family:'IBM Plex Mono',monospace; font-size:0.71rem; color:var(--muted); white-space:nowrap; }
.trace-why { font-size:0.72rem; color:var(--muted); }
.trace-skip {
  font-family:'IBM Plex Mono',monospace; font-size:0.71rem;
  color:var(--muted); text-decoration:line-through; opacity:.5;
}

/* case cards */
.case {
  background:var(--card); border:1px solid var(--rule);
  border-left:3px solid var(--rule); padding:18px 20px; margin-bottom:14px;
}
.case-high { border-left-color:var(--high); }
.case-med  { border-left-color:var(--med); }
.case-low  { border-left-color:var(--low); }
.case-id { font-family:'IBM Plex Mono',monospace; font-size:1.02rem; font-weight:600; }
.badge {
  font-size:0.62rem; font-weight:700; text-transform:uppercase;
  letter-spacing:0.12em; padding:4px 10px; border:1px solid currentColor;
}
.b-high{color:var(--high)} .b-med{color:var(--med)} .b-low{color:var(--low)}
.reason {
  font-size:0.87rem; line-height:1.55; margin:10px 0;
  padding:8px 0 8px 14px; border-left:1px solid var(--rule); color:#2c3742;
}
.action {
  font-size:0.72rem; font-weight:600; text-transform:uppercase;
  letter-spacing:0.1em; margin-top:14px; padding-top:12px;
  border-top:1px solid var(--rule); color:var(--signal);
}

section[data-testid="stSidebar"] { background:#EFEDE8; border-right:1px solid var(--rule); }
section[data-testid="stSidebar"] .stButton button {
  font-family:'IBM Plex Mono',monospace; font-size:0.75rem;
  text-align:left; background:var(--card); border:1px solid var(--rule);
  border-radius:2px; color:var(--ink);
}
section[data-testid="stSidebar"] .stButton button:hover {
  border-color:var(--signal); color:var(--signal);
}

#MainMenu, footer { visibility:hidden; }
header[data-testid="stHeader"] { background:transparent; height:0; }
[data-testid="stSidebarCollapsedControl"] { display:block !important; z-index:999; }

/* tab bar */
.stTabs [data-baseweb="tab-list"] { gap:4px; border-bottom:1px solid var(--rule); }
.stTabs [data-baseweb="tab"] {
  font-family:'Archivo',sans-serif; font-size:0.78rem; font-weight:600;
  text-transform:uppercase; letter-spacing:0.08em; color:var(--muted);
  padding:10px 18px; border-radius:0;
}
.stTabs [aria-selected="true"] {
  color:var(--signal) !important; border-bottom:2px solid var(--signal) !important;
}

/* metric cards lift */
[data-testid="stMetric"] {
  box-shadow:0 1px 2px rgba(22,32,43,.06);
  transition:border-color .15s;
}
[data-testid="stMetric"]:hover { border-color:var(--signal); }

/* case cards */
.case { box-shadow:0 1px 3px rgba(22,32,43,.07); transition:box-shadow .15s; }
.case:hover { box-shadow:0 3px 10px rgba(22,32,43,.12); }

/* trace bars get depth */
.trace-bar {
  background:linear-gradient(90deg,var(--signal),#2E7BB8);
  box-shadow:0 1px 2px rgba(31,92,140,.25);
}
.trace-row:hover .trace-name { color:var(--signal); }

/* buttons */
.stButton button {
  transition:all .15s; border-radius:2px;
}
.stButton button:hover { transform:translateX(2px); }
[data-testid="stBaseButton-primary"] {
  background:var(--signal) !important; border:none !important;
  font-family:'Archivo',sans-serif !important; font-weight:600 !important;
  text-transform:uppercase; letter-spacing:0.08em; font-size:0.78rem !important;
}

/* dataframes */
.stDataFrame { border:1px solid var(--rule); border-radius:2px; }

/* download button */
[data-testid="stDownloadButton"] button {
  border:1px solid var(--signal) !important; color:var(--signal) !important;
  background:transparent !important;
}
</style>
"""

EMPTY_STATE = """
<div class='grid'>
  <div class='qcard'><div class='qcard-k'>Single entity</div>
    <div class='qcard-q'>Is customer 80004B890 suspicious?</div></div>
  <div class='qcard'><div class='qcard-k'>Typology + time</div>
    <div class='qcard-q'>Find structuring patterns in the last 3 days</div></div>
  <div class='qcard'><div class='qcard-k'>Threshold rule</div>
    <div class='qcard-q'>Which customers made 10+ transactions under $10,000?</div></div>
  <div class='qcard'><div class='qcard-k'>Graph topology</div>
    <div class='qcard-q'>Show me circular flows over $50,000</div></div>
  <div class='qcard'><div class='qcard-k'>Free-form</div>
    <div class='qcard-q'>Top 10 accounts by total volume</div></div>
  <div class='qcard'><div class='qcard-k'>Capability</div>
    <div class='qcard-q'>What can you do?</div></div>
</div>
"""


def funnel(trace, skipped):
    if not trace:
        return ""
    peak = max(max(t.rows_in for t in trace), 1)
    rows = []
    for t in trace:
        pct = max(t.rows_out / peak * 100, 0.4) if t.rows_out else 0.4
        rows.append(
            f"<div class='trace-row'>"
            f"<div class='trace-name'>{t.tool}</div>"
            f"<div class='trace-bar' style='width:{pct:.2f}%'></div>"
            f"<div class='trace-val'>{t.rows_in:,} → {t.rows_out:,}</div>"
            f"<div class='trace-why'>{t.reason}</div></div>")
    for tool, why in skipped:
        rows.append(
            f"<div class='trace-row'>"
            f"<div class='trace-name trace-skip'>{tool}</div>"
            f"<div class='trace-why'>skipped — {why}</div></div>")
    return "".join(rows)


def case_card(r):
    cls = {"high": "high", "medium": "med", "low": "low"}[r["risk"]]
    reasons = "".join(f"<div class='reason'>{x}</div>" for x in r["reasons"])
    return (
        f"<div class='case case-{cls}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<span class='case-id'>{r['account']}</span>"
        f"<span class='badge b-{cls}'>{r['risk']} · {r['score']}</span></div>"
        f"{reasons}"
        f"<div class='action'>{r['action']} — {r['action_text']}</div></div>")