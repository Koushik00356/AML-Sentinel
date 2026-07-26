# 🛡 AML Sentinel

> **An agentic investigation assistant for anti-money-laundering analysts.**
> Ask in plain English — the agent decides which analyses to run, flags
> suspicious activity, explains why, and recommends an escalation action.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/ui-streamlit-red)
![API key optional](https://img.shields.io/badge/API%20key-optional-green)
![Dataset bundled](https://img.shields.io/badge/dataset-bundled-brightgreen)

---

## ⚡ Evaluate in 60 seconds

```bash
git clone <repo-url> && cd aml-sentinel

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
streamlit run app.py
```

**No dataset download. No API key. No GPU.** 244,926 labelled transactions ship
with the repository.

Paste these three queries in order and watch the **execution trace** change:

| # | Paste this | What to look for |
|---|---|---|
| 1 | `Is customer 8000A7470 suspicious?` | Filters 245k rows down to a handful. Skips EDA, graph traversal and the ML layer — unnecessary for a single account. |
| 2 | `Find structuring patterns in the last 3 days` | Applies a date filter first, then runs **only** the structuring detector. Eight other detectors are listed as skipped, each with a stated reason. |
| 3 | `Which customers made 10+ transactions under $10,000?` | Answered by aggregation alone. **No ML, no detectors** — the agent recognises it doesn't need them. |

Three queries, three different execution paths through the same system. That
routing is the core of this submission.

> 💡 Then drag the **Sensitivity** slider in the sidebar from 1 to 4 and re-run
> the Full scan. Alert volume drops 99% while precision quadruples. That is the
> false-positive problem, made controllable.

---

## 🗂 Four tabs

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
explains every flag in analyst language, and provides a direct control for
trading recall against precision.

*Scope: retail and commercial transaction monitoring. Trade-based and securities
laundering require different data and are out of scope.*

---

## 🤖 What makes it agentic

The agent does **not** run a fixed pipeline. It parses intent, filters, entities
and target typology, then builds an execution plan that invokes only what the
question needs — and reports what it deliberately skipped.

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

Baseline: **4.7%** of accounts in the bundled slice are laundering-involved.
Reproduce everything below with `python -m evaluation.metrics`.

### Graph detectors reach near-perfect precision

| Detector | Flagged | True positives | Precision | Lift |
|---|---|---|---|---|
| cycle | 17 | 17 | **100%** | 21× |
| fan-in | 28 | 27 | **96%** | 21× |
| smurfing | 13 | 12 | **92%** | 20× |
| layering | 39 | 25 | **64%** | 14× |
| rapid cash-out | 907 | 184 | 20% | 4× |
| fan-out | 1,762 | 80 | 5% | 1× |
| ML anomaly | 123 | 4 | 3% | 0.7× |
| structuring | 697 | 19 | 3% | 0.6× |
| velocity | 2,576 | 59 | 2% | 0.5× |

Money laundering is a **network** crime. Graph-topology detectors — cycles,
fan-in, layering chains — massively outperform amount-based rules on this data,
because the laundering present is structural rather than threshold-based.
Row-wise scoring structurally cannot see it.

Rule detectors encode genuine regulatory typologies and would fire on cash
structuring; this dataset simply contains very little of it. Both layers are
retained deliberately.

### Confirmation ensemble

| Confirmations required | Accounts | True positives | Precision | Lift |
|---|---|---|---|---|
| 1+ | 4,173 | 279 | 6.7% | 1.4× |
| 2+ | 1,612 | 92 | 5.7% | 1.2× |
| 3+ | 336 | 44 | 13.1% | 2.8× |
| 4+ | 35 | 9 | **25.7%** | **5.5×** |

Requiring more independent confirmation cuts alert volume by 99% while
quadrupling precision. The sidebar sensitivity control moves along this curve
live.

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
   recognise, a language model emits a JSON spec (filters, group-by,
   aggregations), validated against an allowlist and executed by pandas.
   *The model proposes; the code decides.*
3. **Intent classifier** — final fallback for on-topic questions the spec
   format cannot express.

Out-of-scope questions are **refused explicitly** rather than answered wrongly.

</details>

<details>
<summary><b>Where the LLM sits — and doesn't →</b></summary>

<br>

The language model touches **intent parsing only**. It never sees transaction
rows, only the schema and category values.

Detection, scoring and explanations are **fully deterministic** — every flag is
reproducible and auditable. In compliance tooling, "the model said so" is not an
acceptable justification for a filing decision.

</details>

<details>
<summary><b>Detection layers →</b></summary>

<br>

| Layer | Detectors | Why |
|---|---|---|
| **Rules** | structuring, smurfing, velocity, rapid cash-out | encode known regulatory typologies |
| **Graph** | fan-in, fan-out, cycles, layering chains | laundering is a network crime; row-wise scoring can't see topology |
| **ML** | IsolationForest over account features | catches novel behaviour no rule encodes |

Risk is confirmation-weighted: an account triggering several independent
detectors scores far higher than one triggering a single weak signal.

</details>

---

## 💬 Queries that work with no API key

```
what can you do?
how many transactions
Is customer 8000A7470 suspicious?
Find structuring patterns in the last 3 days
Show me smurfing activity
Detect layering chains
Find fan-in patterns
Show me circular flows over $50,000
Which customers made 10+ transactions under $10,000?
Analyse this dataset for suspicious activity
```

These are **examples, not limits.** Any phrasing containing a typology keyword
routes correctly.

<details>
<summary><b>Full keyword vocabulary →</b></summary>

<br>

| Typology | Triggering keywords |
|---|---|
| structuring | structur, split, under the threshold, sub-threshold |
| smurfing | smurf, multiple depositors, many senders, mules |
| layering | layer, chain, hop, passed through, trace |
| rapid cash-out | cash-out, funnel, pass-through, immediate withdrawal |
| velocity | velocit, burst, spike, sudden, high frequency |
| fan-in | fan-in, converg, collection point, many to one |
| fan-out | fan-out, dispers, distribut, one to many |
| cycle | cycle, circular, round-trip, loop |

**Combinable filters:** `last N days` · `since 2022-09-05` · `before 2022-09-12`
· `under $10,000` · `over $50,000` · `N+ transactions` · currency names ·
`customer <id>`

</details>

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

**Bundled** — `data/sample/demo_transactions.csv`
244,926 transactions · 2,743 laundering-involved accounts · 16 days

Selected by **whole account history**, not random sampling — a random sample
fragments histories, so multi-transaction typologies cannot appear. Every
labelled laundering transaction in the selected accounts is retained. Selection
logic in `data/make_demo_slice.py`.

**Full dataset (optional)** —
[IBM Transactions for Anti-Money Laundering](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)

Download `HI-Small_Trans.csv` (high illicit rate) and optionally
`LI-Small_Trans.csv` (low illicit rate) into `data/raw/`, then select them from
the dataset dropdown — the same detectors tested at two different prevalence
levels.

All sources load through a canonical schema
(`timestamp, tx_id, sender, receiver, amount, currency, tx_type, is_laundering`).
Adding a new dataset requires only a mapping entry in `tools/loader.py`.

<details>
<summary><b>Preprocessing decisions →</b></summary>

<br>

**Institutional hubs excluded.** Accounts above 5,000 transactions in either
direction are banks or settlement nodes, not customers. They legitimately show
extreme velocity and constant pass-through and would dominate every detector.
Correspondent banking has separate controls in a real compliance programme.
**Label retention is reported on every filter**, so narrowing the population can
never silently destroy the ability to evaluate.

**Multi-currency thresholds.** A €9,200 transfer is not structuring against a
$10,000 threshold. Threshold typologies evaluate each transaction against its
own currency's reporting trigger — USD 10,000 (FinCEN CTR), EUR 10,000,
CNY 50,000. Cross-account comparisons normalise to `amount_usd` so behaviour is
not distorted by denomination. Cryptocurrency is excluded from threshold rules —
no equivalent cash-reporting trigger exists.

**Rule parameters.** Typology definitions follow FATF guidance. The $10,000
reference is the Bank Secrecy Act Currency Transaction Report threshold — the
requirement structuring exists to evade. Windows and counts were set from the
99th percentile of the observed population and stored in
`config/thresholds.json`.

</details>

---

## 🔧 Tech stack

`Python 3.10+` · `pandas` · `scikit-learn` · `networkx` · `streamlit` ·
`plotly` · optional `Groq` for intent parsing

**No database. No deployment. No model weights to download.**

---

## 📂 Structure

```
agent/       intent parsing, query spec, planning, execution
tools/       loader, filters, currency, features, rules, graph,
             anomaly, risk, explanation, EDA, visualisation
data/        bundled slice and its generator
evaluation/  metrics against labelled ground truth
config/      tuned detection thresholds
tests/       unit tests for detectors
```

Headless alternatives:

```bash
python run_cli.py
python -m evaluation.metrics
pytest tests/
```

---

<details>
<summary><b>⚠️ Limitations — stated honestly →</b></summary>

<br>

- Batch analysis; live stream ingestion is not implemented
- Layering search is bounded to the highest-value seed transactions;
  exhaustive path enumeration is out of scope for a batch prototype
- Smurfing uses fixed time bins, so a ring spanning a boundary may be missed
- Multi-step reasoning questions ("which accounts changed behaviour after the
  10th") cannot be expressed in the query spec format
- FX rates are static reference values, not time-of-transaction rates
- The activity filter removes roughly 20% of labelled laundering transactions;
  exact retention is printed at load time
- The bundled slice over-samples laundering accounts to keep the demo dense, so
  its 4.7% base rate is higher than the ~1% of the full dataset

**Roadmap:** stream ingestion behind the same tool interface · columnar storage
for larger-than-memory datasets · trade-based laundering module for investment
banking · analyst feedback loop to retune thresholds from dispositions

</details>

---

## 📚 Sources and disclosure

**Data** — IBM Transactions for Anti-Money Laundering (Kaggle), linked above

**Reference** — FATF money laundering typology definitions · FinCEN / Bank
Secrecy Act Currency Transaction Report threshold

**Libraries** — as listed in `requirements.txt`

**AI assistance** — an AI coding assistant was used for code scaffolding,
debugging and documentation drafting. Architecture decisions, detector design,
threshold tuning and evaluation were directed and verified by the author.

**Licence** — MIT