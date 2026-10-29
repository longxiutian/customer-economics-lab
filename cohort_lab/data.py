"""Public source schemas and validation for the frozen analytical release.

Data generation and future outcomes are maintained outside the student
repository. This module validates observed records; it cannot simulate them.
"""
from __future__ import annotations
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

DATA_AS_OF = "2026-01-01T00:00:00Z"
SCHEMA_VERSION = "2.0"
DATASET_VERSION = "3.0"

SCHEMAS = {
    "people.csv": {
        "person_id": "VARCHAR", "record_created_at": "TIMESTAMP", "attributes_recorded_at": "TIMESTAMP",
        "age_band": "VARCHAR", "household_type": "VARCHAR", "primary_need": "VARCHAR", "region": "VARCHAR"},
    "subscription_periods.csv": {
        "period_id": "VARCHAR", "subscription_id": "VARCHAR", "person_id": "VARCHAR", "period_start": "DATE",
        "period_end": "DATE", "renewal_due_at": "TIMESTAMP", "renewal_outcome": "VARCHAR",
        "cancellation_effective_at": "TIMESTAMP", "plan_tier": "VARCHAR"},
    "transactions.csv": {
        "transaction_id": "VARCHAR", "person_id": "VARCHAR", "period_id": "VARCHAR", "occurred_at": "TIMESTAMP",
        "transaction_type": "VARCHAR", "related_transaction_id": "VARCHAR", "order_id": "VARCHAR",
        "charge_type": "VARCHAR", "quantity": "INTEGER", "unit_price": "DECIMAL(12,2)",
        "gross_amount": "DECIMAL(12,2)", "discount_amount": "DECIMAL(12,2)",
        "refund_amount": "DECIMAL(12,2)", "variable_cost": "DECIMAL(12,2)"},
    "product_events.csv": {
        "event_id": "VARCHAR", "person_id": "VARCHAR", "occurred_at": "TIMESTAMP", "event_type": "VARCHAR", "platform": "VARCHAR"},
    "feedback.csv": {
        "response_id": "VARCHAR", "person_id": "VARCHAR", "submitted_at": "TIMESTAMP", "journey_stage": "VARCHAR",
        "ease_rating": "INTEGER", "value_rating": "INTEGER", "main_difficulty": "VARCHAR"},
    "campaign_spend.csv": {
        "campaign_id": "VARCHAR", "spend_date": "DATE", "channel": "VARCHAR", "target_need": "VARCHAR",
        "media_spend": "DECIMAL(12,2)", "other_acquisition_spend": "DECIMAL(12,2)"},
    "acquisition_attribution.csv": {
        "person_id": "VARCHAR", "first_paid_transaction_id": "VARCHAR", "credited_campaign_id": "VARCHAR",
        "source_type": "VARCHAR", "attribution_rule": "VARCHAR", "credited_at": "TIMESTAMP"},
    "experiment_assignments.csv": {
        "experiment_id": "VARCHAR", "person_id": "VARCHAR", "tested_campaign_id": "VARCHAR",
        "assigned_at": "TIMESTAMP", "arm": "VARCHAR", "followup_end_at": "TIMESTAMP"},
}
PRIMARY_KEYS = {
    "people.csv": ["person_id"], "subscription_periods.csv": ["period_id"],
    "transactions.csv": ["transaction_id"], "product_events.csv": ["event_id"],
    "feedback.csv": ["response_id"], "campaign_spend.csv": ["campaign_id", "spend_date"],
    "acquisition_attribution.csv": ["person_id"], "experiment_assignments.csv": ["experiment_id", "person_id"],
}
NULLABLE = {
    "subscription_periods.csv": {"cancellation_effective_at"},
    "transactions.csv": {"related_transaction_id", "quantity", "unit_price"},
    "feedback.csv": {"ease_rating", "value_rating", "main_difficulty"},
    "campaign_spend.csv": {"target_need"}, "acquisition_attribution.csv": {"credited_campaign_id"},
}
GRAINS = {
    "people.csv": "One person, including eligible prospects who never purchase.",
    "subscription_periods.csv": "One scheduled monthly cycle; a paid outcome establishes retained membership for that cycle.",
    "transactions.csv": "One payment or refund event; each payment is one order and refunds reuse its order ID.",
    "product_events.csv": "One observed product/support interaction; no event does not mean no subscription.",
    "feedback.csv": "One completed linked survey response; nonresponse is missing, not a zero rating.",
    "campaign_spend.csv": "One campaign per spending date; aggregate before joining to customer outcomes.",
    "acquisition_attribution.csv": "One acquired person and the recorded credit for the first successful payment.",
    "experiment_assignments.csv": "One eligible person per randomized experiment, including all nonbuyers.",
}



def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_data(data_dir: Path) -> dict:
    """Fail closed on changed exports, then check independent source invariants."""
    data_dir = Path(data_dir)
    manifest_path = data_dir / "data_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Missing data_manifest.json; use the complete frozen dataset release.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or set(manifest.get("files", {})) != set(SCHEMAS):
        raise ValueError("Unsupported schema or unexpected set of source files.")
    cutoff = datetime.fromisoformat(manifest["data_as_of"].replace("Z", "+00:00")).replace(tzinfo=None)
    rows = {}
    for name, fields in SCHEMAS.items():
        path = data_dir / name
        if not path.is_file() or _digest(path) != manifest["files"][name]["sha256"]:
            raise ValueError(f"Input hash mismatch: {name}. Restore the frozen source before proceeding.")
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(fields):
                raise ValueError(f"Unexpected columns: {name}")
            data = list(reader)
        if len(data) != manifest["files"][name]["row_count"]:
            raise ValueError(f"Row count mismatch: {name}")
        keys = [tuple(r[k] for k in PRIMARY_KEYS[name]) for r in data]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate primary key: {name}")
        for r in data:
            for field, kind in fields.items():
                value = r[field]
                if not value:
                    if field not in NULLABLE.get(name, set()):
                        raise ValueError(f"Missing required {name}.{field}")
                    continue
                try:
                    if kind == "INTEGER": int(value)
                    elif kind == "DATE": date.fromisoformat(value)
                    elif kind == "TIMESTAMP": datetime.fromisoformat(value)
                    elif kind.startswith("DECIMAL"):
                        amount = Decimal(value)
                        if not amount.is_finite() or amount.as_tuple().exponent < -2 or amount < 0:
                            raise ValueError("Invalid nonnegative cent amount")
                except (ValueError, ArithmeticError) as exc:
                    raise ValueError(f"Invalid {name}.{field}: {value!r}") from exc
        rows[name] = data
    people = {r["person_id"]: r for r in rows["people.csv"]}
    periods = {r["period_id"]: r for r in rows["subscription_periods.csv"]}
    tx = {r["transaction_id"]: r for r in rows["transactions.csv"]}
    campaigns = defaultdict(list)
    for r in rows["campaign_spend.csv"]:
        if datetime.fromisoformat(r["spend_date"]) >= cutoff:
            raise ValueError("Future campaign spending is not observed.")
        campaigns[r["campaign_id"]].append(r)
    for cid, cost in campaigns.items():
        if len({(r["channel"], r["target_need"], r["spend_date"][:7]) for r in cost}) != 1:
            raise ValueError(f"Campaign channel, target or acquisition month changes: {cid}")
    for name in SCHEMAS:
        if name == "people.csv" or "person_id" not in SCHEMAS[name]: continue
        for r in rows[name]:
            if r["person_id"] not in people:
                raise ValueError(f"Unknown person in {name}")
    for p in people.values():
        if p["record_created_at"] > p["attributes_recorded_at"]:
            raise ValueError("Attributes precede CRM record creation.")
    by_person = defaultdict(list)
    for p in periods.values():
        if p["renewal_outcome"] not in {"paid", "cancelled", "failed", "pending"}:
            raise ValueError("Invalid renewal outcome.")
        if p["period_start"] >= p["period_end"]:
            raise ValueError("Invalid subscription period.")
        due = datetime.fromisoformat(p["renewal_due_at"])
        if (p["renewal_outcome"] == "pending") != (due >= cutoff):
            raise ValueError("Pending/observed renewal disagrees with data cutoff.")
        by_person[p["person_id"]].append(p)
    for pid, history in by_person.items():
        history.sort(key=lambda p: p["period_start"])
        if len({p["subscription_id"] for p in history}) != 1:
            raise ValueError("More than one subscription per person.")
        if len({p["period_start"][:7] for p in history}) != len(history):
            raise ValueError("Duplicate person subscription month.")
        ended = False
        for p in history:
            if ended and p["renewal_outcome"] == "paid": raise ValueError("Undocumented reactivation.")
            if p["renewal_outcome"] in {"cancelled", "failed"}: ended = True
    payments_by_person = defaultdict(list)
    paid_periods = Counter()
    order_payments = set()
    refunds = defaultdict(Decimal)
    for t in tx.values():
        p = periods.get(t["period_id"])
        if not p or p["person_id"] != t["person_id"]:
            raise ValueError("Payment/period person mismatch.")
        when = datetime.fromisoformat(t["occurred_at"])
        if when >= cutoff or t["occurred_at"][:7] != p["period_start"][:7]:
            raise ValueError("Financial event outside observed cycle/month.")
        gross, discount, refund, cost = [Decimal(t[k]) for k in ("gross_amount", "discount_amount", "refund_amount", "variable_cost")]
        if t["transaction_type"] == "payment":
            if p["renewal_outcome"] != "paid" or t["related_transaction_id"] or refund or not t["quantity"] or not t["unit_price"]:
                raise ValueError("Malformed successful payment.")
            if int(t["quantity"]) <= 0 or gross != int(t["quantity"]) * Decimal(t["unit_price"]) or gross <= discount:
                raise ValueError("Payment quantity/price/discount does not reconcile.")
            if t["order_id"] in order_payments: raise ValueError("Duplicate paid order.")
            order_payments.add(t["order_id"])
            payments_by_person[t["person_id"]].append(t)
            if t["charge_type"] == "subscription": paid_periods[t["period_id"]] += 1
        elif t["transaction_type"] == "refund":
            original = tx.get(t["related_transaction_id"])
            if not original or original["transaction_type"] != "payment": raise ValueError("Refund has no original payment.")
            if any(t[k] != original[k] for k in ["person_id", "period_id", "order_id", "charge_type"]): raise ValueError("Refund identity mismatch.")
            if gross or discount or cost or t["quantity"] or t["unit_price"] or refund <= 0 or t["occurred_at"] < original["occurred_at"]:
                raise ValueError("Refund duplicates payment/cost or has invalid timing.")
            refunds[t["related_transaction_id"]] += refund
        else: raise ValueError("Unknown financial transaction type.")
        if t["charge_type"] not in {"subscription", "add_on"}: raise ValueError("Unknown charge type.")
    for tid, amount in refunds.items():
        if amount > Decimal(tx[tid]["gross_amount"]) - Decimal(tx[tid]["discount_amount"]): raise ValueError("Refund exceeds payment.")
    for p in periods.values():
        if (paid_periods[p["period_id"]] == 1) != (p["renewal_outcome"] == "paid"):
            raise ValueError("Paid membership and subscription payment do not reconcile.")
    attribution = {a["person_id"]: a for a in rows["acquisition_attribution.csv"]}
    if set(attribution) != set(payments_by_person): raise ValueError("Acquired people and attribution coverage disagree.")
    firsts = {}
    for pid, payments in payments_by_person.items():
        first = min(payments, key=lambda t: (t["occurred_at"], t["transaction_id"]))
        firsts[pid] = first
        a = attribution[pid]
        if a["first_paid_transaction_id"] != first["transaction_id"]: raise ValueError("Attributed acquisition is not first payment.")
        if people[pid]["attributes_recorded_at"] >= first["occurred_at"]: raise ValueError("Baseline attributes are not pre-acquisition.")
        cid = a["credited_campaign_id"]
        if cid:
            if cid not in campaigns or a["source_type"] != "paid_campaign": raise ValueError("Unknown credited campaign.")
            campaign = campaigns[cid][0]
            if campaign["target_need"] and campaign["target_need"] != people[pid]["primary_need"]: raise ValueError("Campaign target and baseline need disagree.")
            if campaign["spend_date"][:7] != first["occurred_at"][:7]: raise ValueError("Cross-month attribution requires an allocation rule.")
        elif a["source_type"] not in {"organic", "unknown"}: raise ValueError("Unsupported unattributed source type.")
    for name, timestamp in [("product_events.csv", "occurred_at"), ("feedback.csv", "submitted_at")]:
        for r in rows[name]:
            if datetime.fromisoformat(r[timestamp]) >= cutoff: raise ValueError("Future product/feedback observation.")
    experiments = defaultdict(list)
    assigned_people = set()
    for r in rows["experiment_assignments.csv"]:
        pid = r["person_id"]
        if pid in assigned_people: raise ValueError("Overlapping experiments are not part of this dataset.")
        assigned_people.add(pid)
        if r["arm"] not in {"treatment", "control"}: raise ValueError("Invalid randomized arm.")
        if people[pid]["attributes_recorded_at"] >= r["assigned_at"] or people[pid]["record_created_at"] >= r["assigned_at"]:
            raise ValueError("Experiment eligibility was not established before assignment.")
        if r["assigned_at"] >= r["followup_end_at"] or datetime.fromisoformat(r["followup_end_at"]) > cutoff:
            raise ValueError("Invalid or immature experiment window.")
        if pid in firsts and firsts[pid]["occurred_at"] <= r["assigned_at"]: raise ValueError("Experiment includes a prior buyer.")
        if r["tested_campaign_id"] not in campaigns: raise ValueError("Unknown experiment campaign.")
        campaign = campaigns[r["tested_campaign_id"]][0]
        if campaign["target_need"] != people[pid]["primary_need"]: raise ValueError("Experiment target mismatch.")
        experiments[r["experiment_id"]].append(r)
    for group in experiments.values():
        if len({(r["tested_campaign_id"], r["assigned_at"], r["followup_end_at"]) for r in group}) != 1:
            raise ValueError("Experiment has inconsistent campaign or followup.")
        if {r["arm"] for r in group} != {"treatment", "control"}: raise ValueError("Experiment is missing its own control.")
    return {"status": "passed", "files_checked": len(SCHEMAS), "row_counts": {k: len(v) for k, v in rows.items()},
            "acquired_people": len(firsts), "eligible_experiment_people": len(assigned_people),
            "manifest_sha256": _digest(manifest_path)}
