"""Query → structured intent. Regex-first so the system runs with no API key."""
from __future__ import annotations

import os
import re
from datetime import datetime

from agent.schemas import Intent, IntentType, Typology, Filters

TYPOLOGY_WORDS = {
    Typology.STRUCTURING: r"structur|split|under the (?:reporting )?threshold|sub-?threshold",
    Typology.SMURFING:    r"smurf|multiple depositors?|many senders?|mules?",
    Typology.LAYERING:    r"layer|chain|hop|pass(?:ed)? through|trace",
    Typology.RAPID_CASHOUT: r"cash[- ]?out|funnel|pass[- ]?through|immediate withdrawal",
    Typology.VELOCITY:    r"velocit|burst|spike|sudden|rapid activity|high frequency",
}

GRAPH_WORDS = {
    "fan_in":  r"fan[- ]?in|converg|collect(?:ion)? point|many to one",
    "fan_out": r"fan[- ]?out|dispers|distribut|one to many",
    "cycle":   r"cycle|circular|round[- ]?trip|loop|returns? to origin",
}

CAPABILITY = r"^\s*(what can you do|help|capabilities|commands|options)\s*\??\s*$"
EXPLAIN = r"why (?:was|is|were)|explain (?:the )?flag|reason for"

ACCOUNT_ID = r"\b(?:customer|account|acct|id)\s*(?:id\s*)?[:#]?\s*([A-Za-z]?\d{3,})\b"
BARE_ID = r"\b([A-F0-9]{6,9})\b"


def _num(text: str) -> float | None:
    cleaned = text.replace(",", "").replace("$", "").strip()
    if cleaned.endswith("k"):
        cleaned = cleaned[:-1] + "000"
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def parse_filters(q: str) -> Filters:
    f = Filters()
    ql = q.lower()

    m = re.search(r"last\s+(\d+)\s*(day|week|month)", ql)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        f.days_back = n * {"day": 1, "week": 7, "month": 30}[unit]
    elif re.search(r"last (?:month|30 days)", ql):
        f.days_back = 30
    elif re.search(r"last week", ql):
        f.days_back = 7

    m = re.search(r"(?:since|after|from)\s+(\d{4}-\d{2}-\d{2})", ql)
    if m:
        f.start_date = datetime.fromisoformat(m.group(1))
    m = re.search(r"(?:before|until|to)\s+(\d{4}-\d{2}-\d{2})", ql)
    if m:
        f.end_date = datetime.fromisoformat(m.group(1))

    m = re.search(r"(?:under|below|less than)\s*\$?\s*([\d,]+k?)", ql)
    if m:
        f.max_amount = _num(m.group(1))
    m = re.search(r"(?:over|above|more than|exceed(?:ing)?)\s*\$?\s*([\d,]+k?)", ql)
    if m:
        f.min_amount = _num(m.group(1))

    m = re.search(r"(\d+)\s*\+?\s*(?:or more\s*)?transactions?", ql)
    if m:
        f.min_count = int(m.group(1))

    for cur in ["us dollar", "dollar", "usd", "euro", "eur", "yuan",
                "pound", "yen", "bitcoin", "rupee"]:
        if re.search(rf"\b{cur}\b", ql):
            f.currency = {
                "usd": "US Dollar", "dollar": "US Dollar", "us dollar": "US Dollar",
                "eur": "Euro", "euro": "Euro", "yuan": "Yuan",
                "pound": "UK Pound", "yen": "Yen",
                "bitcoin": "Bitcoin", "rupee": "Rupee",
            }[cur]
            break

    return f


def parse_regex(query: str) -> Intent:
    q, ql = query.strip(), query.strip().lower()
    intent = Intent(raw_query=query, parser_used="regex")
    intent.filters = parse_filters(q)

    if re.match(CAPABILITY, ql):
        intent.intent_type = IntentType.CAPABILITY
        intent.confidence = 1.0
        return intent

    ids = re.findall(ACCOUNT_ID, q, flags=re.I)
    if not ids and re.search(r"customer|account", ql):
        ids = re.findall(BARE_ID, q)
    intent.entity_ids = ids

    if re.search(EXPLAIN, ql):
        intent.intent_type = IntentType.EXPLAIN_FLAG
        intent.confidence = 0.8

    if ids:
        intent.intent_type = IntentType.ENTITY_LOOKUP
        intent.confidence = 0.9

    for typ, pattern in TYPOLOGY_WORDS.items():
        if re.search(pattern, ql):
            intent.typology = typ
            if intent.intent_type == IntentType.UNKNOWN:
                intent.intent_type = IntentType.PATTERN_SEARCH
            intent.confidence = max(intent.confidence, 0.85)
            break

    for name, pattern in GRAPH_WORDS.items():
        if re.search(pattern, ql):
            intent.notes.append(f"graph_typology:{name}")
            if intent.intent_type == IntentType.UNKNOWN:
                intent.intent_type = IntentType.PATTERN_SEARCH
            intent.confidence = max(intent.confidence, 0.85)
            break

    if (intent.intent_type == IntentType.UNKNOWN
            and (intent.filters.min_count or intent.filters.max_amount
                 or intent.filters.min_amount)):
        intent.intent_type = IntentType.THRESHOLD_QUERY
        intent.confidence = 0.8

    if intent.intent_type == IntentType.UNKNOWN:
        if re.search(r"analys|analyz|overview|explore|profile|summar|"
                     r"suspicious activity|high[- ]risk|scan", ql):
            intent.intent_type = IntentType.BROAD_SCAN
            intent.confidence = 0.7

    if intent.intent_type == IntentType.UNKNOWN:
        intent.notes.append("no recognised intent")
        intent.confidence = 0.0

    return intent


def parse_llm(query: str) -> Intent | None:
    """Optional LLM refinement. Returns None if unavailable — never raises."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        import json
        import requests

        schema = {
            "intent_type": [e.value for e in IntentType],
            "typology": [t.value for t in Typology],
        }
        prompt = (
            "Extract AML query intent as JSON only, no prose. "
            f"Allowed values: {json.dumps(schema)}. "
            "Fields: intent_type, typology, entity_ids (list of strings), "
            "days_back (int or null), min_amount, max_amount, min_count, currency.\n"
            f"Query: {query}"
        )
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0,
                  "response_format": {"type": "json_object"}},
            timeout=8,
        )
        data = json.loads(r.json()["choices"][0]["message"]["content"])

        intent = Intent(raw_query=query, parser_used="llm", confidence=0.95)
        intent.intent_type = IntentType(data.get("intent_type", "unknown"))
        intent.typology = Typology(data.get("typology", "any"))
        intent.entity_ids = [str(x) for x in data.get("entity_ids", [])]
        intent.filters = Filters(
            days_back=data.get("days_back"),
            min_amount=data.get("min_amount"),
            max_amount=data.get("max_amount"),
            min_count=data.get("min_count"),
            currency=data.get("currency"),
        )
        return intent
    except Exception:
        return None


def parse(query: str, use_llm: bool = True) -> Intent:
    """LLM if available and confident, regex otherwise. Regex always works."""
    regex_intent = parse_regex(query)

    if use_llm and regex_intent.confidence < 0.85:
        llm_intent = parse_llm(query)
        if llm_intent and llm_intent.intent_type != IntentType.UNKNOWN:
            llm_intent.notes.append("regex fallback available")
            return llm_intent

    return regex_intent