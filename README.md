# 🛡 AML Sentinel

> **An agentic investigation assistant for anti-money-laundering analysts.**
> Ask in plain English — the agent decides which analyses to run, flags
> suspicious activity, explains why, and recommends an escalation action.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/ui-streamlit-red)
![No API key required](https://img.shields.io/badge/API%20key-optional-green)
![Dataset bundled](https://img.shields.io/badge/dataset-bundled-brightgreen)

---

## ⚡ Evaluate in 60 seconds

```bash
git clone <repo-url> && cd aml-sentinel
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
streamlit run app.py
```

**No dataset download. No API key. No GPU.** 397,624 real transactions ship
with the repository.

Then paste these three queries in order and watch the **execution trace** change:

| # | Paste this | What to look for |
|---|---|---|
| 1 | `Is customer 80004B890 suspicious?` | Filters 397k rows → a handful. Skips EDA, graph traversal and ML — unnecessary for one account. |
| 2 | `Find structuring patterns in the last 3 days` | Applies a date filter first, then runs **only** the structuring detector. Eight other detectors listed as skipped, each with a reason. |
| 3 | `Which customers made 10+ transactions under $10,000?` | Answers by aggregation alone. **No ML, no detectors** — the agent recognises it doesn't need them. |

Three queries, three different execution paths through the same system. That
routing is the core of the submission.

> 💡 Then drag the **Sensitivity** slider in the sidebar from 1 to 3 and re-run
> a scan. Precision climbs from 8% to 29% as the agent requires more
> independent confirmation. That is the false-positive problem, controllable.

---

## 🗂 What's in the four tabs

| Tab | What it shows |
|---|---|
| **Investigate** | Query-driven analysis with a live execution trace |
| **Full scan** | Every detector run in batch, ranked results, CSV export |
| **Detector metrics** | Precision and recall against labelled ground truth |
| **Dataset profile** | Automated exploratory analysis |

---

## 🎯 The problem

Rule-based AML systems bury compliance teams in false positives while
sophisticated typologies — structuring, smurfing, layering — slip past. Analysts
spend their day dismissing alerts instead of investigating threats.

**AML Sentinel** is a query-driven agent that detects laundering patterns,
explains every flag in analyst language, and gives a direct control for trading
recall against precision.

*Scope: retail and commercial transaction monitoring. Trade-based and
securities laundering need different data and are out of scope.*

---

## 🤖 What makes it agentic

The agent does **not** run a fixed pipeline. It parses intent, filters, entities
and target typology, then builds an execution plan invoking only what's needed —
and reports what it deliberately skipped.

<details>
<summary><b>See the routing table →</b></summary>

<br>

| Query | Invoked | Skipped |
|---|---|---|
| `Is customer X suspicious?` | entity filter, features, cheap detectors | EDA, graph traversal, ML layer |
| `Find structuring in the last 3 days` | date filter, features, structuring | 8 detectors, EDA |
| `10+ transactions under $10,000?` | aggregation only | all detectors, ML |
| `How many transactions?` | dataset description | everything |
| `What can you do?` | nothing | everything |

Every response shows rows entering and leaving each tool, why each tool was
chosen, and why each was skipped.

</details>

---

## 📊 Results

<details open>
<summary><b>Confirmation ensemble — the headline result</b></summary>

<br>

Accounts flagged by several **independent** detectors are far more likely to be
genuine:

| Confirmations | Accounts | True positives | Precision | Lift |
|---|---|---|---|---|
| 1+ | 1,077 | 88 | 8.2% | 1.2× |
| 2+ | 269 | 26 | 9.7% | 1.4× |
| 3+ | 34 | 10 | 29.4% | 4.3× |
| 4+ | 5 | 4 | **80.0%** | **11.6×** |

Precision rises monotonically with confirmation. The sidebar slider moves along
this curve live.

</details>

<details>
<summary><b>Per-detector precision →</b></summary>

<br>

| Detector | Flagged | Precision |
|---|---|---|
| cycle | 4 | 100% |
| smurfing | 5 | 100% |
| fan-in | 8 | 88% |
| layering | 2 | 50% |
| ML anomaly | 29 | 34% |
| rapid cash-out | 146 | 31% |
| fan-out | 91 | 12% |
| structuring | 200 | 5% |
| velocity | 901 | 4% |

Reproduce: `python -m evaluation.metrics`

The bundled slice over-samples laundering accounts to keep the demo dense, so
its base rate is higher than reality. On the full dataset the base rate is ~1%
and real-world lift is correspondingly higher.

</details>

---

## 🏗 Architecture

```
        Analyst query
              ↓
  ┌───────────────────────────┐
  │  Intent parsing           │   ← LLM optional
  │  regex → spec → classify  │
  └───────────────────────────┘
              ↓
  ┌───────────────────────────┐
  │  Planner                  │   ← picks tools per query
  └───────────────────────────┘
              ↓
  ┌───────────────────────────┐
  │  Execution                │   ← fully deterministic
  │  detect → score → explain │
  └───────────────────────────┘
```

<details>
<summary><b>Three-tier intent parsing →</b></summary>

<br>

1. **Regex parser** — deterministic, no dependencies. Handles every core
   typology, entity and threshold query. **Works with no API key.**
2. **Constrained query spec** — for analytical questions regex doesn't
   recognise, an LLM emits a JSON spec (filters, group-by, aggregations),
   validated against an allowlist and executed by pandas. *The model proposes;
   the code decides.*
3. **Intent classifier** — final fallback for on-topic questions the spec
   format can't express.

Out-of-scope questions are **refused explicitly** rather than answered wrongly.

</details>

<details>
<summary><b>Where the LLM sits — and doesn't →</b></summary>

<br>

The language model touches **intent parsing only**. It never sees transaction
rows, only the schema and category values.

Detection, scoring and explanations are **fully deterministic** — every flag is
reproducible and auditable. In compliance tooling, "the model said so" is not an
acceptable justification.

</details>

<details>
<summary><b>Detection layers →</b></summary>

<br>

| Layer | Detectors | Why |
|---|---|---|
| **Rules** | structuring, smurfing, velocity, rapid cash-out | encode known regulatory typologies |
| **Graph** | fan-in, fan-out, cycles, layering chains | laundering is a network crime; row-wise scoring can't see topology |
| **ML** | IsolationForest over account features | catches novel behaviour no rule encodes |

</details>

---

## 💬 Queries that work without an API key

Copy any of these:

```
what can you do?
how many transactions
Is customer 80004B890 suspicious?
Find structuring patterns in the last 3 days
Show me smurfing activity
Detect layering chains
Find fan-in patterns
Show me circular flows over $50,000
Which customers made 10+ transactions under $10,000?
Analyse this dataset for suspicious activity
```

**Combinable filters:** `last N days` · `since 2022-09-05` · `under $10,000` ·
`over $50,000` · `N+ transactions` · currency names

<details>
<summary><b>Enabling free-form questions (optional) →</b></summary>

<br>

Questions like *"top 10 accounts by total volume"* need a language model to
build a query spec. Create `.env`:

```
GROQ_API_KEY=your_key_here
```

Free key at [console.groq.com](https://console.groq.com) — no card required.

Without it the app runs in **deterministic mode**: all detection works, and
unrecognised free-form questions return a clarification prompt rather than a
guess.

</details>

---

## 📁 Dataset

**Bundled** — `data/sample/demo_transactions.csv` · 397,624 transactions ·
63,233 accounts · 16 days

Selected by **whole account history**, not random sampling — a random sample
fragments histories, so multi-transaction typologies can't appear. Every
labelled laundering transaction in the selected accounts is retained. Logic in
`data/make_demo_slice.py`.

**Full dataset (optional)** —
[IBM Transactions for AML](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)

Download `HI-Small_Trans.csv` (high illicit rate) and `LI-Small_Trans.csv` (low)
into `data/raw/`, then pick them from the dataset dropdown — the same detectors
tested at two different prevalence levels.

<details>
<summary><b>Preprocessing decisions →</b></summary>

<br>

**Institutional hubs excluded.** Accounts above 5,000 transactions are banks or
settlement nodes, not customers. They legitimately show extreme velocity and
constant pass-through and would dominate every detector. Correspondent banking
has separate controls. **Label retention is reported on every filter**, so
narrowing the population can never silently destroy evaluation.

**Multi-currency thresholds.** A €9,200 transfer is not structuring against a
$10,000 threshold. Threshold typologies use each currency's own reporting
trigger — USD 10,000 (FinCEN CTR), EUR 10,000, CNY 50,000. Cross-account
comparisons normalise to `amount_usd`. Cryptocurrency is excluded from threshold
rules — no equivalent cash-reporting trigger exists.

**Rule parameters.** Typologies follow FATF definitions. The $10,000 reference
is the Bank Secrecy Act CTR threshold — the requirement structuring exists to
evade. Windows and counts were set from the 99th percentile of the observed
population and live in `config/thresholds.json`.

</details>

---

## 🔧 Tech stack

`Python 3.10+` · `pandas` · `scikit-learn` · `networkx` · `streamlit` ·
`plotly` · optional `Groq` for intent parsing

**No database. No deployment. No model weights.**

---

## 📂 Structure

```
agent/       intent parsing, query spec, planning, execution
tools/       loader, filters, currency, features, rules, graph,
             anomaly, risk, explanation, EDA, visualisation
data/        bundled slice + generator
evaluation/  metrics against labelled ground truth
config/      tuned detection thresholds
tests/       unit tests for detectors
```

---

<details>
<summary><b>⚠️ Limitations — stated honestly →</b></summary>

<br>

- Batch analysis; live stream ingestion not implemented
- Layering search bounded to highest-value seed transactions
- Smurfing uses fixed time bins — a ring spanning a boundary may be missed
- Multi-step reasoning questions can't be expressed in the query spec format
- FX rates are static reference values, not time-of-transaction
- Activity filtering removes a small share of labelled laundering; exact
  retention printed at load

**Roadmap:** stream ingestion · columnar storage for larger-than-memory data ·
trade-based laundering module · analyst feedback loop to retune thresholds

</details>

---

## 📚 Sources & disclosure

**Data** — IBM Transactions for Anti-Money Laundering (Kaggle), linked above

**Reference** — FATF typology definitions · FinCEN / Bank Secrecy Act CTR
threshold

**Libraries** — see `requirements.txt`

**AI assistance** — an AI coding assistant was used for scaffolding, debugging
and documentation drafting. Architecture, detector design, threshold tuning and
evaluation were directed and verified by the author.

**Licence** — MIT