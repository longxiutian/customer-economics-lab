"""Logged, bounded, read-only SQL exploration after the canonical analysis stage."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path

import duckdb

from .analysis import validate_analysis
from .data import SCHEMAS
from .workflow import InputIntegrityError, WorkflowError, implementation_snapshot, verify_frozen_inputs


class QueryRejected(WorkflowError):
    pass


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _check_sql(connection, sql: str) -> None:
    if not sql.strip() or len(sql.encode("utf-8")) > 65536:
        raise QueryRejected("Supply one nonempty SELECT statement of at most 64 KiB.")
    try:
        statements = connection.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryRejected(f"SQL could not be parsed: {exc}") from exc
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise QueryRejected("Only one SELECT statement is allowed; WITH ... SELECT is supported.")
    # The engine's disabled external access is the security boundary. This
    # additional check gives clear feedback for common external/dynamic calls.
    tokens = re.sub(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'", " ", sql, flags=re.S).replace('"', '')
    functions = {name.casefold() for name in re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*)\s*\(", tokens)}
    denied = sorted(name for name in functions if name.startswith(("read_", "write_", "http_"))
                    or name.endswith("_scan") or name in {"glob", "query", "query_table", "sqlite_attach", "nextval", "setval", "setseed"})
    if denied:
        raise QueryRejected("External, dynamic, or state-changing functions are unavailable: " + ", ".join(denied))


def run_query(data_dir: Path, output_dir: Path, sql: str, *, max_rows: int = 10000,
              timeout_seconds: float = 20.0) -> dict:
    """Execute a single SELECT against verified in-memory lab tables.

    This helper does not advance or rewrite guided state. The CLI checks the
    stage gate first; the helper also requires a validated analysis manifest.
    """
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    query_id = uuid.uuid4().hex
    folder = output_dir / "queries" / query_id
    folder.mkdir(parents=True, exist_ok=False)
    query_path = folder / "query.sql"
    query_path.write_text(sql, encoding="utf-8", newline="")
    receipt = {"query_id": query_id, "status": "started", "sql_sha256": _hash(query_path),
               "duckdb_version": duckdb.__version__, "max_rows": max_rows,
               "timeout_seconds": timeout_seconds, "advanced": False,
               "implementation_hashes": implementation_snapshot(),
               "memory_limit": "512MB", "threads": 1, "timezone": "UTC"}
    connection = None
    timer = None
    expired = threading.Event()
    try:
        if not 1 <= max_rows <= 50000 or not 0 < timeout_seconds <= 60:
            raise QueryRejected("Choose 1–50,000 rows and a timeout above zero and at most 60 seconds.")
        snapshot = verify_frozen_inputs(data_dir)
        receipt["raw_input_hashes"] = snapshot["hashes"]
        validate_analysis(output_dir)
        analysis = json.loads((output_dir / "analysis_manifest.json").read_text(encoding="utf-8"))
        if analysis["input_data_manifest_sha256"] != snapshot["hashes"]["data_manifest.json"]:
            raise InputIntegrityError("The saved analysis was built from a different data manifest.")
        receipt["analysis_manifest_sha256"] = _hash(output_dir / "analysis_manifest.json")
        table_files = dict(analysis["output_table_hashes"])
        if (output_dir / "model_manifest.json").exists():
            from .report import _validate_model_outputs
            _validate_model_outputs(output_dir)
            model = json.loads((output_dir / "model_manifest.json").read_text(encoding="utf-8"))
            receipt["model_manifest_sha256"] = _hash(output_dir / "model_manifest.json")
            table_files.update({Path(name).name: digest for name, digest in model["output_hashes"].items()
                                if name.startswith("tables/") and name.endswith(".csv")})
        receipt["analytical_table_hashes"] = table_files
        connection = duckdb.connect(":memory:", config={"threads": 1, "memory_limit": "512MB",
                                                          "autoload_known_extensions": False,
                                                          "autoinstall_known_extensions": False})
        _check_sql(connection, sql)
        registration = ["SET TimeZone='UTC';", "CREATE SCHEMA raw;"]
        connection.execute("SET TimeZone='UTC'; CREATE SCHEMA raw;")
        for filename, columns in SCHEMAS.items():
            name = Path(filename).stem
            types = ", ".join(f"{_literal(key)}: {_literal(kind)}" for key, kind in columns.items())
            load = f"CREATE TABLE raw.{name} AS SELECT * FROM read_csv({_literal((data_dir / filename).as_posix())}, header=true, columns={{{types}}}, nullstr='', strict_mode=true);"
            connection.execute(load)
            registration.append(load)
            alias = f"CREATE VIEW {name} AS SELECT * FROM raw.{name};"
            connection.execute(alias)
            registration.append(alias)
        for filename in sorted(table_files):
            name = Path(filename).stem
            if not re.fullmatch(r"[a-z_][a-z_0-9]*", name):
                raise QueryRejected("Unexpected analytical table name.")
            load = f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto({_literal((output_dir / 'tables' / filename).as_posix())}, header=true, sample_size=-1, nullstr='');"
            connection.execute(load)
            registration.append(load)
        lock = "SET enable_external_access=false; SET lock_configuration=true;"
        connection.execute(lock)
        registration.append(lock)
        (folder / "registration.sql").write_text("\n".join(registration) + "\n", encoding="utf-8", newline="\n")
        receipt["registered_relations"] = sorted([Path(name).stem for name in SCHEMAS] + [Path(name).stem for name in table_files])
        def interrupt():
            expired.set()
            connection.interrupt()

        timer = threading.Timer(timeout_seconds, interrupt)
        timer.daemon = True
        timer.start()
        result = connection.execute(sql)
        columns = [entry[0] for entry in result.description]
        rows = result.fetchmany(max_rows + 1)
        timer.cancel()
        if expired.is_set():
            raise QueryRejected("Query exceeded the configured timeout; no partial result is presented.")
        if len(rows) > max_rows:
            raise QueryRejected("Result exceeds the row limit. Narrow or aggregate the query; no silently truncated result is presented.")
        result_path = folder / "result.csv"
        with result_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows([["" if value is None else value.isoformat() if hasattr(value, "isoformat") else value for value in row] for row in rows])
        receipt.update(status="complete", row_count=len(rows), columns=columns, result_sha256=_hash(result_path),
                       artifacts=[f"queries/{query_id}/query.sql", f"queries/{query_id}/registration.sql",
                                  f"queries/{query_id}/result.csv", f"queries/{query_id}/manifest.json"])
        return receipt
    except Exception as exc:
        if expired.is_set():
            exc = QueryRejected("Query exceeded the configured timeout; no partial result is presented.")
        receipt.update(status="rejected" if isinstance(exc, (QueryRejected, InputIntegrityError, ValueError)) else "failed",
                       error=str(exc))
        raise QueryRejected(f"{exc} Query receipt: queries/{query_id}/manifest.json") from exc
    finally:
        if timer:
            timer.cancel()
            timer.join(timeout=1)
        if connection:
            connection.close()
        (folder / "manifest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
