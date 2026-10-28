"""Deterministic figures and a portrait report from verified SQL/model tables.

This module never reads raw customer CSVs or constructs alternative aggregates.
It selects, pivots and displays saved outputs. Summation is used only for explicit
reconciliation checks. The source tables remain the numerical authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.ticker import PercentFormatter, FuncFormatter
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
EPOCH = 1794787200  # 2026-11-16 00:00 UTC; no wall-clock values in artifacts.
FIXED_DATE = datetime.fromtimestamp(EPOCH, timezone.utc)
COLORS = {"ink": "#172D3C", "teal": "#087F8C", "gold": "#B78431",
          "orange": "#B75C22", "muted": "#526875", "rule": "#CEDBDC"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required verified output is missing: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _table(output: Path, name: str, columns: tuple[str, ...] = ()) -> pd.DataFrame:
    path = output / "tables" / name
    if not path.exists():
        raise FileNotFoundError(f"Run the analysis stage first; missing tables/{name}")
    df = pd.read_csv(path)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")
    return df


def _col(df: pd.DataFrame, *names: str) -> str:
    for name in names:
        if name in df:
            return name
    raise ValueError(f"Verified table lacks required field; expected one of {names}, got {list(df.columns)}")


def _style() -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                        "axes.titlesize": 11, "axes.titleweight": "bold",
                        "axes.labelsize": 9, "axes.edgecolor": COLORS["rule"],
                        "axes.labelcolor": COLORS["ink"], "text.color": COLORS["ink"],
                        "xtick.color": COLORS["muted"], "ytick.color": COLORS["muted"],
                        "axes.spines.top": False, "axes.spines.right": False,
                        "figure.facecolor": "white", "axes.facecolor": "white",
                        "savefig.facecolor": "white", "pdf.fonttype": 42,
                        "svg.hashsalt": "customer-economics-lab-v1"})


def _save(fig, directory: Path, name: str) -> list[str]:
    fig.savefig(directory / f"{name}.pdf", bbox_inches="tight",
                metadata={"Creator": "Customer Economics Lab", "CreationDate": FIXED_DATE,
                          "ModDate": FIXED_DATE, "Title": name})
    fig.savefig(directory / f"{name}.png", dpi=180, bbox_inches="tight",
                metadata={"Software": "Customer Economics Lab"})
    plt.close(fig)
    return [f"{name}.pdf", f"{name}.png"]


def _months(ax, values, count=6):
    n = len(values)
    idx = np.unique(np.linspace(0, max(0, n - 1), min(count, n), dtype=int))
    ax.set_xticks(idx, [str(values[i])[:7] for i in idx], rotation=0, fontsize=8)


def _selected(values, number=6):
    v = sorted(set(map(str, values)))
    return [v[i] for i in np.unique(np.linspace(0, len(v) - 1, min(number, len(v)), dtype=int))]


def _currency(x, _pos=None):
    return (f"${x / 1000:,.1f}k" if abs(x)<10000 else f"${x / 1000:,.0f}k") if abs(x) >= 1000 else f"${x:,.0f}"


def _validate_unique(df, keys, label):
    if df.duplicated(keys).any():
        raise ValueError(f"{label} contains repeated {keys}; plotting would hide a grain error")


def _validate_model_outputs(output: Path) -> dict:
    manifest=_json(output/"model_manifest.json")
    expected={"model_summary.json","posterior_draws.json","tables/cohort_valuation.csv",
              "tables/cohort_valuation_by_segment.csv","tables/forecast_curve.csv","tables/backtest.csv","tables/valuation_backtest.csv","tables/model_fit_checks.csv"}
    if set(manifest.get("output_hashes",{}))!=expected:
        raise ValueError("Unexpected model output contract; rebuild the forecast")
    for name,value in manifest["output_hashes"].items():
        path=output/name
        if not path.is_file() or _sha(path)!=value:raise ValueError(f"Model output hash mismatch: {name}")
    for name,value in manifest.get("input_hashes",{}).items():
        if name not in {"cohort_age_summary.csv","cohort_acquisition_costs.csv","cohort_cash_economics.csv"}:raise ValueError("Unexpected model input")
        if _sha(output/"tables"/name)!=value:raise ValueError(f"Model input changed: {name}; refit before reporting")
    if set(manifest.get("input_hashes",{}))!={"cohort_age_summary.csv","cohort_acquisition_costs.csv","cohort_cash_economics.csv"}:raise ValueError("Missing model input hashes")
    if manifest.get("code_sha256")!=_sha(Path(__file__).with_name("model.py")):raise ValueError("Model code changed; refit before reporting")
    return {"status":"passed","model_manifest_sha256":_sha(output/"model_manifest.json")}


def build_charts(output_dir: Path) -> dict:
    """Create analysis charts; add forecast charts when model outputs exist."""
    output = Path(output_dir).resolve()
    from .analysis import validate_analysis
    validate_analysis(output)
    directory = output / "report" / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    _style()
    manifest = {"version": 1, "source_date_epoch": EPOCH, "sources": {}, "figures": {},
                "numerical_policy": "Select/pivot saved SQL/model outputs; never recalculate source aggregates."}
    def read(name, cols=()):
        df = _table(output, name, cols)
        manifest["sources"][name] = _sha(output / "tables" / name)
        return df
    def done(fig, name, source_names, notes, values=None):
        names = _save(fig, directory, name)
        manifest["figures"][name] = {"files": names, "sources": source_names, "notes": notes,
            "sha256": {f: _sha(directory/f) for f in names}}
        if values is not None:
            manifest["figures"][name]["display_values"] = values

    ct = read("cohort_totals.csv", ("cohort_month", "age_month", "n_acquired", "n_retained", "retained_share", "revenue_retention"))
    cash = read("cohort_cash_economics.csv", ("cohort_month", "age_month"))
    _validate_unique(ct, ["cohort_month", "age_month"], "cohort_totals")
    _validate_unique(cash, ["cohort_month", "age_month"], "cohort_cash_economics")
    if ((ct.retained_share < 0) | (ct.retained_share > 1.000001)).any():
        raise ValueError("Retained shares must be fractions in [0,1]")
    cohorts = _selected(ct.cohort_month, 6)
    ages = list(range(12))
    rate = ct.assign(cohort_month=ct.cohort_month.astype(str)).pivot(index="cohort_month", columns="age_month", values="retained_share").reindex(index=cohorts, columns=ages)
    cash_field = _col(cash, "balance_after_acquisition", "cumulative_after_acquisition", "cash_after_acquisition", "balance_after_spend", "cumulative_contribution_after_acquisition")
    cash_display = cash.copy()
    # Per-person normalization is arithmetic on an already verified cohort row.
    n_field = _col(cash, "n_acquired", "cohort_size")
    cash_display["display_per_person"] = cash_display["balance_per_customer"] if "balance_per_customer" in cash_display else cash_display[cash_field] / cash_display[n_field]
    bal = cash_display.assign(cohort_month=cash_display.cohort_month.astype(str)).pivot(index="cohort_month", columns="age_month", values="display_per_person").reindex(index=cohorts, columns=ages)
    fig, axes = plt.subplots(2, 1, figsize=(7.1, 4.45), gridspec_kw={"hspace": .45})
    cmap = LinearSegmentedColormap.from_list("retention", ["#F0F7F6", "#087F8C"])
    diverge = LinearSegmentedColormap.from_list("cash", ["#C97543", "#FBF7EE", "#087F8C"])
    for ax, matrix, title, mode in [(axes[0], rate, "Contractual retention · % of original cohort", "rate"),
                                    (axes[1], bal, "Observed cash after acquisition · $ per acquired person", "cash")]:
        a = matrix.to_numpy(dtype=float)
        kw = {"vmin": 0, "vmax": 1, "cmap": cmap} if mode == "rate" else {"cmap": diverge, "norm": TwoSlopeNorm(vmin=min(-1., float(np.nanmin(a))), vcenter=0, vmax=max(1., float(np.nanmax(a))))}
        ax.imshow(np.ma.masked_invalid(a), aspect="auto", **kw)
        ax.set_xticks(range(12), ages); ax.set_yticks(range(len(cohorts)), [x[:7] for x in cohorts], fontsize=8)
        ax.set_title(title, loc="left", pad=10); ax.set_xlabel("Age index (0 = first paid month)")
        for r in range(a.shape[0]):
            for c in range(a.shape[1]):
                if np.isfinite(a[r,c]):
                    label = f"{a[r,c]*100:.0f}" if mode == "rate" else f"{a[r,c]:.0f}"
                    white = (mode == "rate" and a[r,c]>.62) or (mode == "cash" and a[r,c] > np.nanmax(a)*.65)
                    ax.text(c,r,label,ha="center",va="center",fontsize=7.5,color="white" if white else COLORS["ink"])
                else:
                    ax.text(c,r,"—",ha="center",va="center",fontsize=8,color="#9EAEB5")
    axes[0].set_xlabel("")
    done(fig, "cohort-triangles", ["cohort_totals.csv", "cohort_cash_economics.csv"],
         "Future ages remain blank, not zero. Cash balance is divided by the saved original cohort size.",
         {"cohorts": cohorts, "age_months": ages, "unobserved_cells": int(rate.isna().sum().sum())})

    mature = ct[ct.age_month >= 5].cohort_month.astype(str).unique()
    chosen = _selected(mature, 3)
    fig, axes = plt.subplots(1,2,figsize=(7.1,3.25),gridspec_kw={"wspace":.32})
    for co,color in zip(chosen,[COLORS["muted"],COLORS["gold"],COLORS["teal"]]):
        d=ct[ct.cohort_month.astype(str)==co].sort_values("age_month")
        for ax,field in zip(axes,["retained_share","revenue_retention"]):
            ax.plot(d.age_month,d[field],marker="o",ms=3,lw=2,color=color,label=co[:7])
    for ax,title in zip(axes,["Retained people", "Net revenue retention"]):
        ax.set_title(title,loc="left");ax.set_xlabel("Age index (0 = first paid month)");ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(axis="y",alpha=.16);ax.set_ylim(bottom=0)
    axes[0].set_ylim(0,1.05);axes[0].legend(frameon=False,fontsize=8,loc="lower left")
    done(fig,"retention-and-revenue",["cohort_totals.csv"],"Same joining cohorts and age axis; revenue is normalized to first-period cohort revenue.",{"selected_cohorts":chosen})

    cells=read("cohort_age_summary.csv",("cohort_month","age_month","channel","primary_need","n_acquired","n_retained"))
    _validate_unique(cells,["cohort_month","age_month","channel","primary_need"],"cohort_age_summary")
    comparisons=["2024-01-01","2025-01-01","2025-07-01"]
    if not set(comparisons).issubset(set(cells.cohort_month)):
        raise ValueError("The fixed teaching comparison requires January2024, January2025 and July2025 cohorts")
    fig,axes=plt.subplots(2,2,figsize=(7.1,4.75),sharex=True,sharey=True,gridspec_kw={"hspace":.42,"wspace":.20})
    for ax,(channel,need) in zip(axes.flat,[("search","save_time"),("search","build_skill"),("partner","save_time"),("partner","build_skill")]):
        for co,color in zip(comparisons,[COLORS["muted"],COLORS["gold"],COLORS["teal"]]):
            one=cells[(cells.channel==channel)&(cells.primary_need==need)&(cells.cohort_month==co)&(cells.age_month<=11)].sort_values("age_month")
            if one.empty or (one.n_acquired<=0).any():raise ValueError("Missing or empty channel-by-need comparison")
            # Normalization of the saved cohort cell; no alternate source aggregation.
            ax.plot(one.age_month,one.n_retained/one.n_acquired,color=color,lw=2,marker="o",ms=3,label=co[:7])
        ax.set_title(channel.title()+" · "+need.replace("_"," "),loc="left",fontsize=10.5)
        ax.set_ylim(0,1.05);ax.set_xlim(0,11);ax.set_xticks([0,3,6,9,11]);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.13)
    for ax in axes[1]:ax.set_xlabel("Age index (0 = first paid month)")
    for ax in axes[:,0]:ax.set_ylabel("Retained / original cell")
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc="lower center",ncol=3,frameon=False,bbox_to_anchor=(.5,-.025),fontsize=9)
    done(fig,"channel-segment-retention",["cohort_age_summary.csv"],
         "Same axes and selected joining cohorts in each channel-by-pre-acquisition-need cell. Only observed ages 0–11 are shown; the July2025 curves stop at their last observed age.",
         {"selected_cohorts":comparisons,"channels":["search","partner"],"primary_needs":["save_time","build_skill"],"max_display_age":11})

    layers=read("company_month.csv",("calendar_month","cohort_month","n_retained"))
    totals=read("company_totals.csv",("calendar_month","n_retained","contribution","acquisition_spend","net_revenue")).sort_values("calendar_month")
    _validate_unique(layers,["calendar_month","cohort_month"],"company_month")
    _validate_unique(totals,["calendar_month"],"company_totals")
    wide=layers.pivot(index="calendar_month",columns="cohort_month",values="n_retained").fillna(0).sort_index()
    expected=totals.set_index("calendar_month").reindex(wide.index).n_retained.to_numpy()
    if not np.allclose(wide.sum(axis=1).to_numpy(),expected,rtol=0,atol=1e-6):
        raise ValueError("Cohort layers do not reconcile to SQL company totals")
    fig,ax=plt.subplots(figsize=(7.1,3.25));colors=plt.get_cmap("viridis")(np.linspace(.15,.87,len(wide.columns)))
    ax.stackplot(np.arange(len(wide)),wide.to_numpy().T,colors=colors,linewidth=.2,edgecolor="white")
    ax.plot(np.arange(len(wide)),expected,color=COLORS["ink"],lw=1.3)
    _months(ax,list(wide.index));ax.set_ylabel("Retained subscribers");ax.set_xlabel("Calendar month");ax.grid(axis="y",alpha=.12)
    ax.set_title("Successive joining cohorts accumulate into the active base",loc="left",pad=13)
    ax.annotate(f"{expected[-1]:,.0f}",(len(wide)-1,expected[-1]),xytext=(-3,9),textcoords="offset points",ha="right",weight="bold")
    ax.text(.01,.97,"Each band = one first-paid cohort",transform=ax.transAxes,ha="left",va="top",fontsize=8)
    done(fig,"company-cohort-layers",["company_month.csv","company_totals.csv"],"Stacks use exact saved monthly values. No forecast and no smoothing.",{"latest_active":float(expected[-1]),"cohort_layers":len(wide.columns)})
    fig,ax=plt.subplots(figsize=(7.1,1.95));x=np.arange(len(totals))
    ax.bar(x,totals.contribution,color=COLORS["teal"],width=.74,label="Contribution before acquisition")
    ax.plot(x,totals.acquisition_spend,color=COLORS["orange"],lw=1.8,label="Tracked acquisition spend")
    _months(ax,list(totals.calendar_month));ax.yaxis.set_major_formatter(FuncFormatter(_currency));ax.legend(frameon=False,fontsize=8,ncol=2,loc="upper left");ax.grid(axis="y",alpha=.12)
    done(fig,"company-economics",["company_totals.csv"],"Calendar-period contribution and acquisition costs; neither is company profit.")

    effects=read("experiment_effects.csv")
    netcol=_col(effects,"incremental_contribution_after_media_per_eligible","incremental_contribution_after_media_per_prospect","contribution_after_media_lift_per_eligible","incremental_contribution_per_eligible_after_media")
    labels=[str(r.get("channel",r.get("experiment_id","")))+" / "+str(r.get("primary_need","")) for _,r in effects.iterrows()]
    vals=effects[netcol].to_numpy(float)
    fig,ax=plt.subplots(figsize=(7.1,2.35));y=np.arange(len(vals))
    ax.barh(y,vals,color=[COLORS["teal"] if v>=0 else COLORS["orange"] for v in vals],height=.58)
    ax.axvline(0,color=COLORS["ink"],lw=.8);ax.set_yticks(y,[x.replace("_"," ") for x in labels],fontsize=8)
    ax.set_xlabel("Incremental contribution after media per assigned eligible prospect ($)");ax.grid(axis="x",alpha=.12);ax.invert_yaxis()
    for i,v in enumerate(vals):ax.annotate(f"${v:,.2f}",(v,i),xytext=(4 if v>=0 else -4,0),textcoords="offset points",ha="left" if v>=0 else "right",va="center",fontsize=8)
    left,right=ax.get_xlim();ax.set_xlim(left-abs(left)*.25-.1,right+abs(right)*.25+.1)
    done(fig,"experiment-effects",["experiment_effects.csv"],"Point estimates over each prespecified experiment window, not lifetime effects.",{"field":netcol,"values":vals.tolist()})

    if (output/"model_summary.json").exists():
        _validate_model_outputs(output)
        model=_json(output/"model_summary.json")
        val=read("cohort_valuation.csv",("cohort_month","ltv_before_cac_mean","ltv_before_cac_p05","ltv_before_cac_p95","cac","horizon_months")).sort_values("cohort_month")
        if not (val.horizon_months==12).all():raise ValueError("Report requires the agreed 12-month valuation horizon")
        if ((val.ltv_before_cac_p05>val.ltv_before_cac_mean)|(val.ltv_before_cac_mean>val.ltv_before_cac_p95)).any():raise ValueError("LTV interval does not contain its posterior mean")
        fig,ax=plt.subplots(figsize=(7.1,2.6));x=np.arange(len(val))
        ax.fill_between(x,val.ltv_before_cac_p05,val.ltv_before_cac_p95,color=COLORS["teal"],alpha=.16,label="5th–95th percentile")
        ax.plot(x,val.ltv_before_cac_mean,color=COLORS["teal"],lw=2,label="12-month LTV before CAC")
        ax.plot(x,val.cac,color=COLORS["orange"],lw=1.8,label="Tracked acquisition cost / acquired person")
        _months(ax,list(val.cohort_month));ax.yaxis.set_major_formatter(FuncFormatter(_currency));ax.grid(axis="y",alpha=.12);ax.set_ylabel("Dollars per acquired person");ax.legend(frameon=False,fontsize=8,loc="upper left")
        done(fig,"ltv-and-cac",["cohort_valuation.csv"],"Common 12-month discounted contribution horizon; CAC is not a marginal-spend estimate.")
        fc=read("forecast_curve.csv",("cohort_month","age_month","contribution_mean","contribution_p05","contribution_p95","observed"))
        newest=str(sorted(fc.cohort_month.astype(str).unique())[-1]);d=fc[fc.cohort_month.astype(str)==newest].sort_values("age_month")
        observed=d.observed.astype(str).str.lower().isin(["true","1"])
        fig,ax=plt.subplots(figsize=(7.1,1.95));ax.fill_between(d.age_month,d.contribution_p05,d.contribution_p95,color=COLORS["teal"],alpha=.16)
        ax.plot(d.age_month,d.contribution_mean,"--",color=COLORS["teal"],lw=1.6)
        ax.plot(d.loc[observed,"age_month"],d.loc[observed,"contribution_mean"],"o-",color=COLORS["ink"],lw=2,ms=4,label="Observed")
        if (~observed).any():
            boundary=float(d.loc[observed,"age_month"].max()) if observed.any() else 0
            ax.axvspan(boundary+.05,float(d.age_month.max())+.1,color=COLORS["gold"],alpha=.08);ax.axvline(boundary+.05,color=COLORS["gold"],lw=.8)
        ax.set_title(f"Newest cohort: {newest[:7]} · observed history and predicted remainder",loc="left",fontsize=10);ax.set_xlabel("Age index (0 = first paid month)");ax.set_ylabel("Cohort contribution ($)");ax.yaxis.set_major_formatter(FuncFormatter(_currency));ax.grid(axis="y",alpha=.12)
        done(fig,"forecast-detail",["forecast_curve.csv"],"Solid points are observed; dashed continuation and shaded intervals are predictions. Values retain the model output units.")
        fit=read("model_fit_checks.csv",("cohort_month","channel","primary_need","age_month","n_acquired","n_retained","fitted_retained_one_step"))
        latest_six=sorted(fit.cohort_month.astype(str).unique())
        fig,axes=plt.subplots(2,2,figsize=(7.1,4.6),sharex=True,sharey=True,gridspec_kw={"hspace":.4,"wspace":.22})
        palette=plt.get_cmap("viridis")(np.linspace(.12,.85,max(1,len(latest_six))))
        for ax,(channel,need) in zip(axes.flat,[("search","save_time"),("search","build_skill"),("partner","save_time"),("partner","build_skill")]):
            for co,color in zip(latest_six,palette):
                rows=fit[(fit.cohort_month==co)&(fit.channel==channel)&(fit.primary_need==need)&(fit.age_month>0)].sort_values("age_month")
                if rows.empty:continue
                if (rows.n_acquired<=0).any():raise ValueError("Model fit diagnostic has an empty original cell")
                residual=100*(rows.n_retained-rows.fitted_retained_one_step)/rows.n_acquired
                ax.plot(rows.age_month,residual,"o-",color=color,lw=1.3,ms=4,label=co[:7])
            ax.axhline(0,color=COLORS["gray"] if "gray" in COLORS else COLORS["muted"],lw=.8)
            ax.set_title(channel.title()+" · "+need.replace("_"," "),loc="left",fontsize=10.5);ax.grid(alpha=.12)
        for ax in axes[1]:ax.set_xlabel("Observed age index")
        for ax in axes[:,0]:ax.set_ylabel("Observed − fitted share (pp)")
        fig.suptitle("In-sample check: observed minus one-step fitted retention",fontsize=11.5,fontweight="bold",y=1.035)
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc="lower center",ncol=3,frameon=False,bbox_to_anchor=(.5,-.12),fontsize=8)
        done(fig,"recent-cohort-fit-check",["model_fit_checks.csv"],"In-sample one-step fitted residuals for recent observed cohorts, conditional on the previous observed count. This is not a held-out backtest. It can flag cell-specific departures from the shared cohort trend.")
        manifest["model_summary_sha256"]=_sha(output/"model_summary.json")
    _write_json(output/"report"/"chart_manifest.json",manifest)
    return manifest


def _tex(value) -> str:
    return "".join({"\\":r"\textbackslash{}","&":r"\&","%":r"\%","$":r"\$","#":r"\#","_":r"\_","{":r"\{","}":r"\}","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}.get(c,c) for c in str(value))


def _money(value, decimals=0):
    return r"\$"+f"{float(value):,.{decimals}f}"


def _latex_table(headers,rows,widths=None):
    layout=widths or ("Y"*len(headers))
    body=[r"\par\begin{tabularx}{\linewidth}{@{}"+layout+r"@{}}\toprule", " & ".join(r"\textbf{"+_tex(x)+"}" for x in headers)+r"\\\midrule"]
    body += [" & ".join(_tex(x) for x in row)+r"\\" for row in rows]
    body += [r"\bottomrule\end{tabularx}\par"]
    return "\n".join(body)


def _context(output: Path) -> dict:
    analysis=_json(output/"analysis_summary.json");model=_json(output/"model_summary.json")
    if int(model.get("horizon_months",12))!=12:raise ValueError("Report requires a common 12-month horizon")
    totals=_table(output,"company_totals.csv").sort_values("calendar_month");last=totals.iloc[-1]
    val=_table(output,"cohort_valuation.csv").sort_values("cohort_month");v=val.iloc[-1]
    seg=_table(output,"segmentation_comparison.csv");effects=_table(output,"experiment_effects.csv");arms=_table(output,"experiment_summary.csv")
    segrows=[[str(r.scheme).replace("_"," "),f"{r.weighted_within_variance:,.1f}",f"{int(r.n_groups)}",f"{int(r.min_group_size)}"] for _,r in seg.iterrows()]
    exrows=[]
    for _,r in arms.iterrows():
        exrows.append([str(r.get("channel",r.experiment_id)).replace("_"," ")+" / "+str(r.get("primary_need","")).replace("_"," "),str(r.arm),f"{int(r.n_assigned):,}",f"{int(r.n_buyers):,}",f"${float(r.contribution):,.2f}",f"${float(r.media_spend):,.2f}"])
    b=model.get("backtest",{});back=f"Withheld cells: {int(b.get('n_cells',0)):,}. Retained-count mean absolute error: {float(b.get('retention_mae',0)):.2f}. Revenue weighted absolute percentage error: {float(b.get('revenue_wape',0)):.1%}."
    vb=model.get("valuation_backtest",{})
    if vb:
        back+=f" A separate training-only forecast checks complete 12-month values: LTV mean absolute error ${float(vb['ltv_mae']):.2f} versus ${float(vb['baseline_ltv_mae']):.2f} for its baseline."
    back+=" These tests evaluate prediction, not campaign effects."
    latest=f"For the {str(v.cohort_month)[:7]} cohort, forecast 12-month net LTV is {_money(v.net_ltv_mean,2)} per acquired person (5th--95th percentile: {_money(v.net_ltv_p05,2)} to {_money(v.net_ltv_p95,2)}). Forecast share of LTV: {float(v.forecast_share):.0%}.".replace("%",r"\%")
    ct=_table(output,"cohort_totals.csv");common=ct[ct.age_month==5].sort_values("cohort_month")
    cash=_table(output,"cohort_cash_economics.csv");caccol=_col(cash,"cac","blended_cac")
    if len(common)<2:raise ValueError("At least two observed six-month cohorts are required for progress comparison")
    a,z=common.iloc[0],common.iloc[-1]
    ca=float(cash[cash.cohort_month==a.cohort_month].iloc[0][caccol]);cz=float(cash[cash.cohort_month==z.cohort_month].iloc[0][caccol])
    rows=[["Sixth-month retained share",f"{a.retained_share:.1%}",f"{z.retained_share:.1%}","Observed at age index 5"],
          ["Tracked cost per acquired person",f"${ca:,.2f}",f"${cz:,.2f}","Defined spending / all acquired people"],
          ["Joining cohort",str(a.cohort_month)[:7],str(z.cohort_month)[:7],"Latest cohort with six observed ages"]]
    direction="higher" if z.retained_share>a.retained_share else "lower or unchanged"
    costdirection="lower" if cz<ca else "higher or unchanged"
    progress=(f"At the common sixth age month, retained share is {direction}: {a.retained_share:.1%} for {str(a.cohort_month)[:7]} versus {z.retained_share:.1%} for {str(z.cohort_month)[:7]}. Tracked acquisition cost per acquired person is {costdirection}: ${ca:,.2f} versus ${cz:,.2f}. This blended CAC includes all acquired people, including organic control buyers; paid-source CAC has a different denominator. These are descriptive comparisons, not campaign effects.")
    cells=_table(output,"cohort_age_summary.csv");improved=0;cell_count=0
    for channel in ["search","partner"]:
        for need in ["save_time","build_skill"]:
            old=cells[(cells.cohort_month=="2024-01-01")&(cells.age_month==5)&(cells.channel==channel)&(cells.primary_need==need)].iloc[0]
            new=cells[(cells.cohort_month=="2025-07-01")&(cells.age_month==5)&(cells.channel==channel)&(cells.primary_need==need)].iloc[0]
            improved+=int(new.n_retained/new.n_acquired>old.n_retained/old.n_acquired);cell_count+=1
    facet_sentence=(f"At observed age index5, July2025 retains a larger share than January2024 in {improved} of the {cell_count} channel-by-need cells. This supports investigating improvement within the groups, rather than attributing the whole aggregate change to a different mix. The curves show where that comparison holds and where later outcomes remain unobserved.")
    choices_path=output/"learner_choices.json"
    choices=_json(choices_path) if choices_path.exists() else {}
    learner_verdict=choices.get("final_verdict", "Instructor reference build: no learner judgment has been recorded.")
    learner_action=choices.get("recommended_action", "Choose the next action after reviewing the observed, forecast and experimental evidence.")
    if choices_path.exists() and (not str(learner_verdict).strip() or not str(learner_action).strip()):
        raise ValueError("Learner verdict and recommended action must both be recorded before rendering a final learner report")
    data_as_of=analysis.get("data_as_of",analysis.get("source_data_as_of",str(last.calendar_month)))
    return {"latest_active":f"{last.n_retained:,.0f}","latest_revenue":_money(last.net_revenue),"latest_contribution":_money(last.contribution),"data_as_of":_tex(data_as_of),
            "segmentation_table":_latex_table(["Grouping","Within-group variance","Groups","Smallest group"],segrows),
            "experiment_table":r"{\fontsize{8}{10}\selectfont "+_latex_table(["Test","Arm","Assigned","Buyers","Contribution","Media"],exrows,"p{.25\\linewidth}lrrrr")+"}",
            "backtest_sentence":_tex(back),"latest_valuation_sentence":latest,
            "economics_assumption":_tex(model.get("economics_assumption","Future economics follow the documented model assumptions.")),
            "facet_sentence":_tex(facet_sentence.replace("index5","index 5").replace("July2025","July 2025").replace("January2024","January 2024")),
            "decision_table":_latex_table(["Evidence","Earlier","Later","Interpretation"],rows),"progress_sentence":_tex(progress),
            "learner_verdict":_tex(learner_verdict),"learner_action":_tex(learner_action)}


def _compile_native(source: Path, engine: str | None=None) -> dict:
    """Compile portably; on this Windows host use native WSL in its Linux FS."""
    env=os.environ.copy();env.update({"SOURCE_DATE_EPOCH":str(EPOCH),"FORCE_SOURCE_DATE":"1","TZ":"UTC"})
    engine=engine or os.environ.get("COHORT_TEX_ENGINE")
    local=engine or ("tectonic" if shutil.which("tectonic") else "pdflatex" if shutil.which("pdflatex") else None)
    if os.name=="nt" and not local and shutil.which("wsl"):
        probe=subprocess.run(["wsl","--exec","sh","-c","command -v pdflatex && kpsewhich sourcesans.sty"],capture_output=True,timeout=20)
        if probe.returncode:raise RuntimeError("No native TeX engine found, and WSL lacks pdflatex/Source Sans. Install a supported TeX engine; editable .tex is preserved.")
        linux_source=subprocess.check_output(["wsl","--exec","wslpath","-a",source.parent.as_posix()],text=True).strip()
        key=hashlib.sha256(source.read_bytes()+(source.parent/"labreport.sty").read_bytes()).hexdigest()[:16]
        script=("set -eu\n"
                f"task_build=\"$HOME/.cache/customer-economics-lab/{key}\"\n"
                "mkdir -p \"$task_build\"\n"
                f"cp -a {__import__('shlex').quote(linux_source)}/. \"$task_build/\"\n"
                "cd \"$task_build\"\n"
                f"export SOURCE_DATE_EPOCH={EPOCH} FORCE_SOURCE_DATE=1 TZ=UTC\n"
                "kpsewhich sourcesans.sty >/dev/null\n"
                "pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error customer-economics-report.tex > compile-1.txt || { tail -60 compile-1.txt; exit 1; }\n"
                "pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error customer-economics-report.tex > compile-2.txt\n"
                f"cp customer-economics-report.pdf customer-economics-report.log {__import__('shlex').quote(linux_source)}/\n")
        p=subprocess.run(["wsl","--exec","bash","-s"],input=script.encode("utf-8"),capture_output=True,env=env,timeout=180)
        if p.returncode:raise RuntimeError("WSL TeX compilation failed: "+p.stdout.decode("utf-8",errors="replace")[-2500:]+p.stderr.decode("utf-8",errors="replace")[-1500:])
        used="WSL pdflatex"
    else:
        if not local:raise RuntimeError("Install a TeX engine (tectonic or pdflatex) or set COHORT_TEX_ENGINE; editable .tex is preserved.")
        args=[local,"--keep-logs","--outdir",str(source.parent),str(source)] if "tectonic" in Path(local).name else [local,"-no-shell-escape","-interaction=nonstopmode","-halt-on-error",source.name]
        for _ in range(1 if "tectonic" in Path(local).name else 2):
            p=subprocess.run(args,cwd=source.parent,env=env,capture_output=True,text=True,timeout=180)
            if p.returncode:raise RuntimeError("TeX compilation failed: "+p.stdout[-2000:]+p.stderr[-1000:])
        used=Path(local).name
    log=source.with_suffix(".log").read_text(encoding="utf-8",errors="replace") if source.with_suffix(".log").exists() else ""
    problems=[line for line in log.splitlines() if "Overfull" in line or "Undefined control" in line or "undefined references" in line]
    if problems:raise RuntimeError("TeX QA requires repair: "+"; ".join(problems))
    return {"engine":used,"source_date_epoch":EPOCH,"overfull_boxes":0,"pdf_sha256":_sha(source.with_suffix(".pdf"))}


def build_report(output_dir: Path, compile_pdf: bool=True) -> dict:
    """Produce editable LaTeX and optionally compile an eight-page report."""
    output=Path(output_dir).resolve();directory=output/"report";directory.mkdir(parents=True,exist_ok=True)
    _json(output/"model_summary.json") # No silent placeholder forecast.
    charts=build_charts(output)
    ctx=_context(output)
    env=Environment(loader=FileSystemLoader(ROOT/"templates"),undefined=StrictUndefined,
                    variable_start_string=r"\VAR{",variable_end_string="}",autoescape=False)
    source=directory/"customer-economics-report.tex"
    source.write_text(env.get_template("customer-economics-report.tex.j2").render(**ctx),encoding="utf-8",newline="\n")
    shutil.copyfile(ROOT/"templates/labreport.sty",directory/"labreport.sty")
    manifest={"version":1,"source_date_epoch":EPOCH,"report_source_sha256":_sha(source),"style_sha256":_sha(directory/"labreport.sty"),
              "chart_manifest_sha256":_sha(directory/"chart_manifest.json"),"analysis_summary_sha256":_sha(output/"analysis_summary.json"),
              "model_summary_sha256":_sha(output/"model_summary.json"),"tables":charts["sources"],"compiled":False}
    manifest["learner_choices_sha256"]=_sha(output/"learner_choices.json") if (output/"learner_choices.json").exists() else None
    if compile_pdf:
        manifest["build"]=_compile_native(source)
        from pypdf import PdfReader
        pdf=PdfReader(source.with_suffix(".pdf"))
        if len(pdf.pages)!=8:raise ValueError(f"Expected eight designed pages, got {len(pdf.pages)}; inspect pagination")
        for page in pdf.pages:
            if abs(float(page.mediabox.width)-612)>1 or abs(float(page.mediabox.height)-792)>1:raise ValueError("Report page size must be US Letter portrait")
        manifest.update({"compiled":True,"pages":len(pdf.pages),"pdf":"report/customer-economics-report.pdf"})
    _write_json(directory/"report_manifest.json",manifest)
    return manifest
