"""Local DuckDB SQL, validated source joins and deterministic teaching outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

import duckdb

from cohort_lab.data import SCHEMAS, validate_data

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SOURCE_SQL = ("01_views.sql", "02_friction.sql")
TABLE_SORTS = {
    "customer_month": "person_id, age_month",
    "cohort_age_summary": "cohort_month, channel, primary_need, age_month",
    "cohort_age_ex_tests": "cohort_month, channel, primary_need, age_month",
    "cohort_acquisition_costs": "cohort_month, channel, primary_need",
    "company_month": "calendar_month, cohort_month",
    "experiment_summary": "experiment_id, arm",
    "segmentation_comparison": "scheme",
    "segmentation_profile": "scheme, segment",
    "cohort_totals": "cohort_month, age_month",
    "cohort_cash_economics": "cohort_month, age_month",
    "company_totals": "calendar_month",
    "experiment_effects": "experiment_id",
    "cohort_six_month_comparison": "cohort_month",
    "cohort_economics_ex_tests": "cohort_month, age_month",
    "friction_subjects": "person_id",
    "friction_segment_summary": "scheme, segment",
    "friction_cohort_segments": "cohort_month, channel, primary_need, scheme, segment",
    "friction_cohort_summary": "cohort_month, primary_need",
    "friction_matched_comparison": "acquisition_year, channel, primary_need, scheme, segment",
    "friction_source_audit": "source, signal",
    "friction_timing_audit": "exposure_days",
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _json_value(value):
    if isinstance(value, Decimal): return float(value)
    if hasattr(value, "isoformat"): return value.isoformat()
    return value


def _records(con, query: str) -> list[dict]:
    result = con.execute(query)
    names = [d[0] for d in result.description]
    return [{name: _json_value(value) for name, value in zip(names, row)} for row in result.fetchall()]


def _source_sql(data_dir: Path, manifest: dict) -> str:
    lines = ["-- Executed source loading SQL; DuckDB is embedded locally, with no database server.",
             "SET threads=1;", "SET TimeZone='UTC';",
             f"CREATE OR REPLACE VIEW lab_settings AS SELECT TIMESTAMP {_quote(manifest['data_as_of'].replace('T',' ').replace('Z',''))} AS data_as_of;"]
    for name, columns in SCHEMAS.items():
        types = ", ".join(f"{_quote(k)}: {_quote(v)}" for k, v in columns.items())
        path = (data_dir / name).resolve().as_posix()
        lines.append(f"CREATE OR REPLACE VIEW {Path(name).stem} AS SELECT * FROM read_csv({_quote(path)}, header=true, columns={{{types}}}, nullstr='', strict_mode=true);")
    return "\n".join(lines) + "\n"


def _assert_analysis(con) -> dict:
    checks = {}
    assertions = {
        "customer_month_unique": "SELECT count(*) - count(DISTINCT (person_id, age_month)) FROM customer_month",
        "no_future_months": "SELECT count(*) FROM customer_month WHERE calendar_month >= (SELECT data_as_of FROM lab_settings)",
        "month_zero_coherent": "SELECT count(*) FROM cohort_age_summary WHERE age_month=0 AND (n_retained<>n_acquired OR n_paying<>n_acquired)",
        "retention_monotone": "SELECT count(*) FROM (SELECT n_retained, lag(n_retained) OVER (PARTITION BY cohort_month,channel,primary_need ORDER BY age_month) AS prev FROM cohort_age_summary) WHERE n_retained>prev",
        "positive_payment_cells": "SELECT count(*) FROM cohort_age_summary WHERE n_retained>0 AND gross_payment_revenue<=0",
        "observed_age_contiguous": "SELECT count(*) FROM (SELECT person_id,count(*) n,max(age_month)+1 expected FROM customer_month GROUP BY person_id) WHERE n<>expected",
        "ledger_revenue_reconciles": "SELECT (SELECT sum(net_revenue) FROM customer_month) - (SELECT sum(gross_amount-discount_amount-refund_amount) FROM transactions)",
        "ledger_cost_reconciles": "SELECT (SELECT sum(variable_cost) FROM customer_month) - (SELECT sum(variable_cost) FROM transactions)",
        "company_revenue_reconciles": "SELECT (SELECT sum(net_revenue) FROM company_totals) - (SELECT sum(net_revenue) FROM customer_month)",
        "company_spend_reconciles": "SELECT (SELECT sum(acquisition_spend) FROM company_totals) - (SELECT sum(media_spend+other_acquisition_spend) FROM campaign_spend)",
        "all_assigned_counted": "SELECT (SELECT sum(n_assigned) FROM experiment_summary) - (SELECT count(*) FROM experiment_assignments)",
        "one_spend_per_experiment": "SELECT (SELECT sum(media_spend) FROM experiment_summary) - (SELECT sum(media_spend) FROM experiment_spend)",
        "organic_CAC_unsupported": "SELECT count(*) FROM cohort_acquisition_costs WHERE channel IN ('organic','unknown') AND cac IS NOT NULL",
        "gross_minus_refunds_reconciles": "SELECT (SELECT sum(gross_payment_revenue-net_revenue) FROM customer_month) - (SELECT sum(refund_amount) FROM transactions)",
        "ex_test_customer_counts_reconcile": "SELECT count(*) FROM cohort_economics_ex_tests x JOIN cohort_cash_economics c USING (cohort_month,age_month) WHERE x.n_acquired+x.excluded_test_buyers<>c.n_acquired",
        "ex_test_cell_counts_reconcile": "SELECT count(*) FROM (SELECT cohort_month,age_month,sum(n_acquired) AS n_acquired,sum(n_retained) AS n_retained FROM cohort_age_ex_tests GROUP BY cohort_month,age_month) c JOIN cohort_economics_ex_tests x USING(cohort_month,age_month) WHERE c.n_acquired<>x.n_acquired OR c.n_retained<>x.n_retained",
        "ex_test_spending_reconciles": "SELECT count(*) FROM cohort_economics_ex_tests x JOIN cohort_cash_economics c USING (cohort_month,age_month) WHERE abs(x.acquisition_spend+x.excluded_test_spend-c.acquisition_spend)>0.000001",
        "friction_unique_customers": "SELECT count(*)-count(DISTINCT person_id) FROM friction_subjects",
        "friction_precedes_outcomes": "SELECT renewals_before_landmark+feature_window_violations+outcome_transactions_before_landmark FROM friction_timing_audit",
        "friction_no_experimental_buyers": "SELECT count(*) FROM friction_subjects f JOIN experiment_assignments x USING(person_id)",
        "friction_complete_denominators": "SELECT count(*) FROM (SELECT scheme,sum(n_acquired) n,sum(n_age5_observed) n5 FROM friction_segment_summary GROUP BY scheme) WHERE n<>(SELECT count(*) FROM friction_subjects) OR n5<>(SELECT count(*) FROM friction_subjects WHERE age5_observed)",
        "friction_future_outcomes_missing": "SELECT count(*) FROM friction_subjects WHERE NOT age5_observed AND (retained_age5 IS NOT NULL OR contribution_ages1_5 IS NOT NULL)",
    }
    for name, query in assertions.items():
        result = con.execute(query).fetchone()[0]
        result = 0 if result is None else result
        if abs(Decimal(str(result))) > Decimal("0.000001"):
            raise ValueError(f"SQL validation failed: {name} = {result}")
        checks[name] = "passed"
    return checks


def build_views(data_dir: Path, output_dir: Path) -> dict:
    """Validate frozen inputs, execute saved SQL, and export canonical sorted CSVs."""
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    source_validation = validate_data(data_dir)
    manifest = json.loads((data_dir / "data_manifest.json").read_text(encoding="utf-8"))
    tables, executed = output_dir / "tables", output_dir / "sql"
    tables.mkdir(parents=True, exist_ok=True)
    executed.mkdir(parents=True, exist_ok=True)
    load_sql = _source_sql(data_dir, manifest)
    (executed / "00_sources.sql").write_text(load_sql, encoding="utf-8", newline="\n")
    view_sql = {name: (SQL_DIR / name).read_text(encoding="utf-8") for name in SOURCE_SQL}
    for name, sql in view_sql.items():
        (executed / name).write_text(sql, encoding="utf-8", newline="\n")
    con = duckdb.connect(":memory:")
    try:
        con.execute(load_sql)
        for sql in view_sql.values():
            con.execute(sql)
        checks = _assert_analysis(con)
        select_sql = []
        for name, order in TABLE_SORTS.items():
            query = f"SELECT * FROM {name} ORDER BY {order}"
            select_sql.append(query + ";")
            result = con.execute(query)
            columns = [c[0] for c in result.description]
            with (tables / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(columns)
                for row in result.fetchall():
                    writer.writerow(["" if v is None else v.isoformat() if hasattr(v, "isoformat") else v for v in row])
        (executed / "02_exports.sql").write_text("\n\n".join(select_sql) + "\n", encoding="utf-8", newline="\n")
        summary_queries = {
            "cohort_overview": "SELECT cohort_month,n_acquired,acquisition_spend,cac,observed_months,first_observed_payback_age,cash_payback_month FROM cohort_cash_economics WHERE age_month=0 ORDER BY cohort_month",
            "six_month_comparison": "SELECT cohort_month,n_acquired,retained_share,revenue_retention,cac,cumulative_contribution_per_customer,balance_per_customer FROM cohort_six_month_comparison ORDER BY cohort_month",
            "experiment_effects": "SELECT * FROM experiment_effects ORDER BY experiment_id",
            "segmentation": "SELECT * FROM segmentation_comparison ORDER BY scheme",
        }
        summaries = {key: _records(con, query) for key, query in summary_queries.items()}
        (executed / "03_summary.sql").write_text("\n\n".join(q + ";" for q in summary_queries.values()) + "\n", encoding="utf-8", newline="\n")
        row_counts = {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in TABLE_SORTS}
    finally:
        con.close()
    summary = {
        "schema_version": "1.0", "data_as_of": manifest["data_as_of"], "timezone": manifest["timezone"],
        "currency": manifest["currency"], "definitions": manifest["definitions"],
        "source_validation": source_validation, "sql_checks": checks, "table_row_counts": row_counts,
        "experiment_interval": "Approximate 95% normal intervals: purchase-rate differences use unpooled Bernoulli standard errors; contribution-after-media per prospect uses sqrt(s_T^2/n_T+s_C^2/n_C), with sample contribution variances over every assigned person including nonbuyers with zero outcomes. Recorded media spending is treated as fixed and changes the mean, not its standard error. Total-pilot contribution intervals scale the per-prospect interval by n_T. Each experiment retains its own controls and explicit assignment/follow-up dates; windows can differ. These are not long-run LTV intervals, do not include cost uncertainty, and have no correction for comparing different tests.",
        "segmentation_scope": "The same paid customers with six complete observed acquisition-age months, excluding both experiment arms. Four baseline schemes each have two groups; outcome is six-receipt contribution including zeros after churn. Variance reduction compares with the pooled outcome. A second comparison centers outcomes by joining month before grouping. Both are descriptive discrimination, not treatment effects.",
        "friction_scope": "Post-acquisition diagnostic groups use [first payment, first payment + 27 days), with complete exposure and both experimental arms excluded. First-renewal retention is primary; age-5 retention and ages1–5 contribution are secondary, including zeros after exit and original-customer denominators. No recorded survey response and unanswered difficulty items remain distinct. Timing assertions verify first renewals and outcome transactions follow the window. Refunds are retained and separately flagged; their presence does not establish exit. Cancellation-request times are unavailable. No diagnostic feature enters the valuation model; no acquisition spending is allocated to these groups.",
        "money": "Source amounts are integer cents rendered as decimal money. DuckDB monetary sums use DECIMAL. Ratios and statistical quantities use floating point.",
        **summaries,
    }
    (output_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    input_manifest = {"data_manifest_sha256": _hash(data_dir / "data_manifest.json"), "files": manifest["files"]}
    (output_dir / "analysis_input_manifest.json").write_text(json.dumps(input_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "schema_version": "1.0", "input_data_manifest_sha256": _hash(data_dir / "data_manifest.json"),
        "input_csv_hashes": {name: spec["sha256"] for name, spec in manifest["files"].items()},
        "source_sql_hashes": {name: _hash(SQL_DIR / name) for name in SOURCE_SQL},
        "executed_sql_hashes": {p.name: _hash(p) for p in sorted(executed.glob("*.sql"))},
        "output_table_hashes": {f"{name}.csv": _hash(tables / f"{name}.csv") for name in TABLE_SORTS},
        "summary_sha256": _hash(output_dir / "analysis_summary.json"),
        "input_receipt_sha256": _hash(output_dir / "analysis_input_manifest.json"),
        "analysis_code_sha256": _hash(Path(__file__)), "duckdb_version": duckdb.__version__,
    }
    (output_dir / "analysis_manifest.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_analysis(output_dir)
    return summary


def validate_analysis(output_dir: Path) -> dict:
    """Refuse mutated SQL-derived model/report inputs before downstream work."""
    output_dir = Path(output_dir)
    path = output_dir / "analysis_manifest.json"
    if not path.is_file(): raise ValueError("Missing analysis_manifest.json; build verified SQL views first.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if set(manifest.get("output_table_hashes", {})) != {f"{name}.csv" for name in TABLE_SORTS}:
        raise ValueError("Unexpected analysis output contract.")
    for filename, expected in manifest["output_table_hashes"].items():
        p = output_dir / "tables" / filename
        if not p.is_file() or _hash(p) != expected:
            raise ValueError(f"Analysis table hash mismatch: {filename}. Rebuild from frozen inputs.")
    for filename, expected in manifest.get("executed_sql_hashes", {}).items():
        p = output_dir / "sql" / filename
        if not p.is_file() or _hash(p) != expected: raise ValueError(f"Executed SQL hash mismatch: {filename}")
    for filename, key in [("analysis_summary.json", "summary_sha256"), ("analysis_input_manifest.json", "input_receipt_sha256")]:
        p = output_dir / filename
        if not p.is_file() or _hash(p) != manifest.get(key): raise ValueError(f"Analysis receipt hash mismatch: {filename}")
    if manifest.get("source_sql_hashes", {}) != {name: _hash(SQL_DIR / name) for name in SOURCE_SQL}:
        raise ValueError("Analysis SQL changed since tables were built; rebuild verified views.")
    if manifest.get("analysis_code_sha256") != _hash(Path(__file__)):
        raise ValueError("Analysis code changed since tables were built; rebuild verified views.")
    return {"status": "passed", "tables_checked": len(TABLE_SORTS), "analysis_manifest_sha256": _hash(path)}
