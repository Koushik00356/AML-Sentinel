from tools.loader import load
from tools.filters import filter_analyzable
from agent.intent_parser import parse
from agent.planner import build_plan
from agent.executor import Executor

df, _ = filter_analyzable(load("data/raw/HI-Small_Trans.csv", schema="ibm_aml"))
ex = Executor(df)

for q in ["Is customer 8000EBD30 suspicious?",
          "Find structuring patterns in the last 30 days",
          "what can you do?"]:
    out = ex.run(build_plan(parse(q)))
    print(f"\n{q}  [{out['elapsed']}s]")
    for t in out["trace"]:
        print(f"  {t.tool:<18} {t.rows_in:>9,} → {t.rows_out:<7,} {t.reason}")
    for r in out["results"][:2]:
        print(f"  → {r['summary']}")



print(df["timestamp"].min(), df["timestamp"].max(),
      (df["timestamp"].max() - df["timestamp"].min()).days)

from tools.rules import detect_structuring
hits = detect_structuring(df)
print([h["account"] for h in hits[:10]])

