CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --paper:#F7F6F3; --ink:#16202B; --rule:#D8D5CE; --muted:#6E7681;
  --signal:#1F5C8C; --high:#A62B1F; --med:#B0761C; --low:#6B7280;
}

.stApp { background: var(--paper); }
html, body, [class*="css"] { color: var(--ink); }

h1, h2, h3 {
  font-family:'Archivo',sans-serif !important;
  letter-spacing:-0.02em; font-weight:700 !important;
}
h1 { font-size:2.1rem !important; text-transform:uppercase; letter-spacing:0.04em !important; }

.eyebrow {
  font-family:'Archivo',sans-serif; font-size:0.68rem; font-weight:600;
  text-transform:uppercase; letter-spacing:0.14em; color:var(--muted);
  border-bottom:1px solid var(--rule); padding-bottom:6px; margin:22px 0 12px;
}

.mono, code, .stDataFrame { font-family:'IBM Plex Mono',monospace !important; }

/* funnel trace */
.trace-row { display:flex; align-items:center; gap:12px; margin:3px 0; }
.trace-name {
  font-family:'IBM Plex Mono',monospace; font-size:0.76rem;
  width:132px; text-align:right; color:var(--ink);
}
.trace-bar {
  height:20px; background:var(--signal); opacity:0.85;
  border-radius:1px; min-width:2px;
  transition:width .5s cubic-bezier(.2,.8,.2,1);
}
.trace-val {
  font-family:'IBM Plex Mono',monospace; font-size:0.72rem;
  color:var(--muted); white-space:nowrap;
}
.trace-why { font-size:0.7rem; color:var(--muted); font-style:italic; }
.trace-skip {
  font-family:'IBM Plex Mono',monospace; font-size:0.72rem;
  color:var(--muted); text-decoration:line-through; opacity:.55;
}

/* case cards */
.case {
  border:1px solid var(--rule); border-left:3px solid var(--rule);
  background:#FFFDFA; padding:16px 18px; margin-bottom:12px;
}
.case-high { border-left-color:var(--high); }
.case-med  { border-left-color:var(--med); }
.case-low  { border-left-color:var(--low); }
.case-id {
  font-family:'IBM Plex Mono',monospace; font-size:1.05rem;
  font-weight:600; letter-spacing:0.02em;
}
.badge {
  font-family:'Archivo',sans-serif; font-size:0.66rem; font-weight:700;
  text-transform:uppercase; letter-spacing:0.12em;
  padding:3px 9px; border:1px solid currentColor;
}
.b-high { color:var(--high); } .b-med { color:var(--med); } .b-low { color:var(--low); }
.reason { font-size:0.87rem; line-height:1.5; margin:8px 0; padding-left:14px;
          border-left:1px solid var(--rule); }
.action {
  font-family:'Archivo',sans-serif; font-size:0.74rem; font-weight:600;
  text-transform:uppercase; letter-spacing:0.1em; margin-top:12px;
  padding-top:10px; border-top:1px solid var(--rule);
}

[data-testid="stMetricValue"] { font-family:'IBM Plex Mono',monospace !important; font-size:1.5rem !important; }
[data-testid="stMetricLabel"] {
  font-family:'Archivo',sans-serif !important; font-size:0.66rem !important;
  text-transform:uppercase; letter-spacing:0.1em; color:var(--muted) !important;
}
#MainMenu, footer, header { visibility:hidden; }
</style>
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