"""Field-level Universal Customer View classification of the observed exports.

The framework describes available evidence; a category assignment does not
convert an accounting/design field into a measured customer attitude or action.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .data import GRAINS, SCHEMAS

CATEGORIES = ("Identifiers", "Engagement", "Relationship", "Perception")
CATEGORY_DEFINITIONS = {
    "Identifiers": "Keys and profile descriptors identify or link people, groups and records; not every identifier is unique.",
    "Engagement": "Observed customer interactions and their measurement context. Firm marketing activity and attribution metadata are retained as explicitly marked contextual evidence; they do not establish individual exposure, action or a causal effect.",
    "Relationship": "Contractual and commercial arrangements, customer status, and explicitly marked operational context for relationship economics.",
    "Perception": "Customer-reported views or intentions, distinguished from behavior and analyst inference.",
}
SOURCE_NAMES = {
    "people.csv": "CRM", "subscription_periods.csv": "Renewal system",
    "transactions.csv": "Finance", "product_events.csv": "Product and support",
    "feedback.csv": "Customer research", "campaign_spend.csv": "Marketing spending",
    "acquisition_attribution.csv": "Marketing attribution",
    "experiment_assignments.csv": "Experiment platform",
}

# Explicit choices are reviewed rather than guessed from field-name substrings.
FIELD_GROUPS = {
    "people.csv": {
        "Identifiers": ["person_id", "age_band", "household_type", "region"],
        "Relationship": ["record_created_at", "attributes_recorded_at"],
        "Perception": ["primary_need"],
    },
    "subscription_periods.csv": {
        "Identifiers": ["period_id", "subscription_id", "person_id"],
        "Relationship": ["period_start", "period_end", "renewal_due_at", "renewal_outcome", "cancellation_effective_at", "plan_tier"],
    },
    "transactions.csv": {
        "Identifiers": ["transaction_id", "person_id", "period_id", "related_transaction_id", "order_id"],
        "Engagement": ["occurred_at", "transaction_type", "charge_type", "quantity", "gross_amount", "discount_amount", "refund_amount"],
        "Relationship": ["unit_price", "variable_cost"],
    },
    "product_events.csv": {
        "Identifiers": ["event_id", "person_id"],
        "Engagement": ["occurred_at", "event_type", "platform"],
    },
    "feedback.csv": {
        "Identifiers": ["response_id", "person_id"],
        "Engagement": ["submitted_at", "journey_stage"],
        "Perception": ["ease_rating", "value_rating", "main_difficulty"],
    },
    "campaign_spend.csv": {
        "Identifiers": ["campaign_id", "target_need"],
        "Engagement": ["spend_date", "channel", "media_spend", "other_acquisition_spend"],
    },
    "acquisition_attribution.csv": {
        "Identifiers": ["person_id", "first_paid_transaction_id", "credited_campaign_id"],
        "Engagement": ["source_type", "credited_at", "attribution_rule"],
    },
    "experiment_assignments.csv": {
        "Identifiers": ["experiment_id", "person_id", "tested_campaign_id"],
        "Relationship": ["assigned_at", "arm", "followup_end_at"],
    },
}

# These fields retain their best-fit category but require an explicit qualifier.
# A dagger is display metadata, never part of the actual source field name.
CONTEXT_ONLY_FIELDS = {
    "people.csv": ["record_created_at", "attributes_recorded_at"],
    "subscription_periods.csv": [],
    "transactions.csv": ["unit_price", "variable_cost"],
    "product_events.csv": [],
    "feedback.csv": ["journey_stage"],
    "campaign_spend.csv": ["target_need", "spend_date", "channel", "media_spend", "other_acquisition_spend"],
    "acquisition_attribution.csv": ["source_type", "credited_at", "attribution_rule"],
    "experiment_assignments.csv": ["assigned_at", "arm", "followup_end_at"],
}

RATIONALE = {
    "people.csv": {
        "age_band": "Profile descriptor; it identifies a demographic group, not a unique person.",
        "household_type": "Profile descriptor; the subscription unit remains one individual.",
        "region": "Geographic profile descriptor, not an observed preference.",
        "record_created_at": "CRM relationship provenance; registration does not establish a paid customer.",
        "attributes_recorded_at": "Profile provenance: verifies attributes were available before acquisition or assignment.",
        "primary_need": "A stated intention recorded before acquisition, not a need inferred from future behavior.",
    },
    "subscription_periods.csv": {
        "renewal_outcome": "Contractual status establishes retention; a logged product action does not.",
        "renewal_due_at": "A scheduled deadline may be known before the outcome is observed.",
        "cancellation_effective_at": "Contractual exit timing; a blank is not proof of indefinite survival.",
    },
    "transactions.csv": {
        "unit_price": "The item's commercial price term is Relationship context; billed quantity and realized amounts record transaction Engagement.",
        "variable_cost": "Firm-side accounting context for relationship economics; unlike billed amounts, it does not record a customer payment or reported perception.",
        "related_transaction_id": "A refund links to the original payment; it does not identify another customer.",
        "refund_amount": "Observed financial reversal; a reason for dissatisfaction is not recorded here.",
    },
    "product_events.csv": {
        "platform": "Context of an observed interaction, not an acquisition channel or a motive.",
    },
    "feedback.csv": {
        "submitted_at": "Survey-response activity and timing, not the attitude itself.",
        "journey_stage": "Context of the response, not a measured universal customer path.",
        "main_difficulty": "Customer-reported difficulty; a hypothesis about causes, not causal evidence.",
    },
    "campaign_spend.csv": {
        "target_need": "Identifies the campaign's target group; unlike a person's primary_need, it is not an individually stated intention. Channel describes the firm's marketing activity, so it is Engagement context instead.",
        "spend_date": "Timing of firm marketing activity, not a customer touchpoint timestamp.",
        "channel": "Context of firm marketing activity; it does not prove an individual's exposure.",
        "media_spend": "Firm-side campaign spending is retained as Engagement context, not individual engagement or evidence of exposure.",
        "other_acquisition_spend": "Firm-side creative/vendor costs are Engagement context, not observed customer activity; aggregate once before joining customers.",
    },
    "acquisition_attribution.csv": {
        "source_type": "Recorded acquisition-path credit; an attribution label does not establish incrementality.",
        "credited_at": "When credit was recorded, not necessarily the acquisition or exposure time.",
        "attribution_rule": "Measurement metadata for engagement credit, not a customer action itself.",
    },
    "experiment_assignments.csv": {
        "assigned_at": "Experimental relationship/design metadata; assignment is not observed exposure or purchase.",
        "arm": "Randomized intervention assignment; control nonbuyers must remain in the denominator.",
        "followup_end_at": "Prespecified measurement window, not a subscription end date.",
    },
}


def build_ucv_tables(data_dir: Path) -> list[dict]:
    """Return one exact, exhaustive four-column field taxonomy per raw dataset.

    Raises on any unreviewed schema change. Record values are never included.
    """
    tables = []
    for filename, schema in SCHEMAS.items():
        path = Path(data_dir) / filename
        with path.open(newline="", encoding="utf-8-sig") as stream:
            fields = next(csv.reader(stream))
        if fields != list(schema):
            raise ValueError(f"UCV schema mismatch: {filename}; review field classifications")
        groups = {category: list(FIELD_GROUPS[filename].get(category, [])) for category in CATEGORIES}
        classified = [field for values in groups.values() for field in values]
        if sorted(classified) != sorted(fields) or len(classified) != len(set(classified)):
            raise ValueError(f"UCV classification must cover each field exactly once: {filename}")
        if not set(RATIONALE[filename]).issubset(fields):
            raise ValueError(f"UCV rationale references an unknown field: {filename}")
        contextual = list(CONTEXT_ONLY_FIELDS[filename])
        if not set(contextual).issubset(fields) or len(contextual) != len(set(contextual)):
            raise ValueError(f"UCV contextual marker references an unknown or duplicate field: {filename}")
        if not set(contextual).issubset(RATIONALE[filename]):
            raise ValueError(f"UCV contextual placement requires a rationale: {filename}")
        tables.append({"file": filename, "source": SOURCE_NAMES[filename], "grain": GRAINS[filename],
                       "columns": groups, "rationale": dict(RATIONALE[filename]),
                       "context_only_fields": contextual,
                       "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return tables


def ucv_markdown(tables: list[dict]) -> str:
    """Portable appendix with field names, explicit gaps and classification notes."""
    lines = ["# Universal Customer View by source dataset", "",
             *[f"**{category}:** {CATEGORY_DEFINITIONS[category]}" for category in CATEGORIES], "",
             "Each field appears once in the best-fitting category. Empty categories are evidence gaps, not zeros. "
             "A dagger (†) marks contextual or operational placement. Such a field supports interpretation without itself establishing a customer action or attitude; its rationale follows the table. The dagger is not part of the field name.", ""]
    for table in tables:
        lines.extend([f"## {table['file']}", "", f"**{table['source']}** — {table['grain']}", "",
                      "| " + " | ".join(CATEGORIES) + " |", "| " + " | ".join(["---"] * 4) + " |",
                      "| " + " | ".join("<br>".join(f"`{f}`" + ("†" if f in table["context_only_fields"] else "") for f in table['columns'][c]) or "—" for c in CATEGORIES) + " |", ""])
        for field, note in table["rationale"].items():
            lines.append(f"- `{field}`: {note}")
        lines.append("")
    return "\n".join(lines)
