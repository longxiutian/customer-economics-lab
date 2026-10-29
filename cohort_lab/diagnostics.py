"""Descriptive journey diagnostics from the saved, pre-renewal SQL population."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from .analysis import validate_analysis, _hash

STRATA = ["acquisition_year", "channel", "primary_need"]
CONTRASTS = [
    ("onboarding", "not_recorded", "recorded", "No completion − completion"),
    ("early_use", "not_recorded", "recorded", "No core use − core use"),
    ("support", "recorded", "not_recorded", "Support contact − none recorded"),
    ("reported_difficulty", "getting_started", "none", "Getting started − no difficulty"),
    ("reported_difficulty", "finding_features", "none", "Finding features − no difficulty"),
    ("reported_difficulty", "finding_time", "none", "Finding time − no difficulty"),
    ("response", "no_response", "response", "No response − response"),
]


def diagnostic_groups(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f["acquisition_year"] = f.cohort_month.str[:4]
    for name, column in [("onboarding", "onboarding_completions"),
                         ("early_use", "early_core_actions"), ("support", "early_support_contacts")]:
        f[name] = np.where(f[column] > 0, "recorded", "not_recorded")
    f["reported_difficulty"] = f.survey_group
    f["response"] = np.where(f.response_id.notna(), "response", "no_response")
    return f


def standardized_contrast(frame: pd.DataFrame, scheme: str, target: str,
                          reference: str, outcome: str, strata=None) -> dict:
    """Fixed empirical weights, common support; no treatment-effect interpretation.

    Normal intervals use within-cell sample variances and independent people.
    Strata with fewer than two observations in either comparison arm are omitted;
    coverage is reported against ALL outcome-observed members, including other
    survey categories. Weights are their empirical stratum frequencies.
    """
    strata = STRATA if strata is None else strata
    f = frame.dropna(subset=[outcome])
    counts = f.groupby(strata, sort=True).size()
    g = f[f[scheme].isin([target, reference])].groupby(strata + [scheme], sort=True)[outcome].agg(["size", "mean", "var"])
    a, b = (g.xs(x, level=scheme) if x in g.index.get_level_values(scheme) else g.iloc[:0].droplevel(scheme)
            for x in [target, reference])
    common = a.index.intersection(b.index)
    common = common[(a.loc[common, "size"] >= 2) & (b.loc[common, "size"] >= 2)]
    left = f.loc[f[scheme] == target, outcome]; right = f.loc[f[scheme] == reference, outcome]
    result = {"n_target": len(left), "n_reference": len(right), "n_population": len(f),
              "crude_difference": float(left.mean() - right.mean()) if len(left) and len(right) else np.nan,
              "n_target_common": int(a.loc[common, "size"].sum()), "n_reference_common": int(b.loc[common, "size"].sum()),
              "strata": " × ".join(strata),
              "n_strata": len(common), "coverage": float(counts.loc[common].sum() / len(f)) if len(f) else 0.}
    if not len(common):
        return {**result, "crude_common_difference": np.nan, "difference": np.nan, "se": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
    crude_common = float(np.average(a.loc[common, "mean"], weights=a.loc[common, "size"]) -
                         np.average(b.loc[common, "mean"], weights=b.loc[common, "size"]))
    w = counts.loc[common] / counts.loc[common].sum()
    difference = float((w * (a.loc[common, "mean"] - b.loc[common, "mean"])).sum())
    se = float(np.sqrt((w**2 * (a.loc[common, "var"] / a.loc[common, "size"] +
                                b.loc[common, "var"] / b.loc[common, "size"])).sum()))
    return {**result, "crude_common_difference": crude_common, "difference": difference, "se": se,
            "ci_lower": difference - 1.96 * se, "ci_upper": difference + 1.96 * se}


def build_diagnostics(output_dir: Path) -> dict:
    output = Path(output_dir)
    validate_analysis(output)
    source = output / "tables/friction_subjects.csv"
    f = diagnostic_groups(pd.read_csv(source))
    records = []
    for scheme, target, reference, label in CONTRASTS:
        for outcome in ["retained_age1", "retained_age5", "contribution_ages1_5"]:
            strata = ["cohort_month", "channel", "primary_need"] if scheme in {"reported_difficulty", "response"} else STRATA
            records.append({"scheme": scheme, "target": target, "reference": reference,
                            "label": label, "outcome": outcome,
                            **standardized_contrast(f, scheme, target, reference, outcome, strata)})
    pd.DataFrame(records).to_csv(output / "tables/friction_contrasts.csv", index=False, float_format="%.10f", lineterminator="\n")
    sensitivity = []
    for scheme, target, reference, label in CONTRASTS[:2]:
        for outcome in ["retained_age1", "retained_age5"]:
            sensitivity.append({"scheme": scheme, "label": label, "outcome": outcome,
                                **standardized_contrast(f[f.in_window_refunds == 0], scheme, target, reference, outcome)})
    pd.DataFrame(sensitivity).to_csv(output / "tables/friction_refund_sensitivity.csv", index=False, float_format="%.10f", lineterminator="\n")
    balance = []
    for scheme in ["onboarding", "early_use", "reported_difficulty"]:
        for segment, g in f.groupby(scheme, sort=True):
            balance.append({"scheme": scheme, "segment": segment, "n": len(g),
                            "share_partner": (g.channel == "partner").mean(),
                            "share_build_skill": (g.primary_need == "build_skill").mean(),
                            "share_2025": (g.acquisition_year == "2025").mean(),
                            "share_premium": (g.initial_plan == "premium").mean(),
                            "mean_initial_discount": g.initial_discount.mean(),
                            "mean_age0_contribution": g.contribution_age0.mean()})
    pd.DataFrame(balance).to_csv(output / "tables/friction_balance.csv", index=False, float_format="%.10f", lineterminator="\n")
    audit = pd.read_csv(output / "tables/friction_timing_audit.csv").iloc[0].to_dict()
    manifest = {"version": 1, "code_sha256": _hash(Path(__file__)),
                "input_hashes": {name: _hash(output / "tables" / name) for name in
                                 ["friction_subjects.csv", "friction_timing_audit.csv"]},
                "output_hashes": {name: _hash(output / "tables" / name) for name in
                                  ["friction_contrasts.csv", "friction_balance.csv", "friction_refund_sensitivity.csv"]},
                "scope": "Recorded behaviour and perceptions in days [0,27) after first payment; both experimental arms excluded. No survival selection. First renewal primary; age5 retention and ages1–5 contribution secondary. No CAC assigned to diagnostic groups.",
                "estimator": "Descriptive differences standardized to empirical channel × need × acquisition-year (events) or acquisition-month (survey groups) frequencies among outcome-observed members, restricted to common-support strata with n>=2 per comparison group. Pooled and adjusted comparisons use that same support; full-sample crude differences are also saved. Approximate unadjusted 95% normal intervals use sample variances, independent people and fixed weights; no equivalence or causal claim. Residual confounding remains.",
                "survey": "Earliest onboarding response inside the window; timestamp ties use response_id. Raw nominal categories, no-response and unanswered-item remain distinct. Invitations are unobserved. The ongoing-use wave is not pooled into these diagnostics.",
                "refund_sensitivity": "Primary denominators retain members with in-window refunds; refunds do not establish exit. A separate descriptive sensitivity excludes them. Cancellation-request times are unavailable; the window precedes recorded renewal outcomes, not necessarily unrecorded decisions.",
                "timing_audit": audit}
    (output / "diagnostics_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def validate_diagnostics(output_dir: Path) -> dict:
    output = Path(output_dir)
    m = json.loads((output / "diagnostics_manifest.json").read_text())
    expected = {"friction_contrasts.csv", "friction_balance.csv", "friction_refund_sensitivity.csv"}
    if set(m["output_hashes"]) != expected or set(m["input_hashes"]) != {"friction_subjects.csv", "friction_timing_audit.csv"}:
        raise ValueError("Unexpected diagnostic output contract")
    if m["code_sha256"] != _hash(Path(__file__)):
        raise ValueError("Diagnostic code changed; rebuild diagnostics")
    for name, digest in {**m["input_hashes"], **m["output_hashes"]}.items():
        if _hash(output / "tables" / name) != digest: raise ValueError(f"Diagnostic hash mismatch: {name}")
    return m
