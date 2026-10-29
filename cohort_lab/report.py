"""Deterministic figures and a portrait report from verified SQL/model tables.

This module never reads raw customer CSVs. It selects and displays saved SQL/model
outputs, with explicit presentation summaries for season-matched cohort windows.
Those summaries retain their windows, weights and source hashes for audit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm, Normalize
from matplotlib.ticker import PercentFormatter, FuncFormatter
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
EPOCH = 1794787200  # 2026-11-16 00:00 UTC; no wall-clock values in artifacts.
FIXED_DATE = datetime.fromtimestamp(EPOCH, timezone.utc)
COLORS = {"ink": "#202521", "teal": "#185A46", "gold": "#8A5E0E",
          "orange": "#B57A19", "muted": "#5A625D", "rule": "#C8CECA"}


def _validate_style() -> dict:
    """Pin the actual maintained visual system, not an approximate new theme."""
    manifest = _json(ROOT / "templates/report-style-manifest.json")
    path = ROOT / manifest["upstream_package"]
    if _sha(path) != manifest["upstream_sha256"]:
        raise ValueError("Vendored report style hash mismatch; review the style version deliberately")
    if manifest.get("private_runtime_dependency") or manifest.get("upstream_package_modified"):
        raise ValueError("Report style must remain portable and preserve its pinned upstream source")
    return manifest


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


def _currency(x, _pos=None):
    return (f"${x / 1000:,.1f}k" if abs(x)<10000 else f"${x / 1000:,.0f}k") if abs(x) >= 1000 else f"${x:,.0f}"


def _validate_unique(df, keys, label):
    if df.duplicated(keys).any():
        raise ValueError(f"{label} contains repeated {keys}; plotting would hide a grain error")


def _cohort_palette(cohorts):
    """Chronology is the color meaning; no separate legend entry per cohort."""
    palette=LinearSegmentedColormap.from_list("cohort_chronology",["#D64343","#A326A8","#344ED6"])
    return palette, {co:palette(i/max(1,len(cohorts)-1)) for i,co in enumerate(cohorts)}


def _cohort_colorbar(fig, axes, cohorts, palette):
    scalar=plt.cm.ScalarMappable(norm=Normalize(0,max(1,len(cohorts)-1)),cmap=palette)
    bar=fig.colorbar(scalar,ax=list(np.ravel(axes)),orientation="horizontal",fraction=.045,pad=.14,aspect=38)
    ticks=np.unique(np.linspace(0,len(cohorts)-1,min(5,len(cohorts)),dtype=int))
    bar.set_ticks(ticks,labels=[cohorts[i][:7] for i in ticks]);bar.ax.tick_params(labelsize=8)
    bar.set_label("Acquisition cohort: older → newer",fontsize=9)


def _triangle(ax, matrix, title, mode, ages, cohorts, test_months=()):
    a=matrix.to_numpy(dtype=float)
    cmap=LinearSegmentedColormap.from_list("retention",["#F2F5F2",COLORS["teal"]])
    diverge=LinearSegmentedColormap.from_list("cash",[COLORS["orange"],"#F2F5F2",COLORS["teal"]])
    kw={"vmin":0,"vmax":1,"cmap":cmap} if mode=="rate" else {
        "cmap":diverge,"norm":TwoSlopeNorm(vmin=min(-1.,float(np.nanmin(a))),vcenter=0,vmax=max(1.,float(np.nanmax(a))))}
    ax.imshow(np.ma.masked_invalid(a),aspect="auto",**kw)
    ax.set_xticks(range(len(ages)),ages,fontsize=7)
    ax.set_yticks(range(len(cohorts)),[x[:7]+(" *" if x[:7] in test_months else "") for x in cohorts],fontsize=8)
    ax.set_title(title,loc="left",pad=12);ax.set_xlabel("Age index (0 = first paid month)")
    ax.set_ylabel("Acquisition cohort")
    for r in range(a.shape[0]):
        for c in range(a.shape[1]):
            if np.isfinite(a[r,c]):
                label=f"{a[r,c]*100:.0f}" if mode=="rate" else f"{a[r,c]:.0f}"
                white=(mode=="rate" and a[r,c]>.62) or (mode=="cash" and a[r,c]>np.nanmax(a)*.65)
                ax.text(c,r,label,ha="center",va="center",fontsize=6.8,color="white" if white else COLORS["ink"])


def _validate_model_outputs(output: Path) -> dict:
    manifest=_json(output/"model_manifest.json")
    expected={"model_summary.json","posterior_draws.json","tables/cohort_valuation.csv",
              "tables/cohort_valuation_by_segment.csv","tables/forecast_curve.csv","tables/backtest.csv","tables/valuation_backtest.csv","tables/model_fit_checks.csv",
              "tables/parameter_summary.csv","tables/heterogeneity_by_cell.csv","tables/calendar_fit_checks.csv"}
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
                "numerical_policy": "Select/pivot saved SQL/model outputs; explicit season-matched presentation comparisons retain windows, weights and source hashes."}
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
    cohorts = sorted(ct.cohort_month.astype(str).unique())
    ages = list(range(int(ct.age_month.max())+1))
    rate = ct.assign(cohort_month=ct.cohort_month.astype(str)).pivot(index="cohort_month", columns="age_month", values="retained_share").reindex(index=cohorts, columns=ages)
    cash_field = _col(cash, "balance_after_acquisition", "cumulative_after_acquisition", "cash_after_acquisition", "balance_after_spend", "cumulative_contribution_after_acquisition")
    cash_display = cash.copy()
    # Per-person normalization is arithmetic on an already verified cohort row.
    n_field = _col(cash, "n_acquired", "cohort_size")
    cash_display["display_per_person"] = cash_display["balance_per_customer"] if "balance_per_customer" in cash_display else cash_display[cash_field] / cash_display[n_field]
    bal = cash_display.assign(cohort_month=cash_display.cohort_month.astype(str)).pivot(index="cohort_month", columns="age_month", values="display_per_person").reindex(index=cohorts, columns=ages)
    ex_tests=read("cohort_economics_ex_tests.csv")
    test_months=sorted(ex_tests.loc[ex_tests.excluded_test_buyers>0,"cohort_month"].str[:7].unique())
    triangle_values={"cohorts":cohorts,"age_months":ages,"unobserved_cells":int(rate.isna().sum().sum()),"test_months":test_months}
    fig,axes=plt.subplots(2,1,figsize=(10.5,13),gridspec_kw={"hspace":.23})
    for ax,matrix,title,mode in [(axes[0],rate,"Contractual retention · % of original cohort","rate"),
                                (axes[1],bal,"Observed cash after acquisition · $ per acquired person","cash")]:
        _triangle(ax,matrix,title,mode,ages,cohorts,test_months)
    done(fig, "cohort-triangles", ["cohort_totals.csv", "cohort_cash_economics.csv", "cohort_economics_ex_tests.csv"],
         "Every acquisition cohort and every observed age; future ages remain blank, not zero. Cash uses original cohort size.",triangle_values)
    for name,matrix,title,mode in [
        ("cohort-retention-triangle",rate,"Contractual retention · % of original cohort","rate"),
        ("cohort-cash-triangle",bal,"Observed cash after acquisition · $ per acquired person","cash")]:
        fig,ax=plt.subplots(figsize=(7.1,6.3))
        _triangle(ax,matrix,title,mode,ages,cohorts,test_months)
        done(fig,name,["cohort_totals.csv","cohort_cash_economics.csv","cohort_economics_ex_tests.csv"],
             "All 24 joining cohorts, full observed age range; the upper-right missing region is unobserved rather than zero.",triangle_values)

    palette,colors=_cohort_palette(cohorts)
    fig, axes = plt.subplots(1,2,figsize=(7.1,4.4),gridspec_kw={"wspace":.32})
    for co in cohorts:
        d=ct[ct.cohort_month.astype(str)==co].sort_values("age_month")
        for ax,field in zip(axes,["retained_share","revenue_retention"]):
            ax.plot(d.age_month,d[field],marker="o",markevery=[len(d)-1],ms=2.5,lw=1.1,color=colors[co],alpha=.9)
    for ax,title in zip(axes,["Retained people", "Net revenue retention"]):
        ax.set_title(title,loc="left");ax.set_xlabel("Age index (0 = first paid month)");ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(axis="y",alpha=.16);ax.set_ylim(bottom=0)
        ax.set_xlim(0,max(ages));ax.set_xticks([0,6,12,18,23])
    axes[0].set_ylim(0,1.05)
    _cohort_colorbar(fig,axes,cohorts,palette)
    done(fig,"retention-and-revenue",["cohort_totals.csv"],"All 24 joining cohorts; shared chronological color scale and observed-age endpoints. Revenue is normalized to each cohort's first-period revenue.",{"cohorts":cohorts,"max_display_age":max(ages),"chronological_colors":{co:matplotlib.colors.to_hex(colors[co]) for co in cohorts}})

    cells=read("cohort_age_summary.csv",("cohort_month","age_month","channel","primary_need","n_acquired","n_retained"))
    _validate_unique(cells,["cohort_month","age_month","channel","primary_need"],"cohort_age_summary")
    comparisons=cohorts
    fig,axes=plt.subplots(2,2,figsize=(7.1,5.65),sharex=True,sharey=True,gridspec_kw={"hspace":.34,"wspace":.20})
    for ax,(channel,need) in zip(axes.flat,[("search","save_time"),("search","build_skill"),("partner","save_time"),("partner","build_skill")]):
        for co in comparisons:
            one=cells[(cells.channel==channel)&(cells.primary_need==need)&(cells.cohort_month==co)].sort_values("age_month")
            if one.empty or (one.n_acquired<=0).any():raise ValueError("Missing or empty channel-by-need comparison")
            # Normalization of the saved cohort cell; no alternate source aggregation.
            ax.plot(one.age_month,one.n_retained/one.n_acquired,color=colors[co],lw=1.1,marker="o",markevery=[len(one)-1],ms=2.5,alpha=.9)
        ax.set_title(channel.title()+" · "+need.replace("_"," "),loc="left",fontsize=10.5)
        ax.set_ylim(0,1.05);ax.set_xlim(0,max(ages));ax.set_xticks([0,6,12,18,23]);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.13)
    for ax in axes[1]:ax.set_xlabel("Age index (0 = first paid month)")
    for ax in axes[:,0]:ax.set_ylabel("Retained / original cell")
    _cohort_colorbar(fig,axes,cohorts,palette)
    done(fig,"channel-segment-retention",["cohort_age_summary.csv"],
         "Same axes and all 24 joining cohorts in each channel-by-pre-acquisition-need cell. Chronological color replaces a long legend; every curve stops at its last observed age.",
         {"cohorts":comparisons,"channels":["search","partner"],"primary_needs":["save_time","build_skill"],"max_display_age":max(ages)})

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
    for field in ("followup_days", netcol+"_ci_lower", netcol+"_ci_upper"):
        if field not in effects: raise ValueError(f"Experiment uncertainty output is missing {field}")
    labels=[str(r.get("channel",r.get("experiment_id","")))+" / "+str(r.get("primary_need",""))+f" ({int(r.followup_days)} days)" for _,r in effects.iterrows()]
    vals=effects[netcol].to_numpy(float)
    fig,ax=plt.subplots(figsize=(7.1,2.35));y=np.arange(len(vals))
    errors=np.vstack([vals-effects[netcol+"_ci_lower"].to_numpy(float),effects[netcol+"_ci_upper"].to_numpy(float)-vals])
    ax.barh(y,vals,color=COLORS["teal"],height=.45,alpha=.65)
    ax.errorbar(vals,y,xerr=errors,fmt="o",color=COLORS["ink"],capsize=4,ms=4,lw=1.3)
    ax.axvline(0,color=COLORS["ink"],lw=.8);ax.set_yticks(y,[x.replace("_"," ") for x in labels],fontsize=8)
    ax.set_xlabel("Incremental contribution after media per assigned eligible prospect ($)");ax.grid(axis="x",alpha=.12);ax.invert_yaxis()
    for i,v in enumerate(vals):ax.annotate(_dollars(v,2),(v,i),xytext=(0,-22),textcoords="offset points",ha="center",va="center",fontsize=8)
    left,right=ax.get_xlim();ax.set_xlim(left-abs(left)*.25-.1,right+abs(right)*.25+.1)
    done(fig,"experiment-effects",["experiment_effects.csv"],"Point estimates and approximate 95% intervals from all-assigned arm variances over the stated windows; fixed media cost shifts the mean, not its sampling variance. Not lifetime effects.",{"field":netcol,"values":vals.tolist(),"ci_lower":effects[netcol+"_ci_lower"].tolist(),"ci_upper":effects[netcol+"_ci_upper"].tolist(),"followup_days":effects.followup_days.tolist()})

    if (output/"model_summary.json").exists():
        _validate_model_outputs(output)
        model=_json(output/"model_summary.json")
        val=read("cohort_valuation.csv",("cohort_month","ltv_before_cac_mean","ltv_before_cac_p05","ltv_before_cac_p95","cac","horizon_months")).sort_values("cohort_month")
        if not (val.horizon_months==12).all():raise ValueError("Report requires the agreed 12-month valuation horizon")
        if ((val.ltv_before_cac_p05>val.ltv_before_cac_mean)|(val.ltv_before_cac_mean>val.ltv_before_cac_p95)).any():raise ValueError("LTV interval does not contain its posterior mean")
        fig,(ax,share)=plt.subplots(2,1,figsize=(7.1,3.0),sharex=True,gridspec_kw={"height_ratios":[4,1],"hspace":.16});x=np.arange(len(val))
        ax.fill_between(x,val.ltv_before_cac_p05,val.ltv_before_cac_p95,color=COLORS["teal"],alpha=.16,label="5th–95th percentile")
        ax.plot(x,val.ltv_before_cac_mean,color=COLORS["teal"],lw=2,label="12-month LTV before CAC")
        ax.plot(x,val.cac,color=COLORS["orange"],lw=1.8,label="Blended CAC")
        ax.yaxis.set_major_formatter(FuncFormatter(_currency));ax.grid(axis="y",alpha=.12);ax.set_ylabel("Dollars / customer");ax.set_ylim(bottom=0)
        ax.legend(frameon=False,fontsize=8,ncol=3,loc="lower left",bbox_to_anchor=(0,1.02),borderaxespad=0)
        share.bar(x,val.forecast_share.clip(0,1),color=COLORS["muted"],width=.75)
        share.set_ylim(0,1);share.set_yticks([0,1],["0%","100%"],fontsize=7);share.set_ylabel("Forecast\nshare",fontsize=8)
        experiment_months=sorted(pd.to_datetime(effects.assigned_at).dt.strftime("%Y-%m").unique())
        for month in experiment_months:
            matches=np.where(val.cohort_month.astype(str).str[:7].to_numpy()==month)[0]
            for position in matches:
                ax.axvline(position,color=COLORS["gold"],ls=":",lw=1)
                ax.annotate(month+" test",(position,.04),xycoords=("data","axes fraction"),rotation=90,fontsize=7,ha="right",va="bottom",color=COLORS["gold"])
        _months(share,list(val.cohort_month))
        done(fig,"ltv-and-cac",["cohort_valuation.csv","experiment_effects.csv"],"Common 12-month discounted contribution horizon; bar strip shows forecast share. Dotted months contain experiments and organic control buyers in the blended CAC denominator. Blended CAC divides tracked spend by all acquired customers, not marginal customers.",{"forecast_share":val.forecast_share.tolist(),"experiment_months":experiment_months,"y_axis_min":0})
        fc=read("forecast_curve.csv",("cohort_month","age_month","contribution_mean","contribution_p05","contribution_p95","observed","n_retained_mean","n_retained_p05","n_retained_p95"))
        is_observed=fc.observed.astype(str).str.lower().isin(["true","1"])
        observed_ages=fc.assign(observed_count=is_observed.astype(int)).groupby("cohort_month").observed_count.sum()
        complete=observed_ages[observed_ages>=12].index.astype(str)
        if len(complete)==0:raise ValueError("A fully observed cohort is required for the retention forecast comparison")
        middle=str((observed_ages[observed_ages<12]-4).abs().sort_values(kind="stable").index[0])
        retention_cohorts=[str(sorted(complete)[-1]),middle,str(sorted(fc.cohort_month.astype(str).unique())[-1])]
        fig,axes=plt.subplots(1,3,figsize=(7.1,3.15),sharex=True,sharey=True,gridspec_kw={"wspace":.18})
        for ax,cohort in zip(axes,retention_cohorts):
            series=fc[fc.cohort_month.astype(str)==cohort].sort_values("age_month")
            n0=float(val[val.cohort_month.astype(str)==cohort].n_acquired.iloc[0])
            observed=series.observed.astype(str).str.lower().isin(["true","1"])
            ax.plot(series.loc[observed,"age_month"],series.loc[observed,"n_retained_mean"]/n0,"o-",color=COLORS["ink"],ms=3,lw=1.8)
            if (~observed).any():
                start=max(0,int(observed.sum())-1);tail=series.iloc[start:]
                ax.plot(tail.age_month,tail.n_retained_mean/n0,"--",color=COLORS["teal"],lw=1.8)
                ax.fill_between(tail.age_month,tail.n_retained_p05/n0,tail.n_retained_p95/n0,color=COLORS["teal"],alpha=.17)
                ax.axvline(float(tail.age_month.iloc[0]),color=COLORS["gold"],lw=.8,alpha=.7)
            renewals=max(0,int(observed.sum())-1)
            ax.set_title(f"{cohort[:7]}\nObserved renewals: {renewals}",loc="left",fontsize=9.5)
            ax.set_xlim(0,11);ax.set_ylim(0,1.05);ax.set_xticks([0,3,6,9,11]);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.13)
            ax.set_xlabel("Age (0 = acquisition)",fontsize=8)
        axes[0].set_ylabel("Retained / original cohort")
        done(fig,"retention-forecast",["forecast_curve.csv","cohort_valuation.csv"],
             "Solid observed retention; dashed forecast continuation; 5th–95th posterior parameter bands. Newest cohort has no observed renewal decision.",{"cohorts":retention_cohorts,"observed_renewal_ages":[int(observed_ages[x])-1 for x in retention_cohorts]})
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
        latest_six=sorted(fit.loc[fit.age_month>0,"cohort_month"].astype(str).unique())
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
        done(fig,"recent-cohort-fit-check",["model_fit_checks.csv"],"In-sample one-step fitted residuals for recent cohorts with at least one observed renewal, conditional on the previous observed count. This is not a held-out backtest.",{"cohorts":latest_six,"n_cohorts":len(latest_six)})
        manifest["model_summary_sha256"]=_sha(output/"model_summary.json")
    _write_json(output/"report"/"chart_manifest.json",manifest)
    return manifest


def _tex(value) -> str:
    return "".join({"\\":r"\textbackslash{}","&":r"\&","%":r"\%","$":r"\$","#":r"\#","_":r"\_","{":r"\{","}":r"\}","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}.get(c,c) for c in str(value))


def _money(value, decimals=0):
    return _tex(_dollars(value,decimals))


def _dollars(value,decimals=0):
    return ("-" if float(value)<0 else "")+"$"+f"{abs(float(value)):,.{decimals}f}"


def _latex_table(headers,rows,widths=None):
    layout=widths or ("Y"*len(headers))
    body=[r"\par\begin{tabularx}{\linewidth}{@{}"+layout+r"@{}}\toprule", " & ".join(r"\textbf{"+_tex(x)+"}" for x in headers)+r"\\\midrule"]
    body += [" & ".join(_tex(x) for x in row)+r"\\" for row in rows]
    body += [r"\bottomrule\end{tabularx}\par"]
    return "\n".join(body)


def _matched_year_evidence(totals: pd.DataFrame, cash: pd.DataFrame,
                           cells: pd.DataFrame, age: int = 5) -> dict:
    """Compare the same joining months one year apart, with explicit denominators.

    All-customer economics use original cohort-size weights. The paid-only renewal
    comparison separately fixes channel-by-need weights to the earlier window.
    Neither comparison identifies the causal effect of a channel or a stated need.
    """
    observed=totals[totals.age_month==age].copy()
    observed["year"]=pd.to_datetime(observed.cohort_month).dt.year
    observed["month"]=pd.to_datetime(observed.cohort_month).dt.month
    years=sorted(observed.year.unique())
    if len(years)<2:raise ValueError("Progress comparison needs two years of observed cohorts")
    years=[int(years[0]),int(years[0]+1)]
    blocks=[];paid=[];cell_keys=[(c,n) for c in ["search","partner"] for n in ["save_time","build_skill"]]
    for year in years:
        window=observed[(observed.year==year)&observed.month.between(1,6)].sort_values("cohort_month")
        if window.month.tolist()!=list(range(1,7)):
            raise ValueError(f"Progress comparison requires January--June {year} at age {age}")
        costs=cash[(cash.age_month==age)&cash.cohort_month.isin(window.cohort_month)].sort_values("cohort_month")
        if costs.cohort_month.tolist()!=window.cohort_month.tolist():raise ValueError("Matched cohort economics are missing")
        np.testing.assert_array_equal(costs.n_acquired.to_numpy(),window.n_acquired.to_numpy())
        denominator=float(window.n_acquired.sum())
        weight=window.n_acquired.to_numpy()/denominator
        block={"year":year,"cohorts":window.cohort_month.tolist(),"n_cohorts":6,
               "n_acquired":int(denominator),"age_month":age,
               "retained_share":float(window.n_retained.sum()/denominator),
               "cohort_weights":{str(c):float(w) for c,w in zip(window.cohort_month,weight)}}
        for target,source in [("blended_cac",_col(costs,"cac","blended_cac")),
                              ("contribution_per_customer","cumulative_contribution_per_customer"),
                              ("cash_after_cac_per_customer","balance_per_customer")]:
            block[target]=float(np.dot(costs[source].to_numpy(),weight))
        if not np.isclose(block["contribution_per_customer"]-block["blended_cac"],block["cash_after_cac_per_customer"],atol=1e-8):
            raise ValueError("Weighted contribution less CAC must reconcile to weighted cash")
        blocks.append(block)
        group=cells[(cells.age_month==age)&cells.cohort_month.isin(window.cohort_month)]
        rows=[]
        for channel,need in cell_keys:
            cell=group[(group.channel==channel)&(group.primary_need==need)]
            if set(cell.cohort_month)!=set(window.cohort_month):raise ValueError("Paid channel-by-need cell is missing a comparison cohort")
            acquired=float(cell.n_acquired.sum());retained=float(cell.n_retained.sum())
            rows.append({"channel":channel,"primary_need":need,"n_acquired":int(acquired),
                         "n_retained":int(retained),"retained_share":retained/acquired})
        paid.append(rows)
    base_total=sum(x["n_acquired"] for x in paid[0])
    weights=[x["n_acquired"]/base_total for x in paid[0]]
    for block,rows in zip(blocks,paid):
        block["paid_raw_retention"]=sum(x["n_retained"] for x in rows)/sum(x["n_acquired"] for x in rows)
        block["paid_fixed_mix_retention"]=sum(w*x["retained_share"] for w,x in zip(weights,rows))
        block["paid_cells"]=rows
    return {"age_month":age,"observed_receipts":age+1,"joining_months":[1,2,3,4,5,6],
            "weighting":"Original acquired customer counts within each six-cohort window",
            "standardization":"Paid channel-by-stated-need composition fixed to the earlier window; organic customers excluded",
            "earlier":blocks[0],"later":blocks[1],
            "fixed_paid_mix":[{"channel":c,"primary_need":n,"weight":w} for (c,n),w in zip(cell_keys,weights)],
            "improved_cells":sum(b["retained_share"]>a["retained_share"] for a,b in zip(paid[0],paid[1])),
            "total_cells":len(cell_keys)}


def _context(output: Path) -> dict:
    analysis=_json(output/"analysis_summary.json");model=_json(output/"model_summary.json")
    if int(model.get("horizon_months",12))!=12:raise ValueError("Report requires a common 12-month horizon")
    totals=_table(output,"company_totals.csv").sort_values("calendar_month");last=totals.iloc[-1]
    val=_table(output,"cohort_valuation.csv").sort_values("cohort_month");v=val.iloc[-1]
    seg=_table(output,"segmentation_comparison.csv");effects=_table(output,"experiment_effects.csv");arms=_table(output,"experiment_summary.csv")
    segrows=[[str(r.scheme).replace("_"," "),f"{r.weighted_within_variance:,.1f}",f"{int(r.n_groups)}",f"{int(r.min_group_size):,}"] for _,r in seg.iterrows()]
    exrows=[]
    for _,r in arms.iterrows():
        exrows.append([str(r.get("channel",r.experiment_id)).replace("_"," ")+" / "+str(r.get("primary_need","")).replace("_"," "),str(r.arm),f"{int(r.n_assigned):,}",f"{int(r.n_buyers):,}",f"${float(r.contribution):,.2f}",f"${float(r.media_spend):,.2f}"])
    b=model.get("backtest",{});back=f"Withheld cells: {int(b.get('n_cells',0)):,}. Retained-count mean absolute error: {float(b.get('retention_mae',0)):.2f}. Revenue weighted absolute percentage error: {float(b.get('revenue_wape',0)):.1%}."
    vb=model.get("valuation_backtest",{})
    if vb:
        back+=f" A separate training-only forecast checks complete 12-month values: LTV mean absolute error ${float(vb['ltv_mae']):.2f} versus ${float(vb['baseline_ltv_mae']):.2f} for its baseline."
    back+=" These tests evaluate prediction, not campaign effects."
    first_value=val.iloc[0]
    latest=(f"Across the cohort sequence, common-horizon contribution LTV combines observed receipts with a growing predicted remainder; the strip makes that dependence visible. Net of blended CAC, the endpoint comparison is {_money(first_value.net_ltv_mean,2)} for {str(first_value.cohort_month)[:7]} versus {_money(v.net_ltv_mean,2)} for {str(v.cohort_month)[:7]}. This is not a monotonic improvement claim. The newest value is {float(v.forecast_share):.0%} forecast, with a 5th--95th parameter range of {_money(v.net_ltv_p05,2)} to {_money(v.net_ltv_p95,2)}.").replace("%",r"\%")
    ct=_table(output,"cohort_totals.csv")
    cash=_table(output,"cohort_cash_economics.csv")
    cells=_table(output,"cohort_age_summary.csv")
    window=_matched_year_evidence(ct,cash,cells)
    a,z=window["earlier"],window["later"]
    adjusted=_table(output,"cohort_economics_ex_tests.csv")
    ex_test=[]
    for block in [a,z]:
        one=adjusted[(adjusted.age_month==5)&adjusted.cohort_month.isin(block["cohorts"])].sort_values("cohort_month")
        if one.cohort_month.tolist()!=block["cohorts"]:raise ValueError("Ex-test comparison must keep the same six joining cohorts")
        n=int(one.n_acquired.sum())
        ex_test.append({"n_acquired":n,"retained_share":float(one.n_retained.sum()/n),"excluded_test_buyers":int(one.excluded_test_buyers.sum()),
                        "excluded_test_spend":float(one.excluded_test_spend.sum()),
                        "blended_cac":float(one.acquisition_spend.sum()/n),
                        "contribution_per_customer":float(one.cumulative_contribution.sum()/n),
                        "cash_after_cac_per_customer":float(one.balance_after_acquisition.sum()/n)})
    window["experiment_excluded"]={"earlier":ex_test[0],"later":ex_test[1],
        "scope":"Same joining windows and age; exclude both experimental arms' buyers and all their observed contribution, and test-window campaign spending. Descriptive sensitivity, not causal adjustment."}
    ca,cz=a["blended_cac"],z["blended_cac"]
    has_economics=True
    rows=[["Sixth-month retained share",f"{a['retained_share']:.1%}",f"{z['retained_share']:.1%}","Observed at age index 5"],
          ["Blended CAC",f"${ca:,.2f}",f"${cz:,.2f}","Tracked spending / all acquired people"],
          ["Six-month contribution / customer",f"${a['contribution_per_customer']:,.2f}",f"${z['contribution_per_customer']:,.2f}","After recorded variable costs"],
          ["Six-month cash after acquisition",f"${a['cash_after_cac_per_customer']:,.2f}",f"${z['cash_after_cac_per_customer']:,.2f}","Contribution less blended CAC"],
          ["Ex-test CAC / cash",f"${ex_test[0]['blended_cac']:,.2f} / ${ex_test[0]['cash_after_cac_per_customer']:,.2f}",f"${ex_test[1]['blended_cac']:,.2f} / ${ex_test[1]['cash_after_cac_per_customer']:,.2f}","Same joining windows; both test arms excluded"]]
    test_disclosure=(f"Reported economics include experimental buyers. The later window contains {ex_test[1]['excluded_test_buyers']} test-assigned buyers and ${ex_test[1]['excluded_test_spend']:,.0f} of test spending; excluding both arms and their contribution gives the sensitivity row. The earlier window excludes {ex_test[0]['excluded_test_buyers']} buyers. Improvement remains; its magnitude is smaller.")
    progress=(f"At age 5, six-month cash after acquisition changes from ${a['cash_after_cac_per_customer']:,.2f} to ${z['cash_after_cac_per_customer']:,.2f} per original customer. The comparison uses January--June {a['year']} and the same joining months of {z['year']}, weighted by acquired cohort size. Table 1 reports the matching retention, contribution and blended-CAC evidence. These are descriptive comparisons, not campaign effects.")
    renewal_improving=(z["retained_share"]>a["retained_share"] and window["improved_cells"]==window["total_cells"])
    facet_sentence=(f"Age-5 paid retention is {a['paid_raw_retention']:.1%} for January--June {a['year']} versus {z['paid_raw_retention']:.1%} for the same {z['year']} joining months. Fixing the earlier channel-by-need mix gives {a['paid_fixed_mix_retention']:.1%} versus {z['paid_fixed_mix_retention']:.1%}; {window['improved_cells']} of {window['total_cells']} paid groups improve. This removes changes in these groups' shares, not all customer differences or confounding. All 24 trajectories are shown above.")
    choices_path=output/"learner_choices.json"
    choices=_json(choices_path) if choices_path.exists() else {}
    improving = (cz < ca and z["contribution_per_customer"] > a["contribution_per_customer"]
                 and z["cash_after_cac_per_customer"] > a["cash_after_cac_per_customer"])
    renewal_claim=("Later cohorts also retain more customers at common ages, including within each channel--need group." if renewal_improving else "Renewal is not clearly improving across successive cohorts.")
    executive_verdict = (("The company is moving toward stronger customer economics: lower blended CAC, higher contribution and more cash recovered over six months. "+renewal_claim+" Short campaign tests do not yet establish the return from a larger acquisition budget.")
                         if improving else "The cohort evidence does not establish broad economic improvement. Evaluate renewal, acquisition cost, contribution and cash recovery together, then resolve the weak channel--need cells before expanding the budget.")
    default_action = ("Continue measured acquisition while requiring a stated cash-payback limit and randomized evidence before increasing campaign spending. Review each new joining cohort at common ages within its channel and stated-need group."
                      if improving else "Keep acquisition expansion conditional on better cohort economics. Assign Marketing, Product and Analytics a review of the channel and customer-need cells where retention or acquisition cost has deteriorated, then test the proposed correction.")
    learner_verdict=choices.get("final_verdict", executive_verdict)
    learner_action=choices.get("recommended_action", default_action)
    if choices_path.exists() and (not str(learner_verdict).strip() or not str(learner_action).strip()):
        raise ValueError("Learner verdict and recommended action must both be recorded before rendering a final learner report")
    data_as_of=analysis.get("data_as_of",analysis.get("source_data_as_of",str(last.calendar_month)))
    cohorts=sorted(ct.cohort_month.astype(str).unique())
    scope_line=f"{len(cohorts)} monthly acquisition cohorts, {cohorts[0][:7]} through {cohorts[-1][:7]}; data cutoff {str(data_as_of)[:10]}"
    best_seg=seg.sort_values("weighted_within_variance").iloc[0]
    other_seg=seg[seg.scheme!=best_seg.scheme]
    relative_gain=(1-float(best_seg.weighted_within_variance)/float(other_seg.weighted_within_variance.min())) if len(other_seg) else 0.
    gain_qualifier="modest" if relative_gain<.10 else "material"
    segmentation_sentence=(f"The {str(best_seg.scheme).replace('_',' ')} grouping has the lowest within-group variance in six-month contribution ({float(best_seg.weighted_within_variance):,.1f} dollars squared), a {relative_gain:.1%} reduction versus the next-best scheme. This {gain_qualifier} separation leaves residual heterogeneity: a need label does not make customers economically identical.")
    experiment_sentence=""
    if len(effects):
        net_col=_col(effects,"incremental_contribution_after_media_per_eligible","incremental_contribution_after_media_per_prospect","contribution_after_media_lift_per_eligible","incremental_contribution_per_eligible_after_media")
        terms=[f"{str(r.channel).replace('_',' ')} / {str(r.primary_need).replace('_',' ')}: {_dollars(r[net_col],2)} over {int(r.followup_days)} days (95% interval {_dollars(r[net_col+'_ci_lower'],2)} to {_dollars(r[net_col+'_ci_upper'],2)})" for _,r in effects.iterrows()]
        zero_count=int(((effects[net_col+"_ci_lower"]<=0)&(effects[net_col+"_ci_upper"]>=0)).sum())
        experiment_sentence="Incremental contribution after media per assigned prospect: "+"; ".join(terms)+f". {zero_count} of {len(effects)} intervals include zero; neither the sign nor the ranking of point estimates warrants a scale-or-stop decision."
        if has_economics and "recommended_action" not in choices:
            monitoring_cash=ex_test[1]["cash_after_cac_per_customer"]
            product_action=("Product should protect the experience supporting stronger renewal and monitor whether the newest cohorts sustain it as acquisition scales." if renewal_improving else "Product should investigate the weaker renewal trajectories before assuming conversion gains imply durable value.")
            learner_action=(f"Marketing and Analytics should preserve controls and extend both campaign follow-ups through the cash-recovery horizon. Finance should monitor six-month cash against the ex-test matched window's ${monitoring_cash:,.2f} per customer, not use it as an automatic causal gate. "+product_action)
    company_sentence=""
    if "acquisition_spend" in totals:
        balance=float(last.contribution)-float(last.acquisition_spend)
        company_sentence=(f"In {str(last.calendar_month)[:7]}, recorded contribution was ${float(last.contribution):,.0f} and acquisition spending was ${float(last.acquisition_spend):,.0f}, leaving ${balance:,.0f} before fixed costs, financing and taxes. This period result should be read alongside the age-aligned cohort comparison, rather than used as a substitute for it.")
    action_rows=[
        ["Marketing + Finance","Defer expansion or rejection based only on the short-window profit estimates; monitor recovery against mature-cohort experience.","Age-aligned value and cash, alongside uncertainty in incremental returns."],
        ["Product + Operations","Monitor the experience behind each segment's renewal trajectory; investigate departures as acquisition scales.","Renewal events, product actions and expressed customer evaluations."],
        ["Marketing + Analytics","Preserve both controls and extend follow-up through the acquisition cash-recovery horizon.","Contribution after media per assigned prospect, including nonbuyers, with uncertainty."],
        ["Data + Analytics","Refresh the evidence from the source exports and review forecast misses before releasing the decision report.","SQL reconciliation, model holdouts, parameter output and file hashes."],
    ]
    return {"latest_active":f"{last.n_retained:,.0f}","latest_revenue":_money(last.net_revenue),"latest_contribution":_money(last.contribution),"data_as_of":_tex(data_as_of),
            "segmentation_table":_latex_table(["Grouping","Variance (dollars squared)","Groups","Smallest group (people)"],segrows),
            "experiment_table":r"{\fontsize{8}{10}\selectfont "+_latex_table(["Test","Arm","Assigned","Buyers","Contribution","Media"],exrows,"p{.25\\linewidth}lrrrr")+"}",
            "backtest_sentence":_tex(back),"latest_valuation_sentence":latest,
            "economics_assumption":_tex(model.get("economics_assumption","Future economics follow the documented model assumptions.")),
            "facet_sentence":_tex(facet_sentence),
            "decision_table":_latex_table(["Evidence","Earlier","Later","Interpretation"],rows),"progress_sentence":_tex(progress).replace("Table 1",r"Table~\ref{tab:executive-evidence}"),
            "learner_verdict":_tex(learner_verdict),"learner_action":_tex(learner_action),
            "scope_line":_tex(scope_line),"executive_verdict":_tex(executive_verdict),
            "evidence_base":_tex(f"Eight source exports; {len(cohorts)} monthly acquisition cohorts; cutoff {str(data_as_of)[:10]}. Pending renewal outcomes are excluded from observed renewal trials. All randomized prospects remain in experimental denominators, including nonbuyers."),
            "matched_cohorts":_tex(f"January--June {a['year']} versus January--June {z['year']}; age 5, six observed receipts; acquired-customer weights"),
            "acquisition_kpi":_money(ca,0)+r" $\rightarrow$ "+_money(cz,0),
            "value_kpi":_money(a["contribution_per_customer"],0)+r" $\rightarrow$ "+_money(z["contribution_per_customer"],0),
            "cash_kpi":_money(a["cash_after_cac_per_customer"],0)+r" $\rightarrow$ "+_money(z["cash_after_cac_per_customer"],0),
            "renewal_window_evidence":window,
            "test_comparability_disclosure":_tex(test_disclosure),
            "executive_metrics_values":{"windows":[a,z],"age_month":5},
            "executive_experiment_sentence":_tex(experiment_sentence),"company_sentence":_tex(company_sentence),
            "segmentation_sentence":_tex(segmentation_sentence),
            "action_table":_latex_table(["Accountable team","Next action","Decision evidence"],action_rows,"p{.18\\linewidth}YY")}


def _field_tex(name: str) -> str:
    """Preserve literal field tokens for reliable PDF copying into SQL."""
    if not re.fullmatch(r"[A-Za-z0-9_]+",name):raise ValueError("Unexpected source-field token")
    return r"\Code{" + name + "}"


def _write_executive_metrics(output: Path, context: dict) -> Path:
    values=context["executive_metrics_values"]
    rows=[]
    for block in values["windows"]:
        rows.append({"window_start":block["cohorts"][0],"window_end":block["cohorts"][-1],
                     "n_cohorts":block["n_cohorts"],"n_acquired":block["n_acquired"],"age_month":values["age_month"],
                     "blended_cac":block["blended_cac"],
                     "retained_share":block["retained_share"],
                     "paid_raw_retention":block["paid_raw_retention"],
                     "paid_fixed_mix_retention":block["paid_fixed_mix_retention"],
                     "cumulative_contribution_per_customer":block["contribution_per_customer"],
                     "cash_after_cac_per_customer":block["cash_after_cac_per_customer"],
                     "ex_test_cac":context["renewal_window_evidence"]["experiment_excluded"]["earlier" if block["year"]==values["windows"][0]["year"] else "later"]["blended_cac"],
                     "ex_test_cash":context["renewal_window_evidence"]["experiment_excluded"]["earlier" if block["year"]==values["windows"][0]["year"] else "later"]["cash_after_cac_per_customer"],
                     "weighting":"original acquired customer counts",
                     "source":"tables/cohort_cash_economics.csv", "source_sha256":_sha(output/"tables/cohort_cash_economics.csv")})
    path=output/"report/executive_metrics.csv";path.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(path,index=False,float_format="%.10f",lineterminator="\n")
    evidence={**context["renewal_window_evidence"],"source_hashes":{name:_sha(output/"tables"/name) for name in ["cohort_totals.csv","cohort_cash_economics.csv","cohort_age_summary.csv","cohort_economics_ex_tests.csv"]}}
    _write_json(path.parent/"matched_cohort_comparison.json",evidence)
    return path


def _model_text(value: str) -> str:
    """Typeset the documented model's known mathematical expressions as math."""
    rendered = _tex(value)
    for plain, math in {"alpha/(alpha+beta+t-1)": r"$\alpha/(\alpha+\beta+t-1)$",
                        "mu*(1-mu)/(phi+1)": r"$\mu(1-\mu)/(\phi+1)$"}.items():
        rendered = rendered.replace(plain, math)
    return rendered


def _ucv_table(table: dict) -> str:
    categories = ("Identifiers", "Engagement", "Relationship", "Perception")
    if set(table["columns"]) != set(categories):
        raise ValueError("Every dataset must have all four Universal Customer View categories")
    cells = []
    for category in categories:
        fields = table["columns"][category]
        cells.append(r"\newline ".join(_field_tex(x)+(r"\textsuperscript{\ensuremath{\dagger}}" if x in table.get("context_only_fields",[]) else "") for x in fields) if fields else r"\textcolor{BriefMuted}{Not observed}")
    note=" ".join(f"{field}: {table['rationale'][field]}" for field in table.get("context_only_fields",[]))
    label="ucv-"+table["file"].removesuffix(".csv").replace("_","-")
    return (r"\TableCaption{"+label+"}{Universal Customer View: "+_tex(table["file"])+".}\n"
            +r"\Evidence{"+_tex(table["source"]+" | "+table["grain"])+"}\n"
            + r"{\fontsize{8}{10}\selectfont\begin{tabularx}{\linewidth}{@{}YYYY@{}}\toprule" + "\n"
            + " & ".join(r"\textbf{" + c + "}" for c in categories) + r"\\\midrule" + "\n"
            + " & ".join(cells) + r"\\\bottomrule\end{tabularx}}\par" + "\n"
            +(r"\Evidence{"+_tex(note)+"}\n" if note else ""))


def _valuation_backtest_context(frame: pd.DataFrame, summary: dict) -> dict:
    """Expose what was genuinely forecast, rather than scoring observed payback."""
    frame=frame.sort_values(["observed_months_at_origin","cohort_month"],ascending=[False,True]).copy()
    if len(frame)!=int(summary["n_forecast_cohorts"]):
        raise ValueError("Valuation backtest row count does not match its summary")
    total_error=frame.pred_ltv_before_cac-frame.actual_ltv_before_cac
    tail_error=frame.pred_forecast_tail_value-frame.actual_forecast_tail_value
    if not np.allclose(total_error,tail_error,rtol=0,atol=1e-8):
        raise ValueError("Valuation backtest does not preserve the same observed prefix")
    already=frame.actual_payback_month.notna() & (frame.actual_payback_month<=frame.observed_months_at_origin)
    scored=(~already)&frame.actual_payback_month.notna()&frame.pred_payback_month.notna()
    if int(already.sum())!=int(summary["n_payback_already_observed"]) or int(scored.sum())!=int(summary["n_both_recovered"]):
        raise ValueError("Payback evaluation must exclude already-observed recovery")
    def month(value):return str(int(value)) if pd.notna(value) else "not recovered"
    rows=[]
    for index,r in frame.iterrows():
        rows.append([str(r.cohort_month)[:7],f"{int(r.observed_months_at_origin)} / {int(r.horizon_months-r.observed_months_at_origin)}",
                     f"${r.actual_ltv_before_cac:.2f}",f"${r.pred_ltv_before_cac:.2f}",f"${r.baseline_ltv_before_cac:.2f}",
                     month(r.actual_payback_month)+" / "+month(r.pred_payback_month),
                     "Already observed" if already.loc[index] else "Future; scored" if scored.loc[index] else "Not in month MAE"])
    error=float(np.abs(frame.loc[scored,"pred_payback_month"]-frame.loc[scored,"actual_payback_month"]).mean()) if scored.any() else None
    if error is not None and not np.isclose(error,float(summary["payback_mae_months_for_both_recovered"]),rtol=0,atol=1e-8):
        raise ValueError("Payback MAE does not match the genuinely forecast cases")
    paragraph=(f"At the {summary['training_last_calendar_month'][:7]} forecast origin, {len(frame)} cohorts had an unfinished 12-month value horizon. "
               f"Payback had already occurred for {int(already.sum())}; those cases are excluded from forecast-month MAE. "
               f"The {int(scored.sum())} remaining cases with both observed and predicted recovery have payback-month MAE {error:.2f}. "
               "This is a small future-payback sample, not evidence of universally exact prediction.")
    return {"valuation_backtest_table":r"{\fontsize{8}{10}\selectfont "+_latex_table(
                ["Cohort","Observed / forecast months","Actual LTV","Model LTV","Baseline LTV","Payback actual / model","Payback evaluation"],rows,
                "p{.10\\linewidth}p{.14\\linewidth}rrrp{.14\\linewidth}Y")+"}",
            "valuation_backtest_sentence":_tex(paragraph),
            "valuation_backtest_origin":_tex(summary["training_last_calendar_month"]),
            "valuation_backtest_counts":{"rows":len(frame),"already_observed":int(already.sum()),"scored":int(scored.sum()),"mae_months":error}}


def _appendix_context(output: Path) -> dict:
    """Use saved model/documentation evidence; never infer a schema from raw rows."""
    model = _json(output / "model_summary.json")
    description = model.get("model_description", {})
    required_description = {"retention", "revenue", "heterogeneity", "censoring", "forecast", "source_adaptation"}
    if not required_description.issubset(description):
        raise ValueError("Model metadata must explain its specification before the report presents results")
    params = _table(output, "parameter_summary.csv", ("parameter", "role", "prior", "mean", "sd", "p05", "p95", "r_hat", "ess", "interpretation"))
    if params.parameter.duplicated().any():
        raise ValueError("Parameter summary repeats parameter names")
    numeric = params[["mean", "sd", "p05", "p95", "r_hat", "ess"]].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError("Parameter summary contains nonfinite estimates or diagnostics")
    # Every estimate remains in the downloadable table. A repeated family of
    # cohort effects is summarized in the PDF, never replaced by fabricated zeroes.
    is_cohort = params.parameter.str.contains(r"cohort_z|cohort_raw|cohort_effect\[", regex=True)
    structural = params.loc[~is_cohort].copy()
    parameter_rows = [[str(r.parameter), str(r.prior), f"{r['mean']:.3f}",
                       f"{r.p05:.3f} to {r.p95:.3f}", f"{r.r_hat:.3f}", f"{r.ess:,.0f}"]
                      for _, r in structural.iterrows()]
    parameter_table = (r"{\fontsize{7.8}{9.5}\selectfont "
                       + _latex_table(["Parameter", "Prior", "Mean", "5th--95th", "R-hat", "ESS"],
                                      parameter_rows, "p{.22\\linewidth}p{.20\\linewidth}rrY r".replace(" ", "")) + "}")
    if is_cohort.any():
        z = params.loc[is_cohort]
        note = (f"The {len(z)} standardized cohort offsets z have posterior means from {z['mean'].min():.3f} to {z['mean'].max():.3f}; multiply each draw by cohort_scale to obtain its log-odds shift. "
                f"Their largest R-hat is {z.r_hat.max():.3f}; smallest effective sample size is {z.ess.min():,.0f}. "
                "The complete parameter_summary.csv provides every cohort effect, prior, interval and interpretation.")
        parameter_table += "\n" + r"\Evidence{" + _tex(note) + "}"
    by_name=params.set_index("parameter")
    mean_intercept=float(by_name.loc["mean_beta[intercept]","mean"])
    concentration_intercept=float(by_name.loc["concentration_beta[intercept]","mean"])
    trend=by_name.loc["mean_beta[cohort_trend]"]
    trend_interpretation=("it is below zero, supporting lower mean churn in later cohorts within this model" if trend.p95<0 else "it is above zero, supporting higher mean churn in later cohorts within this model" if trend.p05>0 else "it includes zero, so this coefficient does not establish a directional cohort trend")
    transformed=(f"At the coefficient means, Search / save time at centered cohort trend and zero offset has mean latent monthly churn mu={1/(1+np.exp(-mean_intercept)):.1%} and concentration phi={np.exp(concentration_intercept):.2f}. The cohort-trend coefficient's 5th--95th interval is {trend.p05:.3f} to {trend.p95:.3f}; {trend_interpretation}. This is a model-based description, not a causal effect of acquisition date.")
    parameter_table += "\n" + r"\Evidence{" + _tex(transformed) + "}"
    d = model["diagnostic"]
    estimation_rows = [
        ["Inference", model.get("inference", d.get("inference", "NUTS"))],
        ["Chains / warmup / samples", f"{model.get('chains', model.get('num_chains', 'see model manifest'))} / {model.get('warmup_per_chain', model.get('num_warmup', 'see model manifest'))} / {model.get('samples_per_chain', model.get('num_samples', 'see model manifest'))} per chain"],
        ["Posterior forecast draws", str(model["draws"])],
        ["Maximum R-hat / minimum ESS", f"{float(d['max_r_hat']):.3f} / {float(d['min_ess']):,.0f}"],
        ["Divergences", str(d["divergences"])],
        ["Seed / numerical backend", f"{model['seed']} / {model.get('backend', 'cpu')} / {model.get('float_precision', 'float64')}"],
    ]
    bt = model["backtest"]; vb = model["valuation_backtest"]
    from .benchmark import validate_benchmark
    validate_benchmark(output)
    benchmark = _json(output / "benchmark_summary.json")
    for key in ("n_cells", "training_last_calendar_month", "held_out_calendar_months"):
        if benchmark[key] != bt[key]:
            raise ValueError(f"The Orduz benchmark does not match the main holdout: {key}")
    main_holdout = _table(output, "backtest.csv")
    neural_holdout = _table(output, "orduz_benchmark.csv")
    holdout_keys = ["cohort_month", "channel", "primary_need", "age_month", "calendar_month"]
    joined = main_holdout.merge(neural_holdout, on=holdout_keys, how="outer", validate="one_to_one", indicator=True)
    if not (joined["_merge"] == "both").all() or not np.array_equal(joined.actual_retained_x, joined.actual_retained_y):
        raise ValueError("Main and neural benchmark score different retained-customer outcomes")
    benchmark_sentence=(f"On the same {bt['n_cells']} held-out cells, retained-count MAE is {bt['retention_mae']:.3f} for sBG, {benchmark['retention_mae']:.3f} for the Orduz-inspired {benchmark['architecture']['hidden_units']}-hidden-unit network, and {bt['baseline_retention_mae']:.3f} for the naive baseline. The network uses variational inference and a conditional monthly churn likelihood; it does not supply executive LTV. Revenue WAPE evaluates the main Gamma revenue model, not the retention-only network.")
    backtest_rows = [
        ["Retained-count MAE", f"{bt['retention_mae']:.2f}", f"{bt['baseline_retention_mae']:.2f}", "People per withheld cell"],
        ["Revenue WAPE", f"{bt['revenue_wape']:.1%}", f"{bt['baseline_revenue_wape']:.1%}", "Withheld calendar months"],
        ["12-month LTV MAE", f"${vb['ltv_mae']:.2f}", f"${vb['baseline_ltv_mae']:.2f}", "Value per original customer"],
    ]
    if "retention_wape" in bt:
        baseline_wape=f"{bt['baseline_retention_wape']:.1%}" if "baseline_retention_wape" in bt else "Not reported"
        backtest_rows.insert(1,["Retained-count WAPE",f"{bt['retention_wape']:.1%}",baseline_wape,"Retained customers, not revenue"])
    valuation_context=_valuation_backtest_context(_table(output,"valuation_backtest.csv"),vb)
    calendar=_table(output,"calendar_fit_checks.csv",("calendar_month","actual_retained","fitted_retained","standardized_residual"))
    _validate_unique(calendar,["calendar_month"],"calendar_fit_checks")
    calendar=calendar.assign(abs_residual=calendar.standardized_residual.abs()).sort_values(["abs_residual","calendar_month"],ascending=[False,True]).head(4)
    calendar_rows=[[str(r.calendar_month)[:7],f"{r.actual_retained:,.0f}",f"{r.fitted_retained:,.1f}",f"{r.standardized_residual:+.2f}"] for _,r in calendar.iterrows()]
    diagram_manifest = _json(output / "diagrams/diagram_manifest.json")
    ucv_path = output / "diagrams/ucv-tables.json"
    expected_ucv = diagram_manifest.get("output_hashes", {}).get("diagrams/ucv-tables.json")
    if not expected_ucv or _sha(ucv_path) != expected_ucv:
        raise ValueError("Dataset UCV documentation is not bound to the diagram manifest")
    ucv = _json(ucv_path)
    tables = ucv["tables"]
    if len(tables) != 8 or len({t["file"] for t in tables}) != 8:
        raise ValueError("Report requires one UCV table for each of eight distinct raw exports")
    analysis_inputs = _json(output / "analysis_input_manifest.json")["files"]
    for table in tables:
        if table["source_sha256"] != analysis_inputs.get(table["file"], {}).get("sha256"):
            raise ValueError(f"UCV and analysis describe different source data: {table['file']}")
    architecture = output / "diagrams/source-systems-report.png"
    if not architecture.exists():
        raise FileNotFoundError("Render the Archify source-systems-report.png before building the report")
    architecture_expected = diagram_manifest.get("output_hashes", {}).get("diagrams/source-systems-report.png")
    if not architecture_expected or _sha(architecture) != architecture_expected:
        raise ValueError("Archify architecture figure is not bound to the diagram manifest")
    shutil.copyfile(architecture, output / "report/figures/source-systems-report.png")
    schema = output / "diagrams/source-tables-report.png"
    if _sha(schema) != diagram_manifest.get("output_hashes", {}).get("diagrams/source-tables-report.png"):
        raise ValueError("Detailed Archify schema is not bound to the diagram manifest")
    shutil.copyfile(schema, output / "report/figures/source-tables-report.png")
    for stem in ["journey-save-time","journey-build-skill","knowledge-assets"]:
        path=output/"diagrams"/(stem+".png")
        expected=diagram_manifest.get("output_hashes",{}).get("diagrams/"+path.name)
        if not expected or not path.is_file() or _sha(path)!=expected:
            raise ValueError(f"Required Archify figure is missing or not hash-bound: {stem}")
        shutil.copyfile(path,output/"report/figures"/path.name)
    style = _validate_style()
    from .ucv import CATEGORY_DEFINITIONS
    model_description = " ".join(str(description[x]) for x in ["retention", "heterogeneity", "censoring"])
    technical = " ".join(str(description[x]) for x in ["retention", "heterogeneity", "revenue", "censoring"])
    contract_rows = [
        ["Joining cohort", "Month of the first successful payment, derived from complete payment history."],
        ["Customer survival", "Renewing contractual membership; original cohort size is the retained-share denominator."],
        ["Revenue and contribution", "Ledger payments less discounts/refunds; contribution also subtracts recorded variable costs."],
        ["Acquisition investment", "Tracked spend, including campaigns with no attributed acquisitions; no invented organic-source CAC."],
        ["Experimental unit", "Every assigned eligible prospect, including nonbuyers and control buyers, within the prespecified follow-up window."],
        ["Unknown future", "Right-censored ages stay unobserved. Missing survey responses remain missing perceptions."],
    ]
    return {
        **valuation_context,
        "model_short_description": _tex(model["model"]),
        "model_description": _model_text(model_description),
        "model_economics_description": _tex(description["revenue"] + " " + description["forecast"].replace("Forecast bands and the probability of nonnegative expected cash cover","Forecast bands cover")),
        "model_equation": r"\[\operatorname{net\,LTV}_{H}=\sum_{a=0}^{H-1}\frac{\operatorname{E}[\text{contribution}_{a}\mid\text{observed history}]}{(1+d)^{a+1}}-\operatorname{CAC}.\]",
        "horizon_months": str(int(model["horizon_months"])),
        "interval_description": _tex(model["uncertainty_label"]),
        "model_technical_description": _model_text(technical),
        "model_specification_equations": (r"\[\begin{aligned}"
            r"p_{i,g}&\sim\operatorname{Beta}(\alpha_g,\beta_g), & \alpha_g&=\mu_g\phi_g, &\beta_g&=(1-\mu_g)\phi_g,\\"
            r"N_{g,t}\mid N_{g,t-1}&\sim\operatorname{Binomial}(N_{g,t-1},1-h_g(t)), & h_g(t)&=\frac{\alpha_g}{\alpha_g+\beta_g+t-1}."
            r"\end{aligned}\]"),
        "parameter_table": parameter_table,
        "estimation_table": _latex_table(["Setting or diagnostic", "Recorded value"], estimation_rows, "p{.36\\linewidth}Y"),
        "backtest_table": _latex_table(["Measure", "Model", "Baseline", "Interpretation"], backtest_rows, "p{.28\\linewidth}rrY"),
        "calendar_residual_table":_latex_table(["Calendar month","Observed renewals","One-step fitted","Standardized residual"],calendar_rows,"Yrrr"),
        "holdout_dates":_tex(f"Training includes {bt['training_last_calendar_month'][:7]}; withheld months are "+", ".join(x[:7] for x in bt['held_out_calendar_months'])+"."),
        "benchmark_sentence": _tex(benchmark_sentence),
        "model_source_note": r"\Evidence{" + _tex(description["source_adaptation"]) + "}",
        "validation_boundary": _tex(vb.get("limitation", "The held-out periods do not establish forecast accuracy in a new business regime.")),
        "architecture_figure": r"\ReportFigure{source-architecture}{Eight source exports become analytical views and decision evidence through an auditable local pipeline.}{source-systems-report.png}{3.6in}",
        "data_contract_table": _latex_table(["Definition", "Contract"], contract_rows, "p{.25\\linewidth}Y"),
        "style_version": _tex(style["upstream_style_version"]),
        "ucv_tables_first": "\n".join(_ucv_table(t) for t in tables[:3]),
        "ucv_tables_second": "\n".join(_ucv_table(t) for t in tables[3:6]),
        "ucv_tables_third": "\n".join(_ucv_table(t) for t in tables[6:]),
        "ucv_category_definitions":_tex(" ".join(f"{name}: {definition}" for name,definition in CATEGORY_DEFINITIONS.items())),
        "ucv_overview_table":r"\TableCaption{ucv-overview}{What the UCV categories contribute to a customer-journey diagnosis.}"+_latex_table(
            ["UCV category","Example raw evidence","What it can establish"],[
                ["Identifiers","person_id; age_band; household_type","Which person or source record is involved; observed descriptors."],
                ["Engagement","product_events.event_type; transaction activity","What was observed at a particular time, not the customer's motivation."],
                ["Relationship","subscription_periods; renewal_outcome; plan_tier","What membership arrangement exists and whether it renews."],
                ["Perception","feedback ratings; primary_need","What customers express about needs, experience and value."],
            ],"p{.19\\linewidth}p{.32\\linewidth}Y"),
        "source_note": _tex("Juan Orduz, Revenue Retention and Customer Lifetime Value with NumPyro; Peter Fader and Bruce Hardie, contractual-customer retention and shifted-Beta-Geometric models; Gil Bouhnick, Cohort Analysis. Exact links, adaptation boundaries and licensing are retained in the repository source documentation. Archify is pinned and redistributed with its license notices."),
    }


def _compile_native(source: Path, engine: str | None=None) -> dict:
    """Compile portably; on this Windows host use native WSL in its Linux FS."""
    env=os.environ.copy();env.update({"SOURCE_DATE_EPOCH":str(EPOCH),"FORCE_SOURCE_DATE":"1","TZ":"UTC"})
    engine=engine or os.environ.get("COHORT_TEX_ENGINE")
    local=engine or ("tectonic" if shutil.which("tectonic") else "pdflatex" if shutil.which("pdflatex") else None)
    if os.name=="nt" and not local and shutil.which("wsl"):
        probe=subprocess.run(["wsl","--exec","sh","-c","command -v pdflatex && kpsewhich sourcesans.sty"],capture_output=True,timeout=20)
        if probe.returncode:raise RuntimeError("No native TeX engine found, and WSL lacks pdflatex/Source Sans. Install a supported TeX engine; editable .tex is preserved.")
        linux_source=subprocess.check_output(["wsl","--exec","wslpath","-a",source.parent.as_posix()],text=True).strip()
        figure_bytes=b"".join(p.name.encode("utf-8")+p.read_bytes() for p in sorted((source.parent/"figures").glob("*")) if p.is_file())
        content_key=hashlib.sha256(source.read_bytes()+(source.parent/"labreport.sty").read_bytes()
                                   +(source.parent/"longxiu-research-brief.sty").read_bytes()+figure_bytes).hexdigest()[:16]
        # Independent output folders must never race on the same native build
        # directory. TeX metadata omits host paths, preserving identical PDFs.
        location_key=hashlib.sha256(source.parent.resolve().as_posix().encode("utf-8")).hexdigest()[:12]
        key=content_key+"-"+location_key
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


def _caption_registry(source: str) -> list[dict]:
    """Number fixed-position exhibits in source order and reject duplicate labels."""
    counters={"figure":0,"table":0};seen=set();records=[]
    pattern=r"\\(ReportFigure|FigureCaption|TableCaption)\{([^{}]+)\}\{([^{}]*)\}"
    for match in re.finditer(pattern,source):
        kind="table" if match[1]=="TableCaption" else "figure"
        label=("tab:" if kind=="table" else "fig:")+match[2]
        if label in seen:raise ValueError(f"Duplicate exhibit label: {label}")
        seen.add(label);counters[kind]+=1
        if not match[3].strip():raise ValueError(f"Exhibit requires a descriptive caption: {label}")
        records.append({"type":kind,"number":counters[kind],"label":label,"caption_tex":match[3]})
    referenced=set(re.findall(r"\\ref\{((?:fig|tab):[^{}]+)\}",source))
    if referenced-seen:raise ValueError(f"Unresolved exhibit references: {sorted(referenced-seen)}")
    return records


def _pdf_copyability(path: Path) -> dict:
    """Check the actual PDF text layer, not only the TeX spelling of code."""
    from pypdf import PdfReader
    from .data import SCHEMAS
    text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    fields=sorted({field for schema in SCHEMAS.values() for field in schema})
    required=["uv sync --frozen","uv run --frozen",*SCHEMAS,*fields]
    missing=[token for token in required if token not in text]
    if missing:raise ValueError(f"PDF code-copyability check failed: {missing}")
    return {"extractor":"pypdf","commands":2,"source_filenames":len(SCHEMAS),"distinct_fields":len(fields),"status":"passed"}


def build_report(output_dir: Path, compile_pdf: bool=True) -> dict:
    """Produce a decision-facing report and required technical/data appendices."""
    output=Path(output_dir).resolve();directory=output/"report";directory.mkdir(parents=True,exist_ok=True)
    _json(output/"model_summary.json") # No silent placeholder forecast.
    charts=build_charts(output)
    style=_validate_style()
    ctx={**_context(output), **_appendix_context(output)}
    metrics_path=_write_executive_metrics(output,ctx)
    env=Environment(loader=FileSystemLoader(ROOT/"templates"),undefined=StrictUndefined,
                    variable_start_string=r"\VAR{",variable_end_string="}",autoescape=False)
    source=directory/"customer-economics-report.tex"
    rendered=env.get_template("customer-economics-report.tex.j2").render(**ctx)
    exhibits=_caption_registry(rendered)
    source.write_text(rendered,encoding="utf-8",newline="\n")
    _write_json(directory/"exhibit_registry.json",{"exhibits":exhibits})
    shutil.copyfile(ROOT/"templates/labreport.sty",directory/"labreport.sty")
    shutil.copyfile(ROOT/"templates/longxiu-research-brief.sty",directory/"longxiu-research-brief.sty")
    manifest={"version":3,"source_date_epoch":EPOCH,"report_source_sha256":_sha(source),"style_sha256":_sha(directory/"labreport.sty"),
              "upstream_style_version":style["upstream_style_version"],"upstream_style_sha256":_sha(directory/"longxiu-research-brief.sty"),
              "template_sha256":_sha(ROOT/"templates/customer-economics-report.tex.j2"),
              "report_skill_sha256":_sha(ROOT/"skills/executive-report/SKILL.md"),
              "parameter_summary_sha256":_sha(output/"tables/parameter_summary.csv"),
              "executive_metrics_sha256":_sha(metrics_path),
              "matched_cohort_comparison_sha256":_sha(directory/"matched_cohort_comparison.json"),
              "diagram_manifest_sha256":_sha(output/"diagrams/diagram_manifest.json"),
              "benchmark_manifest_sha256":_sha(output/"benchmark_manifest.json"),
              "ucv_sha256":_sha(output/"diagrams/ucv-tables.json"),
              "chart_manifest_sha256":_sha(directory/"chart_manifest.json"),"analysis_summary_sha256":_sha(output/"analysis_summary.json"),
              "model_summary_sha256":_sha(output/"model_summary.json"),"tables":charts["sources"],"compiled":False,
              "exhibit_registry_sha256":_sha(directory/"exhibit_registry.json"),
              "figure_count":sum(x["type"]=="figure" for x in exhibits),"table_count":sum(x["type"]=="table" for x in exhibits),
              "renewal_window_evidence":ctx["renewal_window_evidence"]}
    manifest["learner_choices_sha256"]=_sha(output/"learner_choices.json") if (output/"learner_choices.json").exists() else None
    if compile_pdf:
        manifest["build"]=_compile_native(source)
        from pypdf import PdfReader
        pdf=PdfReader(source.with_suffix(".pdf"))
        expected_pages=rendered.count(r"\PageTitle{")
        schema_page=rendered.split(r"\BeginSchemaFoldout",1)[0].count(r"\PageTitle{")
        if len(pdf.pages)!=expected_pages:raise ValueError(f"Expected {expected_pages} designed pages including the schema foldout, got {len(pdf.pages)}; inspect pagination")
        for index,page in enumerate(pdf.pages):
            width,height=(1190.551,841.89) if index==schema_page else (612,792)
            if abs(float(page.mediabox.width)-width)>1 or abs(float(page.mediabox.height)-height)>1:raise ValueError("Report must use Letter portrait with one A3 landscape schema foldout")
        manifest.update({"compiled":True,"pages":len(pdf.pages),"pdf":"report/customer-economics-report.pdf"})
        manifest["pdf_copyability"]=_pdf_copyability(source.with_suffix(".pdf"))
    _write_json(directory/"report_manifest.json",manifest)
    return manifest
