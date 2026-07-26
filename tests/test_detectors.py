import pandas as pd
import pytest
from tools.rules import detect_structuring
from tools.graph import detect_fan_in, detect_cycles


def make_df(rows):
    df = pd.DataFrame(rows, columns=["timestamp", "tx_id", "sender",
                                     "receiver", "amount", "currency",
                                     "tx_type", "is_laundering"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def test_structuring_fires_on_planted_pattern():
    rows = [(f"2024-01-0{i+1}", f"t{i}", "A", "B", 9200, "US Dollar", "Cash", 1)
            for i in range(4)]
    hits = detect_structuring(make_df(rows))
    assert len(hits) == 1
    assert hits[0]["account"] == "A"
    assert hits[0]["count"] >= 3


def test_structuring_ignores_large_amounts():
    rows = [(f"2024-01-0{i+1}", f"t{i}", "A", "B", 50000, "US Dollar", "Wire", 0)
            for i in range(4)]
    assert detect_structuring(make_df(rows)) == []


def test_structuring_ignores_spread_out_transactions():
    rows = [(f"2024-0{i+1}-01", f"t{i}", "A", "B", 9200, "US Dollar", "Cash", 0)
            for i in range(4)]  # months apart
    assert detect_structuring(make_df(rows)) == []


def test_fan_in_fires():
    rows = [("2024-01-01", f"t{i}", f"S{i}", "HUB", 5000, "US Dollar", "ACH", 1)
            for i in range(10)]
    hits = detect_fan_in(make_df(rows))
    assert any(h["account"] == "HUB" for h in hits)


def test_cycle_detected():
    rows = [("2024-01-01", "t1", "A", "B", 10000, "US Dollar", "Wire", 1),
            ("2024-01-02", "t2", "B", "C", 10000, "US Dollar", "Wire", 1),
            ("2024-01-03", "t3", "C", "A", 10000, "US Dollar", "Wire", 1)]
    hits = detect_cycles(make_df(rows))
    assert len(hits) >= 1
    assert hits[0]["hops"] == 3