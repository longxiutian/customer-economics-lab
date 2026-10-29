"""Report exhibits for comparable segmentation and acquisition-cost estimands."""
from decimal import Decimal, ROUND_HALF_UP

def decision_context(output):
    from .report import _table, _latex_table, _tex
    from .decision_metrics import validate_decision_metrics
    validate_decision_metrics(output)
    segments = _table(output, "segmentation_objective.csv")
    cac = _table(output, "cac_reconciliation.csv")
    money = lambda x: ("-" if x < 0 else "") + "$" + format(Decimal(str(abs(x))).quantize(Decimal(".01"), rounding=ROUND_HALF_UP), ",.2f")
    labels = {"primary_need": "Stated need", "acquisition_channel": "Acquisition channel", "age_band": "Age band", "region": "Region"}
    seg_rows = [[labels[r.scheme], f"{r.within_sd:.2f}", f"{r.between_share:.2%}", f"{r.cohort_centered_between_share:.2%}"] for _, r in segments.iterrows()]
    need = segments.set_index("scheme").loc["primary_need"]
    counts, costs, intervals = [], [], []
    for _, r in cac.iterrows():
        label = ("Tested-program sum" if r.experiment_id == "TESTED_PROGRAM" else
                 "Search / save time" if r.channel == "search" else "Partner / build skill")
        counts.append([label, f"{r.n_treatment:,.0f} / {r.n_control:,.0f}", f"{r.buyers_treatment:,.0f}", f"{r.expected_buyers_without_tested_campaign:,.0f}", f"{r.incremental_buyers:,.0f}"])
        costs.append([label, money(r.incremental_media_spend), money(r.treatment_media_cac), f"{r.estimated_background_share:.1%}", money(r.incremental_media_cac)])
        interval = (money(r.icac_ci_lower) + " to " + money(r.icac_ci_upper) if r.icac_interval_status == "finite" else
                    money(r.icac_ci_lower) + " to unbounded" if r.icac_interval_status == "unbounded" else "No positive-lift interval")
        intervals.append([label, f"{r.incremental_buyers:.0f} ({r.incremental_buyers_ci_lower:.1f} to {r.incremental_buyers_ci_upper:.1f})", interval])
    small = lambda t: r"{\fontsize{8.5}{10.5}\selectfont " + t + "}"
    return {
        "segmentation_objective_table": small(_latex_table(["Two-cell strategy", "Within-cell SD ($)", "Between-cell share", "After cohort centering"], seg_rows, "p{.28\\linewidth}YYY")),
        "segmentation_objective_sentence": _tex(f"Stated need separates the group means most strongly among these four candidates: {need.between_share:.2%} of the six-receipt contribution variance lies between its cells, and {need.within_share:.2%} remains within them. After subtracting each joining cohort's mean, the between-cell share is {need.cohort_centered_between_share:.2%}. This is a useful but modest descriptive improvement, not homogeneous customers or demonstrated intervention effects."),
        "segmentation_objective_n": f"{need.n_customers:,.0f}",
        "cac_counts_table": small(_latex_table(["Test", "Assigned T / C", "T buyers", "Expected baseline", "Incremental buyers"], counts, "p{.25\\linewidth}YYYY")),
        "cac_costs_table": small(_latex_table(["Test", "Extra media", "Credited CAC", "Background share", "Media iCAC"], costs, "p{.25\\linewidth}YYYY")),
        "cac_intervals_table": small(_latex_table(["Test", "Incremental buyers (95%)", "Media iCAC (95%)"], intervals, "p{.28\\linewidth}YY")),
        "cac_contribution_sentence": _tex("The all-assigned point decompositions are " + "; ".join(
            f"{r.channel.title()}: {money(r.incremental_contribution/r.incremental_buyers)} contribution per incremental acquisition versus {money(r.incremental_media_cac)} media iCAC, leaving {money(r.incremental_contribution_after_media)} total net contribution"
            for _, r in cac[cac.scope == "individual_test"].iterrows()) + ". The value-to-cost ratios are " + " and ".join(
            f"{r.incremental_contribution/r.incremental_media_spend:.2f}" for _, r in cac[cac.scope == "individual_test"].iterrows()) +
            ". These contribution-per-incremental-buyer ratios are point decompositions; their intervals would require the joint value/lift distribution. The existing net-contribution intervals remain the inferential statements."),
    }
