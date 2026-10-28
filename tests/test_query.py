import csv
import hashlib
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from cohort_lab.analysis import build_views
from cohort_lab.query import QueryRejected, run_query
from cohort_lab.workflow import LabWorkflow


@pytest.fixture(scope="module")
def query_lab(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    temporary = tmp_path_factory.mktemp("query-lab")
    data = temporary / "data"
    shutil.copytree(root / "data", data)
    output = temporary / "output"
    build_views(data, output)
    return data, output


def _new_receipt(output, before):
    after = set((output / "queries").glob("*/manifest.json"))
    created = after - before
    assert len(created) == 1
    path = created.pop()
    return path, json.loads(path.read_text())


def test_readonly_query_matches_independent_financial_sum_and_logs_exact_sql(query_lab):
    data, output = query_lab
    with (data / "transactions.csv").open(newline="", encoding="utf-8") as stream:
        expected = sum(Decimal(row["gross_amount"]) - Decimal(row["discount_amount"])
                       - Decimal(row["refund_amount"]) - Decimal(row["variable_cost"])
                       for row in csv.DictReader(stream))
    sql = "WITH ledger AS (SELECT gross_amount-discount_amount-refund_amount-variable_cost AS c FROM raw.transactions)\nSELECT sum(c) AS contribution FROM ledger;"
    result = run_query(data, output, sql)
    folder = output / "queries" / result["query_id"]
    with (folder / "result.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert Decimal(rows[0]["contribution"]) == expected
    assert (folder / "query.sql").read_text() == sql
    assert result["raw_input_hashes"]["transactions.csv"] == hashlib.sha256((data / "transactions.csv").read_bytes()).hexdigest()
    assert "enable_external_access=false" in (folder / "registration.sql").read_text()
    assert result["advanced"] is False


def test_query_does_not_advance_or_rewrite_guided_state(query_lab, monkeypatch):
    data, output = query_lab
    # Code-invalidation behavior has its own test; keep this query-isolation
    # test stable while other development agents edit unrelated model files.
    monkeypatch.setattr("cohort_lab.workflow.implementation_snapshot", lambda: {"fixture": "stable"})
    workflow = LabWorkflow(data, output, runner=lambda stage, *_: {"ready": True})
    workflow.start()
    for _ in range(3):
        workflow.handle_message("next")
    before = workflow.state_path.read_bytes()
    first = run_query(data, output, "SELECT cohort_month, cac FROM cohort_six_month_comparison ORDER BY cohort_month")
    second = run_query(data, output, "SELECT cohort_month, cac FROM cohort_six_month_comparison ORDER BY cohort_month")
    assert first["result_sha256"] == second["result_sha256"]
    assert workflow.state_path.read_bytes() == before
    assert workflow.status()["state"]["completed_stage"] == 3


@pytest.mark.parametrize("sql", [
    "DROP TABLE people", "UPDATE people SET region='west'", "CREATE TABLE new_table(x INTEGER)",
    "COPY (SELECT 1) TO 'bad.csv'", "ATTACH ':memory:' AS other", "INSTALL httpfs", "LOAD httpfs",
    "SELECT 1; SELECT 2", "PRAGMA version",
])
def test_mutation_multiple_statements_and_extensions_are_rejected_and_logged(query_lab, sql):
    data, output = query_lab
    before = set((output / "queries").glob("*/manifest.json"))
    with pytest.raises(QueryRejected, match="Only one SELECT"):
        run_query(data, output, sql)
    path, receipt = _new_receipt(output, before)
    assert receipt["status"] == "rejected"
    assert (path.parent / "query.sql").read_text() == sql
    assert not (path.parent / "result.csv").exists()


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('https://example.com/private.csv')",
    "SELECT * FROM \"read_csv\"('secret.csv')",
    "SELECT * FROM query('SELECT 1')",
    "SELECT * FROM read_text('secret.txt')",
    "SELECT * FROM 'secret.csv'",
])
def test_external_and_dynamic_reads_cannot_escape_registered_tables(query_lab, sql):
    data, output = query_lab
    with pytest.raises(QueryRejected):
        run_query(data, output, sql)


def test_modified_raw_file_fails_closed_and_logs_attempt(query_lab):
    data, output = query_lab
    path = data / "people.csv"
    original = path.read_bytes()
    before = set((output / "queries").glob("*/manifest.json"))
    try:
        path.write_bytes(original + b"corruption\n")
        with pytest.raises(QueryRejected, match="Modified frozen input"):
            run_query(data, output, "SELECT count(*) FROM people")
    finally:
        path.write_bytes(original)
    _, receipt = _new_receipt(output, before)
    assert receipt["status"] == "rejected"


def test_modified_derived_table_is_not_queried(query_lab):
    data, output = query_lab
    path = output / "tables" / "cohort_age_summary.csv"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"corruption\n")
        with pytest.raises(QueryRejected, match="Analysis table hash mismatch"):
            run_query(data, output, "SELECT count(*) FROM cohort_age_summary")
    finally:
        path.write_bytes(original)


def test_row_limit_rejects_instead_of_silently_truncating(query_lab):
    data, output = query_lab
    before = set((output / "queries").glob("*/manifest.json"))
    with pytest.raises(QueryRejected, match="Result exceeds the row limit"):
        run_query(data, output, "SELECT * FROM people LIMIT 4", max_rows=3)
    path, _ = _new_receipt(output, before)
    assert not (path.parent / "result.csv").exists()


def test_resource_bounded_query_is_interrupted(query_lab):
    data, output = query_lab
    with pytest.raises(QueryRejected, match="interrupt|timeout"):
        run_query(data, output, "SELECT sum(i) FROM range(1000000000000) t(i)", timeout_seconds=0.01)


def test_cli_accepts_stdin_for_verified_instructor_outputs(query_lab):
    data, output = query_lab
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "lab.py"), "--data", str(data), "--output", str(output),
                             "query", "--instructor"], input="SELECT count(*) AS n FROM raw.people;",
                            text=True, capture_output=True, check=True, cwd=root)
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "complete"
    assert receipt["row_count"] == 1
    assert receipt["advanced"] is False
