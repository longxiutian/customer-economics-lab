"""Matched-population segmentation and experimental acquisition-cost accounting."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from .analysis import validate_analysis, _hash

INPUTS = {"segmentation_comparison.csv", "segmentation_profile.csv", "experiment_summary.csv", "experiment_effects.csv"}
OUTPUTS = {"segmentation_objective.csv", "cac_reconciliation.csv"}


def segmentation_objective(comparison: pd.DataFrame, profile: pd.DataFrame) -> pd.DataFrame:
    if comparison.scheme.duplicated().any() or set(comparison.scheme) != set(profile.scheme):
        raise ValueError("Segmentation strategies must have unique, matching profiles")
    if comparison.n_customers.nunique() != 1 or comparison.n_groups.nunique() != 1:
        raise ValueError("Compare the same population size and group complexity")
    rows = []
    for _, r in comparison.iterrows():
        g = profile[profile.scheme == r.scheme]
        if g.n.sum() != r.n_customers or len(g) != r.n_groups or (g.n <= 0).any():
            raise ValueError("Segmentation denominator mismatch")
        weights = g.n / g.n.sum()
        mean = float(np.sum(weights * g.mean_contribution))
        within = float(np.sum(weights * g.variance))
        between = float(np.sum(weights * (g.mean_contribution - mean) ** 2))
        if not np.allclose([within, within + between], [r.weighted_within_variance, r.pooled_variance], rtol=1e-9, atol=1e-8):
            raise ValueError("Within/between variance does not reconcile")
        if within + between <= 0 or r.pooled_cohort_centered_variance <= 0:
            raise ValueError("Variance shares require positive total outcome variance")
        centered_between = r.pooled_cohort_centered_variance - r.cohort_centered_within_variance
        if centered_between < -1e-8:
            raise ValueError("Negative between-group variance")
        rows.append(dict(scheme=r.scheme, n_customers=int(r.n_customers), n_groups=int(r.n_groups),
            min_group_size=int(g.n.min()), pooled_mean=mean, total_variance=within+between,
            within_variance=within, between_variance=between, within_sd=np.sqrt(within),
            within_share=within/(within+between), between_share=between/(within+between),
            mean_min=float(g.mean_contribution.min()), mean_max=float(g.mean_contribution.max()),
            cohort_centered_between_share=centered_between/r.pooled_cohort_centered_variance))
    return pd.DataFrame(rows).sort_values("between_share", ascending=False)


def _ratio_record(row: dict) -> dict:
    spend, buyers, se = row["incremental_media_spend"], row["incremental_buyers"], row["incremental_buyers_se"]
    if spend < 0:
        raise ValueError("This reconciliation expects nonnegative incremental media spend")
    lower, upper = buyers - 1.96*se, buyers + 1.96*se
    status = "finite" if lower > 0 else "unbounded" if upper > 0 else "no_positive_lift"
    row.update(incremental_buyers_ci_lower=lower, incremental_buyers_ci_upper=upper,
        incremental_media_cac=spend/buyers if buyers > 0 else np.nan,
        icac_ci_lower=spend/upper if upper > 0 else np.nan,
        icac_ci_upper=spend/lower if lower > 0 else np.nan, icac_interval_status=status,
        treatment_media_cac=row["media_spend_treatment"]/row["buyers_treatment"] if row["buyers_treatment"] else np.nan,
        incremental_spend_per_treated_buyer=spend/row["buyers_treatment"] if row["buyers_treatment"] else np.nan,
        estimated_background_share=row["expected_buyers_without_tested_campaign"]/row["buyers_treatment"] if row["buyers_treatment"] else np.nan)
    return row


def cac_reconciliation(arms: pd.DataFrame, effects: pd.DataFrame) -> pd.DataFrame:
    if effects.experiment_id.duplicated().any() or set(arms.experiment_id) != set(effects.experiment_id):
        raise ValueError("Experimental source coverage mismatch")
    rows = []
    for exp, group in arms.groupby("experiment_id", sort=True):
        if len(group) != 2 or set(group.arm) != {"treatment", "control"}:
            raise ValueError("Each experiment requires one treatment and one control")
        g = group.set_index("arm"); t, c = g.loc["treatment"], g.loc["control"]
        for field in ["channel", "primary_need", "assigned_at", "followup_end_at", "followup_days"]:
            if t[field] != c[field]: raise ValueError("Experimental populations or horizons differ")
        if min(t.n_assigned, c.n_assigned) <= 0 or not (0 <= t.n_buyers <= t.n_assigned and 0 <= c.n_buyers <= c.n_assigned):
            raise ValueError("Invalid assignment or buyer denominator")
        k = float(t.n_assigned/c.n_assigned)
        pt, pc = t.n_buyers/t.n_assigned, c.n_buyers/c.n_assigned
        row = dict(experiment_id=exp, scope="individual_test", channel=t.channel, primary_need=t.primary_need,
            assigned_at=t.assigned_at, followup_end_at=t.followup_end_at, followup_days=float(t.followup_days),
            n_treatment=int(t.n_assigned), n_control=int(c.n_assigned), scale_to_treatment=k,
            buyers_treatment=int(t.n_buyers), buyers_control=int(c.n_buyers),
            media_spend_treatment=float(t.media_spend), media_spend_control=float(c.media_spend),
            expected_buyers_without_tested_campaign=float(k*c.n_buyers),
            incremental_buyers=float(t.n_buyers-k*c.n_buyers),
            incremental_buyers_se=float(t.n_assigned*np.sqrt(pt*(1-pt)/t.n_assigned+pc*(1-pc)/c.n_assigned)),
            incremental_media_spend=float(t.media_spend-k*c.media_spend),
            incremental_contribution=float(t.contribution-k*c.contribution))
        row["incremental_contribution_after_media"] = row["incremental_contribution"]-row["incremental_media_spend"]
        saved = effects.set_index("experiment_id").loc[exp]
        fields = ["incremental_buyers", "incremental_media_spend", "incremental_contribution", "incremental_contribution_after_media"]
        if not np.allclose([row[f] for f in fields], [saved[f] for f in fields], rtol=1e-9, atol=1e-8):
            raise ValueError("CAC reconciliation differs from saved intention-to-treat results")
        rows.append(_ratio_record(row))
    if not rows: raise ValueError("No experimental comparisons")
    # Sum separately standardized effects, not a pooled-arm rate difference.
    pool = {name: sum(r[name] for r in rows) for name in ["n_treatment", "n_control", "buyers_treatment", "buyers_control",
        "media_spend_treatment", "media_spend_control", "expected_buyers_without_tested_campaign", "incremental_buyers",
        "incremental_media_spend", "incremental_contribution", "incremental_contribution_after_media"]}
    pool.update(experiment_id="TESTED_PROGRAM", scope="descriptive_tested_program_rollup", channel="multiple", primary_need="multiple",
        assigned_at="", followup_end_at="", followup_days=np.nan, scale_to_treatment=np.nan,
        incremental_buyers_se=float(np.sqrt(sum(r["incremental_buyers_se"]**2 for r in rows))))
    rows.append(_ratio_record(pool))
    return pd.DataFrame(rows)


def build_decision_metrics(output_dir: Path) -> dict:
    output = Path(output_dir); validate_analysis(output); tables = output/"tables"
    read = lambda n: pd.read_csv(tables/n)
    results = {"segmentation_objective.csv":segmentation_objective(read("segmentation_comparison.csv"), read("segmentation_profile.csv")),
               "cac_reconciliation.csv":cac_reconciliation(read("experiment_summary.csv"), read("experiment_effects.csv"))}
    for name, frame in results.items(): frame.to_csv(tables/name,index=False,float_format="%.10f",lineterminator="\n")
    manifest = {"version":1,"code_sha256":_hash(Path(__file__)),
        "input_hashes":{n:_hash(tables/n) for n in sorted(INPUTS)},"output_hashes":{n:_hash(tables/n) for n in sorted(OUTPUTS)},
        "segmentation_scope":"Same mature nonexperimental paid customers, six receipts and two-group candidate partitions. Population variance equals customer-weighted within plus between variance. Descriptive, not intervention or future prediction effects.",
        "cac_scope":"Randomized all-assigned acquisition tests; background acquisitions standardized to treatment-arm size. Incremental media costs and buyer effects reconcile to the existing SQL outputs. No private outcomes, lifetime extrapolation or all-company calibration.",
        "uncertainty":"Approximate unadjusted 95% normal buyer-lift interval, conditional on fixed media spend; invert only the positive effect region. Intervals crossing zero have no finite upper iCAC bound. No clipping or fabricated finite estimate.",
        "pooling":"Sum each test's separately standardized effects and costs; independent tests supply summed variances. This fixed tested-program rollup spans different populations and windows and is not company-wide or marginal CAC."}
    (output/"decision_metrics_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding="utf-8")
    return manifest


def validate_decision_metrics(output_dir: Path) -> dict:
    output=Path(output_dir);m=json.loads((output/"decision_metrics_manifest.json").read_text(encoding="utf-8"))
    if set(m["input_hashes"])!=INPUTS or set(m["output_hashes"])!=OUTPUTS or m["code_sha256"]!=_hash(Path(__file__)):
        raise ValueError("Decision-metrics provenance mismatch")
    for n,h in {**m["input_hashes"],**m["output_hashes"]}.items():
        if _hash(output/"tables"/n)!=h:raise ValueError(f"Decision-metrics hash mismatch: {n}")
    return m
