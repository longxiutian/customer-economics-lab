"""Segmentation, acquisition-only holdouts and the final value/cost comparison."""
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

def decision_context(output):
    from .report import _table, _latex_table, _tex
    from .decision_metrics import validate_decision_metrics
    validate_decision_metrics(output)
    segments=_table(output,"segmentation_objective.csv")
    cac=_table(output,"channel_cac.csv").sort_values("test_id")
    value=_table(output,"channel_value_decision.csv").sort_values("test_id")
    def money(x):
        if pd.isna(x):return "Not defined"
        return ("-" if x<0 else "")+"$"+format(Decimal(str(abs(x))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),',.2f')
    label=lambda r:r.channel.title()+" / "+r.primary_need.replace('_',' ')
    small=lambda t:r"{\fontsize{8.5}{10.5}\selectfont "+t+"}"
    table=lambda headers,rows,layout:small(_latex_table(headers,rows,layout))
    labels={"primary_need":"Stated need","acquisition_channel":"Acquisition channel","age_band":"Age band","region":"Region"}
    segrows=[[labels[r.scheme],f"{r.within_sd:.2f}",f"{r.between_share:.2%}",f"{r.cohort_centered_between_share:.2%}"] for _,r in segments.iterrows()]
    need=segments.set_index("scheme").loc["primary_need"]
    counts=[[label(r),f"{r.n_treatment:,.0f} / {r.n_control:,.0f}",f"{r.buyers_treatment:,.0f} / {r.buyers_control:,.0f}",f"{r.incremental_buyers:,.0f}"] for _,r in cac.iterrows()]
    costs=[[label(r),money(r.incremental_spend),money(r.credited_cac),money(r.icac)] for _,r in cac.iterrows()]
    intervals=[[label(r),f"{r.incremental_buyers:.0f} ({r.buyers_ci_lower:.1f} to {r.buyers_ci_upper:.1f})",money(r.icac_ci_lower)+" to "+(money(r.icac_ci_upper) if pd.notna(r.icac_ci_upper) else "unbounded")] for _,r in cac.iterrows()]
    values=[[label(r),f"{r.forecast_share:.0%}",money(r.ltv_before_cac_mean),money(r.icac),money(r.value_less_icac)] for _,r in value.iterrows()]
    best=value.sort_values('value_less_icac',ascending=False).iloc[0]
    first=cac.iloc[0]
    return {
      "segmentation_objective_table":table(["Two-cell strategy","Within-cell SD ($)","Between-cell share","After cohort centering"],segrows,"p{.28\\linewidth}YYY"),
      "segmentation_objective_sentence":_tex(f"Stated need separates the group means most strongly among these four candidates: {need.between_share:.2%} of the six-receipt contribution variance lies between its cells, and {need.within_share:.2%} remains within them. After subtracting each joining cohort's mean, the between-cell share is {need.cohort_centered_between_share:.2%}. This is a useful but modest descriptive improvement; substantial customer heterogeneity remains."),
      "segmentation_objective_n":f"{need.n_customers:,.0f}",
      "channel_counts_table":table(["Channel / baseline need","Assigned T / C","Buyers T / C","Additional buyers"],counts,"p{.29\\linewidth}YYY"),
      "channel_cost_table":table(["Channel / baseline need","Additional spend","Credited CAC","iCAC"],costs,"p{.29\\linewidth}YYY"),
      "channel_interval_table":table(["Channel / baseline need","Additional buyers (95%)","iCAC (95%)"],intervals,"p{.30\\linewidth}YY"),
      "channel_example":_tex(f"For {label(first)}, {first.buyers_treatment:.0f} treated prospects acquire and the holdout supplies a baseline of {first.expected_background_buyers:.0f}. The estimated additional acquisitions are {first.incremental_buyers:.0f}. With {money(first.incremental_spend)} in additional acquisition spending, credited CAC is {money(first.credited_cac)} and iCAC is {money(first.icac)}."),
      "channel_value_table":table(["Channel / baseline need","Value forecast share","Contribution LTV","iCAC","Value less iCAC"],values,"p{.26\\linewidth}YYYY"),
      "channel_value_example":_tex(f"For {label(best)}, the planning calculation is {best.incremental_buyers:.0f} additional customers times {money(best.ltv_before_cac_mean)} contribution value, less {money(best.incremental_spend)} acquisition spending: {money(best.planning_net_value)} expected net value. Equivalently, value less iCAC is {money(best.value_less_icac)} per additional customer. This is an assumption-based projection, not a lifetime outcome observed in the holdout."),
      "channel_recommendation":_tex(f"{label(best)} has the largest modeled value less iCAC among the tested cells. Prioritize it for measured expansion, subject to cash capacity and confirmation that the additional customers resemble the value benchmark. Recheck acquisition lift and cost as spend changes; these four tests do not trace an optimal budget curve."),
    }
