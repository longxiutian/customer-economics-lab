"""Journey and acquisition-strategy exhibits, using saved diagnostic outputs."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def add_journey_chart(output, read, done):
    from .diagnostics import build_diagnostics
    build_diagnostics(output)
    f = read("friction_cohort_summary.csv")
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.5), sharex=True, sharey=True,
                             gridspec_kw={"hspace": .25, "wspace": .15})
    for col, need in enumerate(["save_time", "build_skill"]):
        d = f[f.primary_need == need].sort_values("cohort_month")
        x = np.arange(len(d))
        for y, color, style, label in [
            (1 - d.n_no_completion / d.n_acquired, "#185A46", "o-", "Completion"),
            (1 - d.n_no_core_action / d.n_acquired, "#8A5E0E", "s--", "Core use"),
            (d.n_respondents / d.n_acquired, "#5A625D", ".:", "Survey response")]:
            axes[0, col].plot(x, y, style, color=color, lw=1.25, ms=3, label=label)
        axes[0, col].set_title(need.replace("_", " ").title(), loc="left", fontsize=11)
        for column, color, label in [("retained_share_age1", "#185A46", "First renewal"),
                                     ("retained_share_age5", "#8A5E0E", "Age 5")]:
            axes[1, col].plot(x, d[column], "o-", color=color, lw=1.5, ms=3, label=label)
        ticks = [0, 5, 11, 17, 23]
        axes[1, col].set_xticks(ticks, d.cohort_month.str[:7].iloc[ticks], fontsize=7)
        axes[1, col].set_xlabel("Acquisition cohort")
    axes[0, 0].set_ylabel("Recorded in first 27 days")
    axes[1, 0].set_ylabel("Observed retained share")
    for ax in axes.flat:
        ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.grid(alpha=.13)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, 1.04), frameon=False, fontsize=8, ncol=3)
    axes[1, 0].legend(loc="lower left", frameon=False, fontsize=7)
    done(fig, "journey-cohort-diagnostics", ["friction_cohort_summary.csv"],
         "All 24 acquisition cohorts within each need; paid non-experimental people. Features in [0,27 days). First-renewal and age5 outcomes are separate; future outcomes stay missing. Channels are pooled here; adjusted contrasts retain channel and year.",
         {"cohorts": sorted(f.cohort_month.unique()), "needs": ["save_time", "build_skill"], "future_outcomes_imputed": False})


def add_strategy_chart(output, read, done):
    from .postestimation import build_postestimation
    manifest = build_postestimation(output)
    f = read("segment_forecast_curves.csv")
    read("strategic_segment_breakout.csv")
    f = f[f.cohort_month == manifest["selected_cohort"]]
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.4), sharex=True,
                             gridspec_kw={"hspace": .3, "wspace": .22})
    for col, channel in enumerate(["search", "partner"]):
        for need, color in [("save_time", "#8A5E0E"), ("build_skill", "#185A46")]:
            d = f[(f.channel == channel) & (f.primary_need == need)].sort_values("age_month")
            observed = d.observed.astype(bool)
            boundary = int(d.loc[observed, "age_month"].max())
            for row, stem in [(0, "retained_share"), (1, "cash_after_cac")]:
                ax = axes[row, col]
                ax.plot(d.age_month, d[stem + "_mean"], "--", color=color, lw=1.4)
                ax.plot(d.loc[observed, "age_month"], d.loc[observed, stem + "_mean"], "o-", color=color, lw=1.6, ms=3, label=need.replace("_", " "))
                ax.fill_between(d.age_month, d[stem + "_p05"], d[stem + "_p95"], color=color, alpha=.15)
                if need == "save_time": ax.axvline(boundary + .5, color="#5A625D", lw=.8)
        axes[0, col].set_title(channel.title(), loc="left", fontsize=11)
        axes[0, col].set_ylim(0, 1.03); axes[0, col].yaxis.set_major_formatter(PercentFormatter(1))
        axes[1, col].axhline(0, color="#202521", lw=.7)
        axes[1, col].set_xlabel("Receipt number"); axes[1, col].set_xticks([0, 2, 5, 8, 11], [1, 3, 6, 9, 12])
        axes[1, col].set_ylim(-110, 300)
        for ax in axes[:, col]: ax.grid(alpha=.13)
    axes[0, 0].set_ylabel("Retained / originally acquired")
    axes[1, 0].set_ylabel("Cumulative cash after CAC ($)")
    axes[0, 0].legend(loc="lower left", frameon=False, fontsize=8)
    done(fig, "strategic-segment-paths", ["segment_forecast_curves.csv", "strategic_segment_breakout.csv"],
         "Frozen posterior expected paths, no refit; observed solid points, forecast dashed continuations, 5th–95th parameter bands. CAC is acquisition-cell tracked spending / original customers; cash undiscounted. Selection by maturity and assignment.",
         {"selected_cohort": manifest["selected_cohort"], "refit": False, "reconciliation": manifest["reconciliation"]})


def extension_context(output):
    from .report import _table, _latex_table, _tex, _dollars
    f = _table(output, "friction_subjects.csv")
    summary = _table(output, "friction_segment_summary.csv")
    contrasts = _table(output, "friction_contrasts.csv")
    audit = _table(output, "friction_timing_audit.csv").iloc[0]
    sensitivity = _table(output, "friction_refund_sensitivity.csv")
    strategy = _table(output, "strategic_segment_breakout.csv")
    manifest = json.loads((output / "postestimation_manifest.json").read_text())
    selected, prior = manifest["selected_cohort"], manifest["comparison_cohort"]
    labels = {("onboarding", "recorded"): "Completion recorded", ("onboarding", "not_recorded"): "No completion recorded",
              ("early_use", "recorded"): "Core use recorded", ("early_use", "not_recorded"): "No core use recorded",
              ("reported_difficulty", "getting_started"): "Getting started",
              ("reported_difficulty", "finding_features"): "Finding features",
              ("reported_difficulty", "finding_time"): "Finding time",
              ("reported_difficulty", "none"): "No difficulty reported",
              ("reported_difficulty", "no_response"): "No recorded response",
              ("reported_difficulty", "unanswered_item"): "Difficulty item unanswered"}
    rows = []
    for _, r in summary.iterrows():
        if (r.scheme, r.segment) not in labels: continue
        rows.append([labels[r.scheme, r.segment], f"{r.n_age1_observed:,.0f}", f"{r.retained_share_age1:.1%}",
                     f"{r.n_age5_observed:,.0f}", f"{r.retained_share_age5:.1%}", _dollars(r.mean_contribution_ages1_5, 2)])
    first = contrasts[contrasts.outcome == "retained_age1"].set_index("scheme")
    def pp(v): return f"{100*v:+.1f}"
    def contrast_text(scheme):
        r = first.loc[scheme]
        return f"{pp(r.difference)} percentage points (95% interval {pp(r.ci_lower)} to {pp(r.ci_upper)})"
    sentence = (f"After standardizing acquisition year, channel and need, the first-renewal gap is {contrast_text('onboarding')} for no completion versus completion, and {contrast_text('early_use')} for no core use versus core use. These estimates provide little separation, but their intervals do not establish equivalence. The signals record whether steps occurred, not the effort required or the value experienced.")
    flow = (f"{audit.all_acquired:,.0f} acquired customers minus {audit.acquired_experimental:,.0f} buyers assigned to either experimental arm leaves {audit.diagnostic_customers:,.0f} paid non-experimental customers with a complete 27-day window. First renewal is observed for {audit.age1_observed_customers:,.0f} (Jan 2024--Nov 2025); age 5 for {audit.mature_customers:,.0f} (Jan 2024--Jul 2025). All assigned prospects remain in the campaign analysis, including nonbuyers.")
    response = f.response_id.notna().sum()
    survey = (f"Onboarding responses are recorded for {response:,} of {len(f):,} customers ({response/len(f):.1%}). Invitations are unavailable, so no response combines uninvited people and people who did not answer. Difficulty categories are nominal and self-reported; a missing response is not a report of no difficulty.")
    adjust_rows = []
    for _, r in contrasts[contrasts.outcome == "retained_age1"].iterrows():
        adjust_rows.append([r.label.replace("−", "vs."), f"{r.n_target_common:,.0f} / {r.n_reference_common:,.0f}",
                            pp(r.crude_common_difference), pp(r.difference), f"{pp(r.ci_lower)} to {pp(r.ci_upper)}", f"{r.coverage:.0%}"])
    secondary_rows = []
    for scheme in ["onboarding", "early_use", "reported_difficulty"]:
        for _, r in contrasts[(contrasts.scheme == scheme) & (contrasts.outcome == "retained_age5")].iterrows():
            dollar = contrasts[(contrasts.scheme == r.scheme) & (contrasts.target == r.target) & (contrasts.outcome == "contribution_ages1_5")].iloc[0]
            secondary_rows.append([r.label.replace("−", "vs."), f"{pp(r.difference)} ({pp(r.ci_lower)} to {pp(r.ci_upper)})",
                                   f"{_dollars(dollar.difference,2)} ({_dollars(dollar.ci_lower,2)} to {_dollars(dollar.ci_upper,2)})", f"{r.coverage:.0%}"])
    balance = _table(output, "friction_balance.csv")
    balance_rows = [[labels[r.scheme, r.segment], f"{r.n:,.0f}", f"{r.share_partner:.0%}", f"{r.share_build_skill:.0%}",
                     f"{r.share_2025:.0%}", f"{r.share_premium:.0%}", _dollars(r.mean_initial_discount,2), _dollars(r.mean_age0_contribution,2)]
                    for _, r in balance.iterrows() if (r.scheme, r.segment) in labels]
    refund_text = (f"The exposure window contains {audit.in_window_refunds:,.0f} refund records, {audit.in_window_effective_cancellations:,.0f} effective cancellations and {audit.in_window_period_ends:,.0f} period ends. Primary comparisons retain refunding customers. Excluding customers with a refund gives first-renewal adjusted gaps of " +
                  "; ".join(f"{pp(r.difference)} pp ({pp(r.ci_lower)} to {pp(r.ci_upper)}) for {r.label.replace('−','versus').lower()}" for _, r in sensitivity[sensitivity.outcome == "retained_age1"].iterrows()) +
                  ". Refunds do not establish exit. Cancellation-request times are unavailable, so the window precedes recorded renewal outcomes, not necessarily the customer's decision.")
    strategy_rows = []; prior_rows = []
    current = strategy[strategy.cohort_month == selected].sort_values(["channel", "primary_need"])
    old = strategy[strategy.cohort_month == prior].set_index(["channel", "primary_need"])
    for _, r in current.iterrows():
        label = r.channel.title() + " / " + r.primary_need.replace("_", " ")
        strategy_rows.append([label, f"{r.n_acquired:,.0f}", _dollars(r.cac), _dollars(r.ltv_before_cac_mean),
                              f"{_dollars(r.net_ltv_mean)} ({_dollars(r.net_ltv_p05)}--{_dollars(r.net_ltv_p95)})", f"{r.forecast_share:.0%}"])
        p = old.loc[r.channel, r.primary_need]
        prior_rows.append([label, f"{p.n_acquired:,.0f} / {r.n_acquired:,.0f}", f"{p.retained_share_age5:.1%} / {r.retained_share_age5:.1%}",
                           f"{_dollars(p.net_ltv_mean)} / {_dollars(r.net_ltv_mean)}",
                           f"{int(p.payback_month)} / {int(r.payback_month)}"])
    latest_need = current.groupby("primary_need").apply(lambda g: float(np.average(g.net_ltv_mean, weights=g.n_acquired)), include_groups=False)
    payoff = (f"Within {selected[:7]}, build-skill customers have mean net twelve-receipt value of {_dollars(latest_need['build_skill'])}, versus {_dollars(latest_need['save_time'])} for save-time customers, weighted by acquired cell size. This is a candidate distinction for acquisition and service tests; it does not show what the next advertising dollar will earn.")
    rank = _table(output, "strategic_rank_stability.csv")
    rank_rows = []
    for channel, g in rank.groupby("channel", sort=True):
        full = g[g.fully_observed.astype(bool)]
        rank_rows.append([channel.title(), f"{int((g.build_minus_save_net_value > 0).sum())} / {len(g)}",
                          f"{_dollars(g.build_minus_save_net_value.median())} ({_dollars(g.build_minus_save_net_value.min())} to {_dollars(g.build_minus_save_net_value.max())})",
                          f"{int((full.build_minus_save_net_value > 0).sum())} / {len(full)}"])
    search = current[current.channel == "search"].set_index("primary_need")
    gaps = {need: float(search.loc[need, "retained_share_age5"] - old.loc[("search", need), "retained_share_age5"]) for need in search.index}
    search_sentence = ("Search's single-month age-5 shares changed by " +
                       "; ".join(f"{100*gap:+.1f} percentage points for {need.replace('_',' ')}" for need, gap in gaps.items()) +
                       ". These small cells do not establish a retention decline. The pooled January--June comparison remains the within-group retention evidence. Value can rise through lower CAC or higher spending per member without stronger retention.")
    small = lambda table: r"{\fontsize{8}{10}\selectfont " + table + "}"
    return {"friction_profile_table": small(_latex_table(["Recorded group", "N, renewal 1", "Retain 1", "N, age 5", "Retain 5", "Ages 1--5 contribution"], rows, "p{.27\\linewidth}rrrrY")),
            "friction_sentence": _tex(sentence), "friction_flow": _tex(flow), "friction_survey": _tex(survey),
            "friction_adjusted_table": small(_latex_table(["Comparison", "N: target / ref.", "Crude pp", "Adjusted pp", "95% interval", "Coverage"], adjust_rows, "p{.27\\linewidth}YrrYY")),
            "friction_secondary_table": small(_latex_table(["Comparison", "Age-5 gap, pp (95%)", "Ages 1--5 contribution gap (95%)", "Coverage"], secondary_rows, "p{.27\\linewidth}YYp{.09\\linewidth}")),
            "friction_balance_table": small(_latex_table(["Recorded group", "N", "Partner", "Skill", "2025", "Premium", "Discount", "Age-0 contrib."], balance_rows, "p{.25\\linewidth}rYYYYYY")),
            "friction_refund_text": _tex(refund_text),
            "strategic_cohort": selected[:7], "strategic_prior": prior[:7], "strategic_interpretation": _tex(payoff),
            "strategic_value_table": small(_latex_table(["Acquisition group", "N", "CAC", "Value before CAC", "Net value (5th--95th)", "Forecast"], strategy_rows, "p{.23\\linewidth}rrYYY")),
            "strategic_comparison_table": small(_latex_table(["Acquisition group", "N", "Age-5 retained", "Net 12-receipt value", "Payback receipt"], prior_rows, "p{.23\\linewidth}YYYY")),
            "strategic_rank_table": small(_latex_table(["Channel", "Positive gap / pairs", "Median gap (range)", "Fully observed: positive / pairs"], rank_rows)),
            "strategic_retention_sentence": _tex(search_sentence),
            "strategic_scope": _tex(f"Latest non-experimental four-cell cohort with six observed receipts: {selected[:7]}. Same-month prior-year comparator: {prior[:7]}. All {manifest['reconciliation']['cells']} acquisition-cell values and all {manifest['reconciliation']['cohorts']} cohort paths reconcile to the saved baseline before selection; no refit.")}
