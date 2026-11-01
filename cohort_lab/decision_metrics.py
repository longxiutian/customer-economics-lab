"""Matched-population segmentation and experimental acquisition-cost accounting."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from .analysis import validate_analysis, _hash

INPUTS = {"segmentation_comparison.csv", "segmentation_profile.csv", "channel_cac.csv", "channel_cac_current.csv"}
OUTPUTS = {"segmentation_objective.csv", "channel_value_decision.csv"}


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


def channel_value_decision(cac: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    keys = ["cohort_month", "channel", "primary_need"]
    # Select value by observed maturity, independently of test dates and outcomes.
    cells = set(zip(cac.channel, cac.primary_need))
    eligible = values[values.observed_months >= 6]
    months = [month for month, group in eligible.groupby("cohort_month")
              if cells <= set(zip(group.channel, group.primary_need))]
    if not months:
        raise ValueError("Each channel test needs a matching value benchmark with six observed receipts")
    source = cac.drop(columns=["value_cohort_month"], errors="ignore").copy()
    source["cohort_month"] = max(months)
    value_cols = keys + ["n_acquired", "observed_months", "horizon_months", "forecast_share", "ltv_before_cac_mean", "ltv_before_cac_p05", "ltv_before_cac_p95"]
    result = source.merge(values[value_cols], on=keys, how="left", validate="many_to_one")
    if result.ltv_before_cac_mean.isna().any() or not (result.horizon_months == 12).all():
        raise ValueError("Each channel test needs its matching twelve-receipt value benchmark")
    result["assumed_value_per_additional_customer"] = result.ltv_before_cac_mean
    result["value_less_icac"] = result.ltv_before_cac_mean - result.icac
    result["planning_net_value"] = result.incremental_buyers*result.ltv_before_cac_mean - result.incremental_spend
    result["value_to_icac"] = result.ltv_before_cac_mean/result.icac
    result["break_even_value"] = result.icac
    result["scope"] = "Planning projection: assume additional pilot customers have matching operational-cohort contribution value and no value change for customers who would acquire anyway. Not an experimentally measured lifetime return."
    return result


def build_decision_metrics(output_dir: Path) -> dict:
    output=Path(output_dir); validate_analysis(output); tables=output/"tables"
    results={"segmentation_objective.csv":segmentation_objective(pd.read_csv(tables/"segmentation_comparison.csv"),pd.read_csv(tables/"segmentation_profile.csv"))}
    inputs=set(INPUTS)
    if (output/"model_manifest.json").exists():
        from .report import _validate_model_outputs
        _validate_model_outputs(output)
        inputs.add("cohort_valuation_by_segment.csv")
        results["channel_value_decision.csv"]=channel_value_decision(pd.read_csv(tables/"channel_cac_current.csv"),pd.read_csv(tables/"cohort_valuation_by_segment.csv"))
    for name,frame in results.items():frame.to_csv(tables/name,index=False,float_format="%.10f",lineterminator="\n")
    manifest={"version":3,"code_sha256":_hash(Path(__file__)),
        "input_hashes":{n:_hash(tables/n) for n in sorted(inputs)},"output_hashes":{n:_hash(tables/n) for n in sorted(results)},
        "segmentation_scope":"Same mature operational customers, six receipts and two-group candidate partitions. Customer-weighted within and between variance.",
        "cac_scope":"Monthly disjoint acquisition-only holdouts. Preserve every completed wave in channel_cac; channel_cac_current selects the latest completed test for each channel/need without screening its result. No pooling across time or channels; no experimental revenue/retention outcomes.",
        "value_scope":"Planning join after fitting: latest current iCAC and the latest common operational cohort with at least six observed receipts in every tested channel/need cell. Twelve receipts of contribution before CAC at 1% monthly discount. Additional-customer value and no effect on would-be buyers are assumptions. No experiment enters the model."}
    (output/"decision_metrics_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding="utf-8")
    return manifest


def validate_decision_metrics(output_dir: Path) -> dict:
    output=Path(output_dir);m=json.loads((output/"decision_metrics_manifest.json").read_text(encoding="utf-8"))
    fitted=(output/"model_manifest.json").exists()
    expected_inputs=INPUTS | ({"cohort_valuation_by_segment.csv"} if fitted else set())
    expected_outputs=OUTPUTS if fitted else {"segmentation_objective.csv"}
    if set(m["input_hashes"])!=expected_inputs or set(m["output_hashes"])!=expected_outputs or m["code_sha256"]!=_hash(Path(__file__)):
        raise ValueError("Decision-metrics provenance mismatch")
    for n,h in {**m["input_hashes"],**m["output_hashes"]}.items():
        if _hash(output/"tables"/n)!=h:raise ValueError(f"Decision-metrics hash mismatch: {n}")
    return m
