from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class IntentType(str, Enum):
    BROAD_SCAN = "broad_scan"
    PATTERN_SEARCH = "pattern_search"
    THRESHOLD_QUERY = "threshold_query"
    ENTITY_LOOKUP = "entity_lookup"
    EXPLAIN_FLAG = "explain_flag"
    CAPABILITY = "capability"
    UNKNOWN = "unknown"
    GENERIC_ANALYSIS = "generic_analysis"
    DATA_SUMMARY = "data_summary"


class Typology(str, Enum):
    STRUCTURING = "structuring"
    SMURFING = "smurfing"
    LAYERING = "layering"
    RAPID_CASHOUT = "rapid_cashout"
    VELOCITY = "velocity"
    ANY = "any"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Filters:
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days_back: Optional[int] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    min_count: Optional[int] = None


@dataclass
class Intent:
    raw_query: str
    intent_type: IntentType = IntentType.UNKNOWN
    typology: Typology = Typology.ANY
    entity_ids: list[str] = field(default_factory=list)
    filters: Filters = field(default_factory=Filters)
    confidence: float = 0.0
    parser_used: str = "regex"
    notes: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    tool: str
    reason: str
    rows_in: int = 0
    rows_out: int = 0
    duration_ms: float = 0.0


@dataclass
class ExecutionPlan:
    intent: Intent
    steps: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Flag:
    entity_id: str
    transaction_ids: list[str]
    typology: Typology
    score: float
    risk: RiskLevel
    explanation: str
    action: str
    evidence: dict = field(default_factory=dict)