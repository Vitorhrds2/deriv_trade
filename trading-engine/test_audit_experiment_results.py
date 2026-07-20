import json

from audit_experiment_results import (
    adjust_fdr,
    binary_test,
    discover_files,
    finite_profit,
    strategy_name,
)


def test_record_fields_are_normalized():
    assert strategy_name({"strategy": "A", "vector": "B"}) == "A"
    assert strategy_name({"vector": "B"}) == "B"
    assert finite_profit({"profit": "9.23"}) == 9.23
    assert finite_profit({"profit": None}) is None


def test_binary_test_infers_breakeven():
    result = binary_test([9.23] * 52 + [-10.0] * 48)
    assert result is not None
    assert result["wins"] == 52
    assert 0.51 < result["breakeven"] < 0.53


def test_fdr_adjustment_is_monotone():
    rows = [{"p": value} for value in (0.05, 0.001, 0.02, 0.9)]
    adjust_fdr(rows)
    ordered = sorted(rows, key=lambda row: row["p"])
    assert all(ordered[index]["q"] <= ordered[index + 1]["q"] for index in range(len(ordered) - 1))


def test_duplicate_files_are_removed(tmp_path):
    first = tmp_path / "d116_a.jsonl"
    second = tmp_path / "d116_b.jsonl"
    content = json.dumps({"profit": 1.0}) + "\n"
    first.write_text(content, encoding="utf-8")
    second.write_text(content, encoding="utf-8")
    files, duplicates = discover_files(tmp_path)
    assert len(files) == 1
    assert len(duplicates) == 1
