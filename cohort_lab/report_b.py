"""Version B pairs monthly acquisition costs with verified operating-cohort evidence."""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd


def incremental_planning(values: pd.DataFrame, cells: pd.DataFrame, paths: pd.DataFrame) -> pd.DataFrame:
    """Price the saved benchmark contribution path at current iCAC, without a refit."""
    keys = ["cohort_month", "channel", "primary_need"]
    result = values.merge(cells[keys + ["cac", "payback_month"]], on=keys, how="left",
                          validate="one_to_one").rename(columns={
        "cac": "historical_cac", "payback_month": "historical_payback_receipt"})
    if result.historical_cac.isna().any() or result.test_id.duplicated().any():
        raise ValueError("Every pilot needs exactly one supported historical benchmark")
    recovery = []
    for row in result.itertuples():
        path = paths[(paths.cohort_month == row.cohort_month) & (paths.channel == row.channel)
                     & (paths.primary_need == row.primary_need)].sort_values("age_month")
        if not np.array_equal(path.age_month.to_numpy(), np.arange(int(row.horizon_months))):
            raise ValueError("Benchmark contribution path must cover the full valuation horizon")
        # Restore the historical acquisition cost once, then compare with iCAC.
        cumulative = path.cash_after_cac_mean.to_numpy(float) + row.historical_cac
        if not np.isfinite(cumulative).all() or not np.isfinite(row.icac):
            raise ValueError("Incremental planning requires finite costs and contribution")
        crossings = np.flatnonzero(cumulative >= row.icac)
        recovery.append(float(path.age_month.iloc[crossings[0]] + 1) if crossings.size else np.nan)
    result["planning_payback_receipt"] = recovery
    result["break_even_value_share"] = result.icac / result.ltv_before_cac_mean
    result["planning_scope"] = ("Additional buyers assumed to follow the matching operational mean contribution path; "
                                "not observed pilot payback or a joint uncertainty interval.")
    return result.sort_values(["value_less_icac", "test_id"], ascending=[False, True]).reset_index(drop=True)


def prepare_version_b(output: Path, context: dict, charts: dict) -> dict:
    from .report import _table, _sha, _write_json, _tex, _dollars, _latex_table, _save, COLORS
    directory = output / "report"
    names = ["channel_value_decision.csv", "strategic_segment_breakout.csv",
             "segment_forecast_curves.csv", "segmentation_objective.csv",
             "segmentation_profile.csv", "cohort_valuation.csv", "company_totals.csv",
             "strategic_rank_stability.csv", "channel_cac.csv", "channel_cac_current.csv"]
    frames = {name: _table(output, name) for name in names}
    sources = {name: _sha(output / "tables" / name) for name in names}
    charts["sources"].update(sources)
    plan = incremental_planning(frames[names[0]], frames[names[1]], frames[names[2]])
    if len(plan) != 4 or plan.cohort_month.nunique() != 1:
        raise ValueError("Version B compares four campaigns against one maturity-selected cohort")
    plan.to_csv(directory / "incremental-planning.csv", index=False, float_format="%.10f", lineterminator="\n")
    best = plan.iloc[0]
    positive = plan[plan.value_less_icac > 0]
    if len(positive) < 2 or pd.isna(best.planning_payback_receipt):
        raise ValueError("Review the comparison narrative: the reference decision has changed")
    runner = positive.iloc[1]
    if (len(positive) != 2 or not (positive.primary_need == "build_skill").all()
            or not best.icac_ci_upper < best.ltv_before_cac_mean
            or not runner.icac_ci_lower < runner.ltv_before_cac_mean < runner.icac_ci_upper
            or plan[plan.primary_need == "save_time"].planning_payback_receipt.notna().any()):
        raise ValueError("Review the acquisition-choice prose against the current cost evidence")
    from .holdout_report import prepare_holdout_history
    holdout_context, holdout_evidence = prepare_holdout_history(output, charts, plan)
    label = lambda r: str(r.channel).title() + " / " + str(r.primary_need).replace("_", " ")
    money = lambda x: _dollars(x)
    table = lambda heads, rows, layout=None: r"{\fontsize{9}{11.2}\selectfont " + _latex_table(heads, rows, layout) + "}"
    receipt = lambda x: "Beyond 12" if pd.isna(x) else str(int(x))
    a, z = context["renewal_window_evidence"]["earlier"], context["renewal_window_evidence"]["later"]
    if not (z["retained_share"] > a["retained_share"] and z["contribution_per_customer"] > a["contribution_per_customer"]
            and z["blended_cac"] < a["blended_cac"]):
        raise ValueError("Review Version B's direction findings against changed evidence")
    cash_gain = z["cash_after_cac_per_customer"] - a["cash_after_cac_per_customer"]
    cost_gain = a["blended_cac"] - z["blended_cac"]
    contribution_gain = z["contribution_per_customer"] - a["contribution_per_customer"]
    if not np.isclose(cash_gain, cost_gain + contribution_gain, atol=1e-8):
        raise ValueError("Cash improvement must reconcile to contribution and acquisition cost")
    profile = frames["segmentation_profile.csv"].query("scheme == 'primary_need'").sort_values("mean_contribution")
    lo, hi = profile.iloc[0], profile.iloc[-1]
    objectives = frames["segmentation_objective.csv"].sort_values("between_share", ascending=False)
    if objectives.iloc[0].scheme != "primary_need":
        raise ValueError("Review Version B's segmentation finding against changed candidates")
    objective = objectives.iloc[0]
    last = frames["company_totals.csv"].sort_values("calendar_month").iloc[-1]
    valuations = frames["cohort_valuation.csv"].sort_values("cohort_month")
    fully = valuations[valuations.forecast_share.abs() < 1e-9]
    old, recent = fully.iloc[0], fully.iloc[-1]
    selected = plan.cohort_month.iloc[0]
    model = json.loads((output / "model_summary.json").read_text(encoding="utf-8"))
    bt, vb = model["backtest"], model["valuation_backtest"]
    if set(frames["segment_forecast_curves.csv"].channel)!={"partner","search"}:
        raise ValueError("Review the Version B reference-panel parameter display")
    context["parameter_table"]="\n".join(line for line in context["parameter_table"].splitlines() if "organic" not in line)
    source_map = [
        ("fig:business-journey", ["diagrams/business-journey.json"]),
        ("fig:channel-icac-history", ["tables/channel_cac.csv"]),
        ("tab:channel-results-b", ["tables/channel_cac_current.csv"]),
        ("fig:retention-triangle", ["tables/cohort_totals.csv"]),
        ("fig:cash-triangle", ["tables/cohort_cash_economics.csv"]),
        ("tab:need-profile-b", ["tables/segmentation_profile.csv"]),
        ("fig:channel-retention", ["tables/cohort_age_summary.csv"]),
        ("tab:segment-progress", ["report/matched_cohort_comparison.json"]),
        ("fig:cohort-layers", ["tables/company_month.csv"]),
        ("fig:company-cash", ["tables/company_totals.csv"]),
        ("fig:retention-forecast", ["tables/forecast_curve.csv"]),
        ("fig:ltv-cac", ["tables/cohort_valuation.csv"]),
        ("tab:strategic-value", ["tables/strategic_segment_breakout.csv"]),
        ("tab:cost-bases-b", ["report/incremental-planning.csv"]),
        ("fig:incremental-cash-b", ["tables/segment_forecast_curves.csv", "report/incremental-planning.csv"]),
        ("tab:channel-value-b", ["tables/channel_value_decision.csv", "report/incremental-planning.csv"])]
    _write_json(directory / "exhibit-source-map.json", {
        "scope": "Main report exhibits; appendix exhibits retain local source notes. Paths relative to this output.",
        "exhibits": [{"label": k, "sources": v} for k, v in source_map],
        "executive_metrics": "report/executive_metrics.csv", "presentation_evidence": "report/version-b-evidence.json"})
    source_rows = []
    for key, files in source_map:
        kind = "Figure" if key.startswith("fig:") else "Table"
        source_rows.append(kind + r"~\ref{" + key + "} & "
                           + r"\newline ".join(r"\Code{" + path.split("/")[-1] + "}" for path in files) + r"\\")
    source_table = (r"{\fontsize{8}{10}\selectfont\begin{tabularx}{\linewidth}{@{}p{.22\linewidth}Y@{}}\toprule "
                    + r"\textbf{Main exhibit} & \textbf{Saved source}\\\midrule "
                    + "\n".join(source_rows) + r"\bottomrule\end{tabularx}}")
    prepare_incremental_cash_chart(output, charts, plan=plan)
    _write_json(directory / "chart_manifest.json", charts)
    _write_json(directory / "version-b-evidence.json", {
        "variant": "B", "main_pages": 15, "model_refit": False, "sources": sources,
        "benchmark_cohort": selected, "cash_improvement": cash_gain, "lower_cac_contribution": cost_gain,
        "higher_contribution": contribution_gain,
        "candidate": {"channel": best.channel, "primary_need": best.primary_need,
                      "selection_rule": "Largest point contribution value less iCAC among tested campaigns"},
        "planning_calculation": "Saved cumulative cash after historical CAC + historical CAC; compare with current iCAC. First crossing counted from payment 1.",
        "continuous_holdouts": holdout_evidence,
        "scope": "Same seven operational CSVs and fitted models as A; acquisition-only history extended to six monthly waves in dataset 5.1. No experimental customer-value outcomes."})
    counts = [[label(r), f"{int(r.buyers_treatment)} / {int(r.buyers_control)}", str(int(r.incremental_buyers)),
               money(r.credited_cac), money(r.icac)] for r in plan.sort_values("test_id").itertuples()]
    costs = [[label(r), money(r.historical_cac), money(r.credited_cac), money(r.icac)] for r in plan.itertuples()]
    decision = [[label(r), money(r.ltv_before_cac_mean),
                 f"{money(r.icac)} ({money(r.icac_ci_lower)}–{money(r.icac_ci_upper)})",
                 money(r.value_less_icac), f"{r.break_even_value_share:.1%}"] for r in plan.itertuples()]
    value_rows = [[label(r), str(int(r.n_acquired)), money(r.ltv_before_cac_mean), money(r.historical_cac),
                   money(r.ltv_before_cac_mean-r.historical_cac), f"{r.forecast_share:.0%}"] for r in plan.itertuples()]
    need_rows = [[str(r.segment).replace("_", " ").capitalize(), f"{int(r.n):,}",
                  f"{r.retained_share:.1%}", money(r.mean_contribution)]
                 for r in profile.sort_values("mean_contribution", ascending=False).itertuples()]
    validation_rows = [
        ["Renewing customers: MAE", bt["training_last_calendar_month"][:7],
         f"{bt['retention_mae']:.2f}", f"{bt['baseline_retention_mae']:.2f}", "People per cell"],
        ["Revenue: WAPE", bt["training_last_calendar_month"][:7],
         f"{bt['revenue_wape']:.1%}", f"{bt['baseline_revenue_wape']:.1%}", "Revenue-weighted error"],
        ["First-year value: MAE", vb["training_last_calendar_month"][:7],
         _dollars(vb["ltv_mae"],2), _dollars(vb["baseline_ltv_mae"],2), "Dollars per original customer"]]
    default_action = (f"Prioritize {label(best)} for a measured acquisition expansion. "
                      f"Its first-year contribution-value benchmark is {money(best.ltv_before_cac_mean)}, "
                      f"against {money(best.icac)} per additional customer. "
                      "Finance should set the spending step and acceptable recovery period before expansion.")
    default_verdict = ("Comparable 2025 cohorts retain more customers, generate more contribution "
                       "and recover acquisition spending sooner. Studio North's customer economics are improving.")
    summary = {
        "b_verdict": context["learner_verdict"] if (output/"learner_choices.json").exists() else _tex(default_verdict),
        "b_action": context["learner_action"] if (output/"learner_choices.json").exists() else _tex(default_action),
        "b_best": _tex(label(best)), "b_runner": _tex(label(runner)),
        "b_best_payback": receipt(best.planning_payback_receipt), "b_runner_payback": receipt(runner.planning_payback_receipt),
        "b_best_historical_payback": receipt(best.historical_payback_receipt),
        "b_runner_historical_payback": receipt(runner.historical_payback_receipt),
        "b_best_extra_buyers": str(int(best.incremental_buyers)),
        "b_raw_gain": f"{100*(z['retained_share']-a['retained_share']):.1f}",
        "b_within_gain": f"{100*(z['paid_fixed_mix_retention']-a['paid_fixed_mix_retention']):.0f}",
        "b_need_points": f"{100*(hi.retained_share-lo.retained_share):.0f}",
        "b_month": _tex(pd.Timestamp(selected).strftime("%B %Y")),
        "b_first_cohort": _tex(pd.Timestamp(old.cohort_month).strftime("%B %Y")),
        "b_last_cohort": _tex(pd.Timestamp(recent.cohort_month).strftime("%B %Y")),
        "b_company_month": _tex(pd.Timestamp(last.calendar_month).strftime("%B %Y")),
        "b_best_ci": _tex(f"{money(best.icac_ci_lower)}–{money(best.icac_ci_upper)}"),
        "b_runner_ci": _tex(f"{money(runner.icac_ci_lower)}–{money(runner.icac_ci_upper)}"),
        "b_channel_table": table(["Channel / stated need", "Buyers: campaign / holdout", "Additional buyers", "Credited CAC", "iCAC"], counts, r"p{.26\linewidth}YYYY"),
        "b_cost_table": table(["Channel / stated need", "Historical avg. CAC", "Latest credited CAC", "Latest iCAC"], costs, r"p{.30\linewidth}YYY"),
        "b_decision_table": table(["Campaign / stated need", "First-year value", "iCAC (95% interval)", "Value less iCAC", "Break-even value share"], decision, r"p{.23\linewidth}Yp{.25\linewidth}YY"),
        "b_value_table": table(["Channel / stated need", "Customers", "Value before CAC", "Historical CAC", "Value after CAC", "Forecast share"], value_rows, r"p{.23\linewidth}rYYYY"),
        "b_need_table": table(["Stated need", "Customers", "Retained at sixth payment", "Six-payment contribution"], need_rows, r"p{.24\linewidth}rYY"),
        "b_validation_table": table(["Measure", "Training through", "Model", "Baseline", "Unit"], validation_rows, r"p{.27\linewidth}YrrY"),
        "b_source_map": source_table,
        "b_validation_scope": _tex(f"Renewal and revenue tests train through {bt['training_last_calendar_month'][:7]} and withhold "
                                  + ", ".join(x[:7] for x in bt["held_out_calendar_months"])
                                  + f". The separate first-year valuation check trains through {vb['training_last_calendar_month'][:7]}.")}
    for key, value in {
        "best_value": best.ltv_before_cac_mean, "best_icac": best.icac, "best_gap": best.value_less_icac,
        "runner_value": runner.ltv_before_cac_mean, "runner_gap": runner.value_less_icac,
        "pilot_spend": best.incremental_spend, "best_total_value": best.incremental_buyers*best.ltv_before_cac_mean,
        "best_total_net": best.planning_net_value, "cash_gain": cash_gain, "cac_gain": cost_gain,
        "contribution_gain": contribution_gain, "need_dollars": hi.mean_contribution-lo.mean_contribution,
        "first_value": old.net_ltv_mean, "last_value": recent.net_ltv_mean,
        "company_cash": last.contribution-last.acquisition_spend, "company_spend": last.acquisition_spend,
        "icac_min": plan.icac.min(), "icac_max": plan.icac.max()}.items():
        summary["b_"+key] = _tex(money(value))
    for key, value in {
        "best_break_even": best.break_even_value_share, "runner_break_even": runner.break_even_value_share,
        "forecast_min": plan.forecast_share.min(), "forecast_max": plan.forecast_share.max(),
        "background_min": (plan.expected_background_buyers/plan.buyers_treatment).min(),
        "background_max": (plan.expected_background_buyers/plan.buyers_treatment).max()}.items():
        summary["b_"+key] = _tex(f"{value:.1%}" if "break_even" in key else f"{value:.0%}")
    for key, value in {"retention_earlier": a["retained_share"], "retention_later": z["retained_share"],
                       "fixed_retention": z["paid_fixed_mix_retention"], "need_between": objective.between_share,
                       "need_within": objective.within_share, "other_between": objectives.iloc[1:].between_share.max()}.items():
        summary["b_"+key] = _tex(f"{value:.1%}")
    example = plan.sort_values("test_id").iloc[0]
    summary["b_pilot_example"] = _tex(
        f"{label(example)} recorded {int(example.buyers_treatment)} treated buyers and "
        f"{int(example.expected_background_buyers)} holdout buyers. The campaign therefore added "
        f"{int(example.incremental_buyers)} buyers. Dividing {money(example.incremental_spend)} by those "
        f"additional buyers gives {money(example.icac)} iCAC, versus {money(example.credited_cac)} "
        "when every treated buyer receives campaign credit.")
    summary.update(holdout_context)
    return summary


def prepare_incremental_cash_chart(output: Path, charts: dict, *, plan=None):
    """Expose the acquisition/value exhibit at checkpoint 16, before the PDF."""
    from .report import _table, _save, _sha, COLORS
    directory = output / "report"
    (directory / "figures").mkdir(parents=True, exist_ok=True)
    names = ["channel_value_decision.csv", "strategic_segment_breakout.csv", "segment_forecast_curves.csv"]
    frames = {name: _table(output, name) for name in names}
    charts["sources"].update({name: _sha(output / "tables" / name) for name in names})
    if plan is None:
        plan = incremental_planning(frames[names[0]], frames[names[1]], frames[names[2]])
    if len(plan) != 4 or plan.cohort_month.nunique() != 1:
        raise ValueError("Expected four acquisition cells and one maturity-selected cohort")
    plan.to_csv(directory / "incremental-planning.csv", index=False, float_format="%.10f", lineterminator="\n")
    label = lambda r: str(r.channel).title() + " / " + str(r.primary_need).replace("_", " ")
    receipt = lambda x: "Beyond 12" if pd.isna(x) else str(int(x))
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.4), sharex=True, sharey=True,
                             gridspec_kw={"hspace": .44, "wspace": .19})
    path_data = frames["segment_forecast_curves.csv"]
    display_paths = []
    for ax, row in zip(axes.flat, plan.itertuples()):
        path = path_data[(path_data.cohort_month == row.cohort_month) & (path_data.channel == row.channel)
                         & (path_data.primary_need == row.primary_need)].sort_values("age_month")
        x = path.age_month.to_numpy(int) + 1
        y = path.cash_after_cac_mean.to_numpy(float) + row.historical_cac
        observed = path.observed.astype(str).str.lower().isin(["true", "1"]).to_numpy()
        ax.plot(x[observed], y[observed], "o-", color=COLORS["teal"], lw=1.8, ms=3)
        start = max(0, int(observed.sum()) - 1)
        ax.plot(x[start:], y[start:], "--", color=COLORS["teal"], lw=1.8)
        ax.axhline(row.historical_cac, color=COLORS["muted"], lw=1, ls=":")
        ax.axhline(row.icac, color=COLORS["orange"], lw=1.3, ls="-.")
        ax.axvline(x[observed][-1], color=COLORS["muted"], alpha=.35, lw=.7)
        ax.set_title(label(row), loc="left", fontsize=10)
        ax.text(.03, .96, "iCAC recovery: " + receipt(row.planning_payback_receipt)
                + (" payments" if pd.notna(row.planning_payback_receipt) else ""),
                transform=ax.transAxes, va="top", fontsize=8, color=COLORS["ink"])
        ax.set_xlim(1, 12); ax.set_xticks([1, 3, 6, 9, 12])
        ax.set_ylim(0, max(350, float(plan.icac.max()) * 1.12))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, pos: "$" + format(value, ".0f")))
        ax.grid(alpha=.12)
        display_paths.append({"test_id": row.test_id, "payments": x.tolist(), "cumulative_contribution": y.tolist(),
                              "historical_cac": float(row.historical_cac), "icac": float(row.icac)})
    for ax in axes[1]: ax.set_xlabel("Monthly payment")
    for ax in axes[:, 0]: ax.set_ylabel("Contribution / customer")
    fig.legend(handles=[
        Line2D([0], [0], color=COLORS["teal"], label="Contribution: solid observed / dashed forecast"),
        Line2D([0], [0], color=COLORS["muted"], ls=":", label="Historical average CAC"),
        Line2D([0], [0], color=COLORS["orange"], ls="-.", label="Latest completed test: iCAC")],
        loc="upper center", bbox_to_anchor=(.5, 1.045), ncol=2, frameon=False, fontsize=8)
    figure_files = _save(fig, directory / "figures", "incremental-cash-paths")
    charts["figures"]["incremental-cash-paths"] = {
        "files": figure_files, "sources": names[:3],
        "notes": "Mean contribution compared with historical CAC and latest completed iCAC; incremental recovery conditional on path transfer.",
        "display_values": display_paths,
        "sha256": {name: _sha(directory / "figures" / name) for name in figure_files}}
    return plan
