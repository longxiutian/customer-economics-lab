"""Present the complete monthly acquisition-testing history from saved SQL."""
from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd


def prepare_holdout_history(output: Path, charts: dict, plan: pd.DataFrame) -> tuple[dict, dict]:
    from .report import _table, _save, _sha, _tex, _dollars, _latex_table
    history = _table(output, "channel_cac.csv").sort_values(["test_month", "test_id"])
    current = _table(output, "channel_cac_current.csv")
    if set(current.test_id) != set(plan.test_id):
        raise ValueError("Planning must use every cell's latest completed acquisition test")
    if len(history) != 24 or history.test_month.nunique() != 6 or plan.test_month.nunique() != 1:
        raise ValueError("Review the six-wave acquisition-history presentation for changed coverage")
    if not ((history.n_treatment == 500).all() and (history.n_control == 500).all()
            and (history.spend_treatment == 11000).all() and (history.spend_control == 0).all()
            and (history.followup_days == 31).all()):
        raise ValueError("Review the shared sample, spending and follow-up statements")
    label = lambda r: r.channel.title() + " / " + r.primary_need.replace("_", " ")
    money = _dollars
    month = lambda x: pd.Timestamp(x).strftime("%B %Y")
    date = lambda x: pd.Timestamp(x).strftime("%B %d, %Y").replace(" 0", " ")
    months = sorted(history.test_month.unique())
    first = history[history.test_month == months[0]]
    initial = first.merge(plan[["channel", "primary_need", "ltv_before_cac_mean"]],
                          on=["channel", "primary_need"], validate="one_to_one")
    initial["value_less_icac"] = initial.ltv_before_cac_mean - initial.icac
    initial_best = initial.sort_values("value_less_icac", ascending=False).iloc[0]
    latest_best = plan.sort_values("value_less_icac", ascending=False).iloc[0]
    trend = []
    for channel in ["search", "partner"]:
        earlier = first[(first.channel == channel) & (first.primary_need == "build_skill")].iloc[0]
        later = current[(current.channel == channel) & (current.primary_need == "build_skill")].iloc[0]
        trend.append(f"{label(later)} iCAC moved from {money(earlier.icac)} to {money(later.icac)}")

    add_holdout_chart(output, charts)

    def history_table(selected):
        rows = [[pd.Timestamp(r.test_month).strftime("%b"), label(r),
                 f"{int(r.buyers_treatment)} / {int(r.buyers_control)}", str(int(r.incremental_buyers)),
                 money(r.credited_cac),
                 f"{money(r.icac)} ({money(r.icac_ci_lower)}–{money(r.icac_ci_upper)})"]
                for r in selected.itertuples()]
        return (r"{\fontsize{8.5}{10.5}\selectfont "
                + _latex_table(["Enrollment", "Channel / stated need", "Buyers T / C", "Additional buyers",
                                "Credited CAC", "iCAC (95% interval)"], rows,
                               r"p{.10\linewidth}p{.24\linewidth}YY Yp{.23\linewidth}") + "}")
    waves = history.groupby("test_month", sort=True).agg(
        closed_at=("followup_end_at", "max"), spend=("spend_treatment", "sum"), tests=("test_id", "count"))
    schedule_rows = [[month(m), date(r.closed_at), money(r.spend)] for m, r in waves.iterrows()]
    schedule = (r"{\fontsize{9}{11.2}\selectfont "
                + _latex_table(["Enrollment wave", "Results available at", "Research spending"], schedule_rows,
                               r"p{.30\linewidth}YY") + "}")
    context = {
        "b_latest_test_month": _tex(month(months[-1])),
        "b_latest_test_closed": _tex(date(current.followup_end_at.max())),
        "b_holdout_trend": _tex("; ".join(trend) + ". Monthly controls keep changes in background acquisition in the calculation."),
        "b_decision_shift": _tex(f"Holding the current value benchmarks fixed, the July costs would favor {label(initial_best)}; the latest costs favor {label(latest_best)}."),
        "b_history_early": history_table(history[history.test_month.isin(months[:3])]),
        "b_history_late": history_table(history[history.test_month.isin(months[3:])]),
        "b_holdout_schedule": schedule,
        "b_wave_budget": _tex(money(waves.spend.iloc[-1])),
        "b_program_budget": _tex(money(waves.spend.sum())),
        "b_test_prospects": f"{int((history.n_treatment + history.n_control).sum()):,}",
    }
    evidence = {
        "history_tests": len(history), "enrollment_waves": len(waves),
        "assigned_prospects": int((history.n_treatment + history.n_control).sum()),
        "current_test_ids": sorted(current.test_id.tolist()),
        "latest_results_available_at": str(current.followup_end_at.max()),
        "latest_wave_spend": float(waves.spend.iloc[-1]), "all_wave_spend": float(waves.spend.sum()),
        "initial_cost_candidate_at_current_value_benchmark": label(initial_best),
        "current_candidate": label(latest_best),
        "selection": "Latest complete 31-day test per channel/need; no significance screen, cross-wave pooling or early stopping.",
        "value_clock": "Current tests paired with the latest common operational cohort having six observed receipts. The July-cost comparison holds today's value benchmark fixed; it is not a reconstructed July decision.",
    }
    return context, evidence


def add_holdout_chart(output: Path, charts: dict):
    """Create the acquisition-only history before any LTV model is required."""
    from .report import _table, _save, _sha
    history = _table(output, "channel_cac.csv").sort_values(["test_month", "test_id"])
    if len(history) != 24 or history.test_month.nunique() != 6:
        raise ValueError("Expected all six monthly acquisition waves")
    months = sorted(history.test_month.unique())
    label = lambda r: r.channel.title() + " / " + r.primary_need.replace("_", " ")
    directory = output / "report" / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    charts["sources"]["channel_cac.csv"] = _sha(output / "tables/channel_cac.csv")
    fig, ax = plt.subplots(figsize=(7.1, 2.45))
    palette = {("search", "build_skill"): "#17656b", ("partner", "build_skill"): "#966726",
               ("search", "save_time"): "#6889a9", ("partner", "save_time"): "#a76e83"}
    for (channel, need), color in palette.items():
        rows = history[(history.channel == channel) & (history.primary_need == need)].sort_values("test_month")
        ax.plot(range(len(rows)), rows.icac, marker="o", markersize=3.5, linewidth=1.7,
                color=color, linestyle="-" if need == "build_skill" else "--", label=label(rows.iloc[0]))
    ax.set_xticks(range(len(months)), [pd.Timestamp(x).strftime("%b") for x in months])
    ax.set_ylabel("Cost per additional buyer", fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, pos: "$" + format(value, ".0f")))
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", alpha=.16)
    ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.01), ncol=2, frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(left=.12, right=.98, bottom=.15, top=.76)
    directory = output / "report" / "figures"
    files = _save(fig, directory, "channel-icac-history")
    display = history[["test_id", "test_month", "followup_end_at", "channel", "primary_need", "icac"]].to_dict("records")
    charts["figures"]["channel-icac-history"] = {
        "files": files, "sources": ["channel_cac.csv"], "display_values": display,
        "notes": "Each point uses its own contemporaneous randomized control and complete 31-day window. Enrollment months are shown; no pooling or within-wave early stopping. Per-test intervals are in the appendix.",
        "sha256": {name: _sha(directory / name) for name in files}}
