"""Original, deterministic synthetic source exports for a subscription business.

Generation uses integer cents.  The eight exports are ordinary source records,
not precomputed answers.  Nothing in this module requires a network connection.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

DEFAULT_SEED = 20261116
DATA_AS_OF = "2026-01-01T00:00:00Z"
SCHEMA_VERSION = "2.0"
DATASET_VERSION = "2.0"

# These are simulation assumptions, not estimated parameters or observed fields.
# Each customer's one persistent draw is kept inside generate_data, never exported.
CHURN_COMPONENTS = {"durable": (0.7, 12.0), "fragile": (2.0, 5.0)}
DISRUPTION_MONTHS = (14, 15)  # March and April 2025; calendar months, not customer ages.
DISRUPTION_CHURN_ODDS_MULTIPLIER = 1.35
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


def _month(index: int) -> date:
    return date(2024 + index // 12, index % 12 + 1, 1)


def _stamp(d: date, day: int = 3, hour: int = 9) -> str:
    return datetime(d.year, d.month, day, hour).isoformat(sep=" ")


def _money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(SCHEMAS[path.name]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def churn_mixture_spec(cohort: int, need: str, channel: str) -> dict:
    """Population mixture before acquisition; neither component is an observed segment.

    Observable segments retain continuous within-segment heterogeneity. Cohort
    quality changes modestly, while the source generator also changes observable
    acquisition mix. Both mechanisms must be separated in the business analysis.
    """
    if not 0 <= cohort < 24 or need not in {"save_time", "build_skill"} or channel not in {"search", "partner", "organic"}:
        raise ValueError("Unsupported acquisition cohort, need, or channel")
    fragile_weight = (0.40 if need == "save_time" else 0.24)
    fragile_weight += {"search": 0.04, "partner": -0.04, "organic": 0.0}[channel]
    fragile_weight += -0.06 * cohort / 23 + 0.02 * math.sin(0.6 * cohort)
    return {"fragile_weight": min(0.85, max(0.05, fragile_weight)),
            "durable": CHURN_COMPONENTS["durable"], "fragile": CHURN_COMPONENTS["fragile"]}


def sample_churn_propensity(rng: random.Random, cohort: int, need: str, channel: str) -> float:
    """Draw one customer's unobserved baseline propensity ONCE, at acquisition."""
    spec = churn_mixture_spec(cohort, need, channel)
    component = "fragile" if rng.random() < spec["fragile_weight"] else "durable"
    return rng.betavariate(*spec[component])


def renewal_probability(theta: float, calendar_index: int) -> float:
    """Monthly renewal conditional on still being active, with a temporary common shock.

    The latent theta is constant. A service disruption changes the odds for two
    calendar months without drawing a new propensity or permanently changing it.
    """
    if not 0 <= theta <= 1:
        raise ValueError("Churn propensity must lie in [0, 1]")
    multiplier = DISRUPTION_CHURN_ODDS_MULTIPLIER if calendar_index in DISRUPTION_MONTHS else 1.0
    hazard = multiplier * theta / (1 - theta + multiplier * theta)
    return 1 - hazard


def generate_data(data_dir: Path, seed: int = DEFAULT_SEED) -> dict:
    """Write the frozen eight-export dataset and its deterministic manifest."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    rows = {name: [] for name in SCHEMAS}
    counters: Counter = Counter()

    def next_id(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}{counters[prefix]:07d}"

    def person(cohort: int, need: str, prospect: bool = False) -> str:
        pid = next_id("P")
        baseline = datetime.combine(_month(cohort), datetime.min.time()) - timedelta(days=14 if prospect else 7)
        rows["people.csv"].append({
            "person_id": pid, "record_created_at": baseline.isoformat(sep=" "),
            "attributes_recorded_at": (baseline + timedelta(days=1)).isoformat(sep=" "),
            "age_band": rng.choice(["18_34", "35_plus"]), "household_type": rng.choice(["solo", "shared"]),
            "primary_need": need, "region": rng.choice(["east", "west"]),
        })
        return pid

    def event(pid: str, when: str, event_type: str, platform: str = "app") -> None:
        rows["product_events.csv"].append({"event_id": next_id("E"), "person_id": pid,
            "occurred_at": when, "event_type": event_type, "platform": platform})

    def payment(pid: str, period: str, month: date, charge: str, quantity: int, unit: int,
                discount: int, cost: int, day: int) -> str:
        tid = next_id("T")
        oid = next_id("O")
        gross = quantity * unit
        rows["transactions.csv"].append({
            "transaction_id": tid, "person_id": pid, "period_id": period, "occurred_at": _stamp(month, day),
            "transaction_type": "payment", "related_transaction_id": "", "order_id": oid,
            "charge_type": charge, "quantity": quantity, "unit_price": _money(unit),
            "gross_amount": _money(gross), "discount_amount": _money(discount), "refund_amount": "0.00",
            "variable_cost": _money(cost),
        })
        if rng.random() < 0.045:
            # A refund is a new ledger event. Original gross payment and service cost are not repeated.
            refund = (gross - discount) // 4
            rows["transactions.csv"].append({
                "transaction_id": next_id("T"), "person_id": pid, "period_id": period,
                "occurred_at": _stamp(month, min(day + 7, 27), 14), "transaction_type": "refund",
                "related_transaction_id": tid, "order_id": oid, "charge_type": charge,
                "quantity": "", "unit_price": "", "gross_amount": "0.00", "discount_amount": "0.00",
                "refund_amount": _money(refund), "variable_cost": "0.00",
            })
        return tid

    def subscribe(pid: str, cohort: int, need: str, channel: str, campaign: str | None) -> None:
        sid = next_id("S")
        # Persistent individual heterogeneity: do not redraw this at each renewal.
        theta = sample_churn_propensity(rng, cohort, need, channel)
        tier = "premium" if rng.random() < (0.08 if need == "save_time" else 0.22) + cohort * 0.004 else "standard"
        first_transaction = None
        alive = True
        for age in range(25 - cohort):
            month = _month(cohort + age)
            future = cohort + age >= 24
            if age and not future:
                alive = rng.random() < renewal_probability(theta, cohort + age)
                if alive and tier == "standard" and rng.random() < 0.065 + 0.0015 * cohort:
                    tier = "premium"
            outcome = "pending" if future else ("paid" if alive else ("cancelled" if rng.random() < 0.88 else "failed"))
            period = next_id("R")
            next_month = _month(cohort + age + 1)
            rows["subscription_periods.csv"].append({
                "period_id": period, "subscription_id": sid, "person_id": pid,
                "period_start": date(month.year, month.month, 3).isoformat(),
                "period_end": date(next_month.year, next_month.month, 3).isoformat(),
                "renewal_due_at": _stamp(month, 3, 8), "renewal_outcome": outcome,
                "cancellation_effective_at": _stamp(month, 3, 8) if outcome == "cancelled" else "",
                "plan_tier": tier,
            })
            if future or not alive:
                break
            # Prices and quantities are explicit: revenue can diverge from headcount without fabricated summaries.
            unit = 5000 if tier == "standard" else 7500
            discount = 500 if age == 0 and rng.random() < 0.23 else 0
            cost = (3100 if tier == "standard" else 4050) - 15 * min(cohort, 16)
            tid = payment(pid, period, month, "subscription", 1, unit, discount, cost, 3)
            if first_transaction is None:
                first_transaction = tid
                event(pid, _stamp(month, 2, 14), "onboarding_started", "web")
                if rng.random() < 0.87:
                    event(pid, _stamp(month, 4, 10), "onboarding_completed")
            if rng.random() < min(0.65, 0.17 + 0.018 * age + 0.004 * cohort + (0.08 if need == "build_skill" else 0)):
                quantity = rng.choices([1, 2, 3], weights=[60, 30, 10])[0]
                addon_unit = 1200 if tier == "premium" else 900
                payment(pid, period, month, "add_on", quantity, addon_unit, 0, quantity * 350, 15)
            # Some paid subscribers have no logged core action in a month: usage is not contractual membership.
            for j in range(rng.choices([0, 1, 2, 3], weights=[15, 35, 35, 15])[0]):
                event(pid, _stamp(month, 8 + j * 6, 16), "core_action")
            if rng.random() < 0.07:
                event(pid, _stamp(month, 21, 11), "support_contact", "support")
            if age in (0, 2) and rng.random() < 0.34:
                ease = rng.choices([1, 2, 3, 4, 5], weights=[3, 7, 17, 43, 30])[0]
                value = rng.choices([1, 2, 3, 4, 5], weights=[2, 8, 20, 40, 30])[0]
                rows["feedback.csv"].append({
                    "response_id": next_id("F"), "person_id": pid, "submitted_at": _stamp(month, 24, 10),
                    "journey_stage": "onboarding" if age == 0 else "ongoing_use", "ease_rating": ease,
                    "value_rating": value, "main_difficulty": "none" if ease >= 4 else rng.choice(["getting_started", "finding_time", "finding_features"]),
                })
        assert first_transaction is not None
        rows["acquisition_attribution.csv"].append({
            "person_id": pid, "first_paid_transaction_id": first_transaction,
            "credited_campaign_id": campaign or "", "source_type": "paid_campaign" if campaign else "organic",
            "attribution_rule": "last_eligible_campaign_in_acquisition_month" if campaign else "no_paid_campaign_credit",
            "credited_at": _stamp(_month(cohort), 4, 9),
        })

    def spend(campaign: str, cohort: int, channel: str, need: str, media: int, other: int) -> None:
        # The three dated rows must be aggregated once, independently of the payment ledger.
        for day, fraction in [(1, 30), (10, 40), (20, 30)]:
            m = media * fraction // 100
            o = other * fraction // 100
            if day == 20:
                m = media - media * 30 // 100 - media * 40 // 100
                o = other - other * 30 // 100 - other * 40 // 100
            rows["campaign_spend.csv"].append({"campaign_id": campaign,
                "spend_date": date(_month(cohort).year, _month(cohort).month, day).isoformat(),
                "channel": channel, "target_need": need, "media_spend": _money(m), "other_acquisition_spend": _money(o)})

    for cohort in range(24):
        expected_total = 140 + 4 * cohort + round(7 * math.sin(cohort * 0.85))
        partner_share = 0.40 + 0.07 * cohort / 23
        skill_share = 0.43 + 0.10 * cohort / 23
        for channel, channel_share in [("search", 1 - partner_share), ("partner", partner_share)]:
            for need, need_share in [("save_time", 1 - skill_share), ("build_skill", skill_share)]:
                expected_n = max(15, round(expected_total * channel_share * need_share))
                n = max(12, round(expected_n * rng.uniform(0.92, 1.08)))
                campaign = f"CORE-{cohort:02d}-{channel}-{need}"
                planned_cac = round(10800 - 170 * cohort + 250 * math.sin(cohort * 0.9))
                planned_cac += (-900 if channel == "partner" else 0) + (500 if need == "build_skill" else 0)
                total_budget = expected_n * planned_cac
                media = total_budget * 85 // 100
                spend(campaign, cohort, channel, need, media, total_budget - media)
                for _ in range(n):
                    subscribe(person(cohort, need), cohort, need, channel, campaign)

    specs = []
    for number, cohort, channel, need, treatment_p, control_p, media in [
        (1, 16, "search", "save_time", 0.25, 0.11, 65000),
        (2, 20, "partner", "build_skill", 0.24, 0.12, 90000),
    ]:
        eid, campaign = f"EXP-{number:02d}", f"TEST-{number:02d}-{channel}-{need}"
        n_arm = 250
        spend(campaign, cohort, channel, need, media, 0)
        arms = ["treatment"] * n_arm + ["control"] * n_arm
        rng.shuffle(arms)
        for arm in arms:
            pid = person(cohort, need, prospect=True)
            rows["experiment_assignments.csv"].append({
                "experiment_id": eid, "person_id": pid, "tested_campaign_id": campaign,
                "assigned_at": _stamp(_month(cohort), 1, 0), "arm": arm,
                "followup_end_at": _stamp(_month(cohort + 1), 1, 0),
            })
            if rng.random() < (treatment_p if arm == "treatment" else control_p):
                subscribe(pid, cohort, need, channel if arm == "treatment" else "organic", campaign if arm == "treatment" else None)
        specs.append({
            "experiment_id": eid, "tested_campaign_id": campaign, "channel": channel, "primary_need": need,
            "assigned_per_arm": n_arm, "randomization": "Seeded shuffled balanced assignment among preexisting, never-paid eligible prospects.",
            "assigned_at": _stamp(_month(cohort), 1, 0), "followup_end_at": _stamp(_month(cohort + 1), 1, 0),
            "eligibility": "CRM and baseline attributes exist before assignment; no prior payment; no person enters another test.",
            "control": "Withhold this focal campaign; record purchases through every route. Own controls are not shared with the other experiment.",
            "cost_scope": "Focal campaign media only; treatment spends the recorded campaign budget, control spends zero focal media.",
        })

    for name in SCHEMAS:
        _write_csv(data_dir / name, rows[name])
    definitions = {
        "business": "Studio North is a fictional monthly creative-work membership for independent professionals. Members use ready-to-use templates to save time or guided learning to build skills; standard ($50) and premium ($75) subscriptions can renew monthly, with optional paid workshops/add-ons.",
        "acquisition": "First positive successful payment; an initial payment remains an acquisition if later refunded. CRM creation is not acquisition.",
        "cohort": "Calendar month of the first paid transaction. cohort_index and age_month are zero-based; age 0 is the acquisition month.",
        "time": "UTC. data_as_of is exclusive. Monthly period statuses are known at renewal. Future pending periods are scheduling records, not observed retention.",
        "retention": "Paid scheduled subscription cycle. One subscription per person; membership is monotone until cancellation/failure, with no reactivation.",
        "usage": "Observed core_action events. A retained subscriber can have no core_action event; usage and membership are different measures.",
        "paying": "At least one payment event in the calendar month; count people and distinct paid orders, not refund ledger rows.",
        "gross_payment_revenue": "Sum gross_amount minus discount_amount on successful payment rows, before refunds; positive for every retained person-month. Net revenue equals this payment revenue minus refunds.",
        "net_revenue": "gross_amount minus discount_amount minus refund_amount, summed over the dated financial ledger.",
        "contribution": "Net revenue minus incurred variable_cost, before acquisition spending and fixed costs. Refund rows do not duplicate original service costs.",
        "acquisition_cost": "Recorded media plus campaign-specific creative/vendor acquisition costs. Discounts reduce transaction revenue and are not counted again as acquisition spending.",
        "CAC": "Recorded acquisition cost / first-paid customers. These are attribution/accounting ratios, not incremental CAC. Organic segment CAC is unsupported, not zero.",
        "targeting": "Every paid campaign targets one baseline primary_need. Direct segment cost aggregation is supported for primary_need, not age_band or region.",
        "attribution": "One credited campaign within the acquisition month. Dates and campaign windows align by design. The export supplies credit, not a reconstructed journey or a causal label.",
        "company_scope": "All acquired customers, including experimental buyers and controls, and all recorded acquisition spending. Company-wide CAC is tracked acquisition spending / acquired customers, not fully loaded company CAC.",
        "experiment_scope": "All assigned eligible prospects remain in denominators. Purchase outcomes do not depend on attributed source. Control buyers may have organic credit.",
        "forecast": "Separate observed cash contribution from model forecasts. A 12-month horizon and 1% monthly discount use first receipt t=age_month+1; cash payback is undiscounted.",
        "synthetic_trends": "Changing acquisition cost and observable need/channel mix; persistent individual churn propensities from a two-Beta mixture whose composition varies across acquisition cohorts, needs and channels; a temporary common service disruption; explicit premium upgrades/add-on quantities and incurred costs. Random variation remains, and aggregate improvement does not by itself establish within-segment improvement.",
    }
    manifest = {
        "schema_version": SCHEMA_VERSION, "dataset_version": DATASET_VERSION, "synthetic_seed": seed,
        "data_as_of": DATA_AS_OF, "timezone": "UTC", "currency": "USD",
        "source_cutoffs": {name: DATA_AS_OF for name in SCHEMAS},
        "files": {name: {"sha256": _digest(data_dir / name), "row_count": len(rows[name])} for name in SCHEMAS},
        "definitions": definitions, "experiment_specs": specs,
        "retention_dgp": {
            "version": "persistent-mixture-beta-v2",
            "components": {k: {"alpha": v[0], "beta": v[1]} for k, v in CHURN_COMPONENTS.items()},
            "fragile_weight": "clip((0.40 if save_time else 0.24) + channel_offset - 0.06*cohort_index/23 + 0.02*sin(0.6*cohort_index), 0.05, 0.85)",
            "channel_offset": {"search": 0.04, "partner": -0.04, "organic": 0.0},
            "latent_draw": "One Beta-mixture churn propensity per acquired person, reused at every renewal; latent propensity and component are never columns in the observed CSVs.",
            "calendar_disruption": {"months": ["2025-03", "2025-04"], "churn_odds_multiplier": DISRUPTION_CHURN_ODDS_MULTIPLIER},
            "renewal": "Bernoulli((1-theta)/(1-theta+odds_multiplier*theta)); monthly until permanent churn; acquisition month is paid and future months are censored.",
            "separation": "These simulation assumptions document data provenance. The inference model must fit only observed source-derived cohort cells, not latent propensities or DGP parameters.",
        },
        "generator": "cohort_lab.data.generate_data; Python standard-library random.Random, integer-cent generation",
        "license": "Original synthetic teaching data; no real personal, course, or licensed-source records.",
    }
    dictionary = {"schema_version": SCHEMA_VERSION, "tables": {
        name: {"grain": GRAINS[name], "primary_key": PRIMARY_KEYS[name], "columns": [
            {"name": col, "type": typ, "nullable": col in NULLABLE.get(name, set())} for col, typ in fields.items()]
        } for name, fields in SCHEMAS.items()}, "definitions": definitions}
    (data_dir / "data_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data_dir / "data_dictionary.json").write_text(json.dumps(dictionary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_data(data_dir)
    return manifest


def validate_data(data_dir: Path) -> dict:
    """Fail closed on changed exports, then check independent source invariants."""
    data_dir = Path(data_dir)
    manifest_path = data_dir / "data_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Missing data_manifest.json; use the frozen dataset or explicit instructor generation.")
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
