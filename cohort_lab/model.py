"""Seeded, conditional-retention and revenue forecasts for fixed cohort inputs.

The model is an adaptation of the two-part retention/revenue idea in Juan
Orduz's tutorial. It uses a conditional survivor likelihood rather than
independent counts of the same surviving customers. No neural network or
customer-clustering model is required. Intervals describe approximate posterior
parameter uncertainty conditional on this model and the future margin rule.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

os.environ.setdefault("JAX_PLATFORMS", "cpu")
os.environ.setdefault("JAX_ENABLE_X64", "true")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

KEYS = ["cohort_month", "channel", "primary_need"]
HORIZON = 12
DISCOUNT = 0.01
DRAWS = 400


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, float_format="%.10f", lineterminator="\n")


def discounted_value(contribution: np.ndarray, rate: float = DISCOUNT) -> np.ndarray:
    """Month age zero is the first receipt, at end-of-month t=1."""
    a = np.asarray(contribution, dtype=float)
    return np.sum(a / (1 + rate) ** np.arange(1, a.shape[-1] + 1), axis=-1)


def cash_payback(contribution: np.ndarray, acquisition_spend: float) -> int | None:
    crossed = np.flatnonzero(np.cumsum(np.asarray(contribution)) >= acquisition_spend)
    return int(crossed[0]) if len(crossed) else None


def _features(frame: pd.DataFrame, survival: bool = False) -> np.ndarray:
    age = frame.age_month.to_numpy(dtype=float)
    return np.column_stack([
        np.ones(len(frame)), np.log(np.maximum(age, 1)) if survival else np.log1p(age),
        (frame.cohort_index.to_numpy(dtype=float) - 11.5) / 12,
        (frame.primary_need == "build_skill").astype(float),
        (frame.channel == "partner").astype(float),
        (frame.channel == "organic").astype(float),
    ])


def _validate(frame: pd.DataFrame) -> pd.DataFrame:
    required = KEYS + ["cohort_index", "age_month", "calendar_month", "n_acquired", "n_retained",
                       "gross_payment_revenue", "net_revenue", "contribution"]
    if set(required) - set(frame):
        raise ValueError(f"Missing cohort model columns: {sorted(set(required) - set(frame))}")
    if frame.duplicated(KEYS + ["age_month"]).any():
        raise ValueError("Duplicate cohort-age cells")
    frame = frame.sort_values(KEYS + ["age_month"]).reset_index(drop=True)
    for _, g in frame.groupby(KEYS, sort=True):
        if not np.array_equal(g.age_month, np.arange(len(g))):
            raise ValueError("Observed cohort ages must be consecutive from zero; do not fill future cells")
        if g.n_acquired.nunique() != 1 or g.n_retained.iloc[0] != g.n_acquired.iloc[0]:
            raise ValueError("Original acquired-customer denominator must be fixed and equal month-zero survivors")
        if (np.diff(g.n_retained) > 0).any() or (g.n_retained < 0).any():
            raise ValueError("This conditional-survival model requires nonincreasing subscription membership")
    if not np.isfinite(frame[required[3:]].select_dtypes(include="number")).all().all():
        raise ValueError("Nonfinite numerical model inputs")
    if ((frame.n_retained > 0) & (frame.gross_payment_revenue <= 0)).any():
        raise ValueError("This paid-subscription revenue model does not support retained cells with zero payment revenue")
    if (frame.groupby(KEYS).size().groupby(level=0).nunique() > 1).any():
        raise ValueError("All channel/need cells in a cohort must have the same observed age range")
    return frame


def _posterior(frame: pd.DataFrame, seed: int, steps: int, init_scale: float = .05) -> tuple[dict, dict]:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import SVI, Trace_ELBO
    from numpyro.infer.autoguide import AutoNormal
    from numpyro.infer.initialization import init_to_value
    from numpyro.optim import ClippedAdam

    numpyro.enable_x64()
    if jax.default_backend() != 'cpu' or not jax.config.x64_enabled:
        raise RuntimeError('The frozen classroom run requires CPU JAX with float64 enabled')
    f = frame.copy()
    f["previous_retained"] = f.groupby(KEYS, sort=True).n_retained.shift(1)
    h = f[(f.age_month > 0) & (f.previous_retained > 0)]
    r = f[(f.n_retained > 0) & (f.gross_payment_revenue > 0)]
    if len(h) < 12 or len(r) < 12:
        raise ValueError("Insufficient mature cohort cells for the two-part model")
    xh, xr = _features(h, True), _features(r)
    prev = h.previous_retained.to_numpy(float)
    survivors = h.n_retained.to_numpy(float)
    alive = r.n_retained.to_numpy(float)
    gross = r.gross_payment_revenue.to_numpy(float) / 100.0

    # Data-based starting values stabilize SVI; priors and likelihood still
    # determine the posterior. A fixed design matrix makes replay inspectable.
    from scipy.special import logit
    bh = np.linalg.lstsq(xh, logit(np.clip((prev-survivors+0.5)/(prev+1), .001, .999)), rcond=None)[0]
    br = np.linalg.lstsq(xr, np.log(gross/alive), rcond=None)[0]

    def specification():
        hazard_beta = numpyro.sample("hazard_beta", dist.Normal(jnp.array([-1., -.7, 0., 0., 0., 0.]), 1.2).to_event(1))
        revenue_beta = numpyro.sample("revenue_beta", dist.Normal(jnp.array([-.5, .1, 0., 0., 0., 0.]), 0.8).to_event(1))
        shape = numpyro.sample("revenue_shape", dist.LogNormal(jnp.log(4.), .8))
        hazard = jax.nn.sigmoid(jnp.asarray(xh) @ hazard_beta)
        mean_per_retained = jnp.exp(jnp.asarray(xr) @ revenue_beta)
        numpyro.sample("survivors", dist.Binomial(total_count=jnp.asarray(prev), probs=1-hazard), obs=jnp.asarray(survivors))
        numpyro.sample("revenue", dist.Gamma(jnp.asarray(alive)*shape, shape/mean_per_retained), obs=jnp.asarray(gross))

    guide = AutoNormal(specification, init_loc_fn=init_to_value(values={
        "hazard_beta": jnp.asarray(bh), "revenue_beta": jnp.asarray(br), "revenue_shape": jnp.asarray(4.)}), init_scale=init_scale)
    svi = SVI(specification, guide, ClippedAdam(.008, clip_norm=10.), Trace_ELBO())
    result = svi.run(jax.random.PRNGKey(seed), steps, progress_bar=False)
    loss = np.asarray(result.losses)
    if not np.isfinite(loss).all():
        raise RuntimeError("Nonfinite variational objective; no forecast released")
    posterior = guide.sample_posterior(jax.random.PRNGKey(seed+1), result.params, sample_shape=(DRAWS,))
    draws = {k: np.asarray(v) for k, v in posterior.items()}
    for k, v in draws.items():
        if not np.isfinite(v).all():
            raise RuntimeError(f"Nonfinite posterior {k}")
    # Diagnostic reduction order can differ at ~1e-12 between CPU processes.
    # Eight decimal places are far beyond meaningful loss precision; keep the
    # posterior draws untouched and give the reported diagnostic a fixed format.
    from scipy.special import expit
    hazard_mean=expit(draws['hazard_beta'] @ xh.T).mean(axis=0)
    revenue_mean=(np.exp(draws['revenue_beta'] @ xr.T)*alive).mean(axis=0)
    revenue_variance=((np.exp(draws['revenue_beta'] @ xr.T)**2)*alive/draws['revenue_shape'][:,None]).mean(axis=0)
    return draws, {"n_retention_cells": len(h), "n_revenue_cells": len(r),
                   "initial_loss_mean": round(float(np.mean(loss[:min(100,len(loss))])), 8),
                   "final_loss_mean": round(float(np.mean(loss[-min(100,len(loss)):])), 8),
                   "final_two_window_relative_loss_change": round(float(abs(np.mean(loss[-250:])-np.mean(loss[-500:-250]))/max(abs(np.mean(loss[-250:])),1)),8) if len(loss)>=500 else None,
                   "retention_pearson_dispersion": round(float(np.sum((survivors-prev*(1-hazard_mean))**2/np.maximum(prev*hazard_mean*(1-hazard_mean),1e-9))/max(len(h)-6,1)),8),
                   "revenue_pearson_dispersion": round(float(np.sum((gross-revenue_mean)**2/np.maximum(revenue_variance,1e-9))/max(len(r)-7,1)),8),
                   "actual_backend":jax.default_backend(),"actual_x64":bool(jax.config.x64_enabled),"init_scale":init_scale}


def _economic_ratios(frame: pd.DataFrame, exemplar: pd.Series, ages: list[int]) -> tuple[np.ndarray,np.ndarray]:
    """Age-aligned observed economics; never borrow a new customer's setup cost for a renewal."""
    group=frame[(frame.channel==exemplar.channel)&(frame.primary_need==exemplar.primary_need)]
    fallback=group[group.age_month>=1]
    net=[]; contribution=[]
    for age in ages:
        cell=group[group.age_month==age]
        if cell.gross_payment_revenue.sum()<=0: cell=fallback
        gross=float(cell.gross_payment_revenue.sum())
        if gross<=0: raise ValueError('No observed renewal economics support this forecast cell')
        net.append(float(cell.net_revenue.sum())/gross)
        contribution.append(float(cell.contribution.sum())/gross)
    return np.asarray(net),np.asarray(contribution)


def _future(draws: dict, exemplar: pd.Series, ages: list[int], remaining: float) -> tuple[np.ndarray, np.ndarray]:
    from scipy.special import expit
    rows = pd.DataFrame([{**exemplar.to_dict(), "age_month": a} for a in ages])
    if not ages:
        return np.empty((DRAWS, 0)), np.empty((DRAWS, 0))
    hazard = expit(draws["hazard_beta"] @ _features(rows, True).T)
    retained = remaining * np.cumprod(1-hazard, axis=1)
    per_retained = 100*np.exp(draws["revenue_beta"] @ _features(rows).T)
    return retained, retained*per_retained


def _backtest(frame: pd.DataFrame, seed: int, steps: int) -> tuple[pd.DataFrame, dict]:
    months = sorted(frame.calendar_month.unique())
    cutoff = months[-4]
    train = frame[frame.calendar_month <= cutoff].copy()
    draws, diagnostic = _posterior(train, seed+100, steps)
    records = []
    for key, g in train.groupby(KEYS, sort=True):
        actual = frame[(frame.cohort_month == key[0]) & (frame.channel == key[1]) &
                       (frame.primary_need == key[2]) & (frame.calendar_month > cutoff)].sort_values("age_month")
        if actual.empty:
            continue
        last = g.iloc[-1]
        n, revenue = _future(draws, last, actual.age_month.astype(int).tolist(), float(last.n_retained))
        # A frozen last-period conditional renewal rate is a transparent baseline.
        rates = g.n_retained.to_numpy(float)[1:] / np.maximum(g.n_retained.to_numpy(float)[:-1], 1)
        baseline_rate = float(np.mean(rates[-3:])) if len(rates) else .8
        baseline_arpu = float(g.tail(3).gross_payment_revenue.sum()/max(g.tail(3).n_retained.sum(), 1))
        for j, (_, row) in enumerate(actual.iterrows()):
            base_n = float(last.n_retained)*baseline_rate**(j+1)
            records.append({"cohort_month": key[0], "channel": key[1], "primary_need": key[2],
                "age_month": int(row.age_month), "calendar_month": row.calendar_month,
                "actual_retained": int(row.n_retained), "pred_retained": float(n[:,j].mean()),
                "actual_revenue": float(row.gross_payment_revenue), "pred_revenue": float(revenue[:,j].mean()),
                "baseline_retained": base_n, "baseline_revenue": base_n*baseline_arpu})
    b = pd.DataFrame(records).sort_values(KEYS+["age_month"]).reset_index(drop=True)
    if b.empty:
        raise ValueError("No eligible historical cohorts for chronological backtest")
    denom = float(b.actual_revenue.sum())
    summary = {"training_last_calendar_month": str(cutoff), "held_out_calendar_months": [str(x) for x in months[-3:]],
               "n_cells": len(b), "retention_mae": float(np.mean(abs(b.actual_retained-b.pred_retained))),
               "revenue_wape": float(abs(b.actual_revenue-b.pred_revenue).sum()/max(denom,1)),
               "baseline_retention_mae": float(np.mean(abs(b.actual_retained-b.baseline_retained))),
               "baseline_revenue_wape": float(abs(b.actual_revenue-b.baseline_revenue).sum()/max(denom,1)),
               "new_holdout_cohorts_excluded": True, "diagnostic": diagnostic}
    return b, summary


def _valuation_record(key: tuple, n: int, spend: float, observed_months: int,
                      contrib: np.ndarray, observed: np.ndarray, supported_cac: bool = True) -> dict:
    ltv = discounted_value(contrib) / n
    cac = spend/n if supported_cac else np.nan
    net = ltv-cac
    mean_curve = contrib.mean(axis=0)
    payback = cash_payback(mean_curve, spend) if supported_cac else None
    status = "unsupported" if not supported_cac else ("not_reached" if payback is None else
              "observed" if payback < observed_months else "forecast")
    observed_value = float(discounted_value(np.where(observed, mean_curve, 0))) / n
    total_value = float(ltv.mean())
    return {"cohort_month": key[0], "n_acquired": n, "acquisition_spend": spend if supported_cac else np.nan,
            "cac": cac, "observed_months": min(observed_months,HORIZON), "horizon_months": HORIZON,
            "ltv_before_cac_mean": total_value, "ltv_before_cac_p05": float(np.quantile(ltv,.05)),
            "ltv_before_cac_p95": float(np.quantile(ltv,.95)), "net_ltv_mean": float(net.mean()),
            "net_ltv_p05": float(np.quantile(net,.05)), "net_ltv_p95": float(np.quantile(net,.95)),
            "ltv_to_cac_mean": total_value/cac if supported_cac and cac>0 else np.nan,
            "payback_age":payback,"payback_month": None if payback is None else payback+1, "payback_status": status,
            "forecast_share": (total_value-observed_value)/total_value if total_value>0 else np.nan,
            "p_cash_balance_nonnegative_at_horizon": float(np.mean(contrib.sum(axis=1)>=spend)) if supported_cac else np.nan,
            "cash_payback_recrosses_below_cost": bool(payback is not None and (np.cumsum(mean_curve)[payback:]<spend).any()),
            "observed_discounted_contribution_per_customer": observed_value}


def _valuation_backtest(frame: pd.DataFrame, company_costs: pd.DataFrame, seed: int, steps: int) -> tuple[pd.DataFrame,dict]:
    """Replay the first year-end decision and score the actual 12-month decision quantities."""
    months=sorted(frame.calendar_month.unique())
    if len(months)<24: raise ValueError('The release LTV backtest needs two calendar years')
    cutoff=months[11]
    train=frame[frame.calendar_month<=cutoff].copy()
    draws,diagnostic=_posterior(train,seed+200,steps)
    groups={}
    for key,g in train.groupby(KEYS,sort=True):
        full=frame[(frame.cohort_month==key[0])&(frame.channel==key[1])&(frame.primary_need==key[2])].sort_values('age_month')
        if len(full)<HORIZON: continue
        prefix=min(len(g),HORIZON)
        forecast=np.zeros((DRAWS,HORIZON));baseline=np.zeros(HORIZON)
        actual=full.contribution.to_numpy(float)[:HORIZON]
        forecast[:,:prefix]=g.contribution.to_numpy(float)[:prefix]
        baseline[:prefix]=actual[:prefix]
        if prefix<HORIZON:
            ages=list(range(prefix,HORIZON))
            _,gross=_future(draws,g.iloc[-1],ages,float(g.n_retained.iloc[-1]))
            _,ratios=_economic_ratios(train,g.iloc[-1],ages)
            forecast[:,prefix:]=gross*ratios
            rates=g.n_retained.to_numpy(float)[1:]/np.maximum(g.n_retained.to_numpy(float)[:-1],1)
            rate=float(np.mean(rates[-3:])) if len(rates) else .8
            arpu=float(g.tail(3).gross_payment_revenue.sum()/max(g.tail(3).n_retained.sum(),1))
            baseline[prefix:]=float(g.n_retained.iloc[-1])*rate**np.arange(1,len(ages)+1)*arpu*ratios
        if key[0] not in groups:
            groups[key[0]]={'n':0,'actual':np.zeros(HORIZON),'forecast':np.zeros((DRAWS,HORIZON)),'baseline':np.zeros(HORIZON),'prefix':prefix}
        agg=groups[key[0]];agg['n']+=int(g.n_acquired.iloc[0]);agg['actual']+=actual;agg['forecast']+=forecast;agg['baseline']+=baseline
    rows=[]
    for cohort,a in sorted(groups.items()):
        if a['prefix']==HORIZON: continue # Already observed values are not forecasts to score.
        spend=float(company_costs.loc[cohort,'acquisition_spend']);n=a['n'];mean=a['forecast'].mean(axis=0)
        if int(company_costs.loc[cohort,'n_acquired'])!=n: raise ValueError('Backtest whole-cohort denominator differs')
        actual=float(discounted_value(a['actual'])/n);pred=float(discounted_value(mean)/n);base=float(discounted_value(a['baseline'])/n)
        pay=lambda values: None if cash_payback(values,spend) is None else cash_payback(values,spend)+1
        mask=np.arange(HORIZON)>=a['prefix']
        rows.append({'cohort_month':cohort,'observed_months_at_origin':a['prefix'],'horizon_months':HORIZON,
                     'actual_ltv_before_cac':actual,'pred_ltv_before_cac':pred,'baseline_ltv_before_cac':base,
                     'actual_net_ltv':actual-spend/n,'pred_net_ltv':pred-spend/n,
                     'actual_forecast_tail_value':float(discounted_value(np.where(mask,a['actual'],0))/n),
                     'pred_forecast_tail_value':float(discounted_value(np.where(mask,mean,0))/n),
                     'actual_payback_month':pay(a['actual']),'pred_payback_month':pay(mean),'baseline_payback_month':pay(a['baseline'])})
    result=pd.DataFrame(rows)
    pending=result[result.actual_payback_month>result.observed_months_at_origin]
    matched=pending.dropna(subset=['actual_payback_month','pred_payback_month'])
    return result,{'training_last_calendar_month':str(cutoff),'n_forecast_cohorts':len(result),
                  'ltv_mae':float(abs(result.actual_ltv_before_cac-result.pred_ltv_before_cac).mean()),
                  'baseline_ltv_mae':float(abs(result.actual_ltv_before_cac-result.baseline_ltv_before_cac).mean()),
                  'forecast_tail_value_mae':float(abs(result.actual_forecast_tail_value-result.pred_forecast_tail_value).mean()),
                  'forecast_tail_value_wape':float(abs(result.actual_forecast_tail_value-result.pred_forecast_tail_value).sum()/result.actual_forecast_tail_value.sum()),
                  'payback_mae_months_for_both_recovered':float(abs(matched.actual_payback_month-matched.pred_payback_month).mean()) if len(matched) else None,
                  'n_both_recovered':len(matched),'n_payback_after_origin':len(pending),'n_payback_already_observed':int((result.actual_payback_month<=result.observed_months_at_origin).sum()),
                  'training_only_economics':True,'diagnostic':diagnostic,
                  'baseline':'Naive frozen last-three-period renewal rate and revenue per retained customer; a one-period cohort uses an explicit 0.8 renewal fallback.',
                  'limitation':'One historical year-end origin, not proof of accuracy for every future cohort or business regime.'}


def fit_and_forecast(output_dir: Path, seed: int = 20261116, steps: int = 3000) -> dict:
    output_dir = Path(output_dir)
    tables = output_dir/"tables"
    input_paths = [tables/"cohort_age_summary.csv", tables/"cohort_acquisition_costs.csv",tables/"cohort_cash_economics.csv"]
    if steps < 3000:
        raise ValueError("At least 3000 SVI steps are required by the tested release contract")
    # Verify the analysis layer if its public validator is available.
    from cohort_lab.analysis import validate_analysis
    validate_analysis(output_dir)
    frame = _validate(pd.read_csv(input_paths[0]))
    costs = pd.read_csv(input_paths[1])
    if costs.duplicated(KEYS).any():
        raise ValueError("Duplicate acquisition cost cells")
    paid=frame.loc[~frame.channel.isin(['organic','unknown']),KEYS].drop_duplicates()
    if (paid.merge(costs[KEYS],on=KEYS,how='left',indicator=True)._merge=='left_only').any():
        raise ValueError('Paid customer cells lack acquisition cost rows')
    company_costs=pd.read_csv(input_paths[2]).query('age_month==0').set_index('cohort_month')
    if company_costs.index.duplicated().any(): raise ValueError('Duplicate whole-cohort cost rows')
    backtest, bt = _backtest(frame, seed, steps)
    value_backtest,vbt=_valuation_backtest(frame,company_costs,seed,steps)
    draws, diagnostic = _posterior(frame, seed, steps)
    for label,check in [('full fit',diagnostic),('three-month backtest',bt.get('diagnostic',{})),('LTV backtest',vbt.get('diagnostic',{}))]:
        required_checks={'final_two_window_relative_loss_change','retention_pearson_dispersion','revenue_pearson_dispersion'}
        if not required_checks.issubset(check): raise RuntimeError(f'{label}: required diagnostics missing')
        if check['final_two_window_relative_loss_change']>.005:
            raise RuntimeError(f'{label}: variational loss has not stabilized; no report released')
        if max(check['retention_pearson_dispersion'],check['revenue_pearson_dispersion'])>1.5:
            raise RuntimeError(f'{label}: residual dispersion exceeds the release diagnostic limit; reassess the likelihood')
    cost_map = costs.set_index(KEYS)
    aggregates = {}
    cell_records, curves = [], []
    for key, g in frame.groupby(KEYS, sort=True):
        g = g.sort_values("age_month")
        n0 = int(g.n_acquired.iloc[0])
        observed_len = min(len(g), HORIZON)
        retained = np.zeros((DRAWS,HORIZON)); revenue = retained.copy(); contribution = retained.copy()
        retained[:,:observed_len] = g.n_retained.to_numpy()[:observed_len]
        revenue[:,:observed_len] = g.net_revenue.to_numpy()[:observed_len]
        contribution[:,:observed_len] = g.contribution.to_numpy()[:observed_len]
        observed = np.arange(HORIZON)<observed_len
        if observed_len < HORIZON:
            future_n, future_gross = _future(draws, g.iloc[-1], list(range(observed_len,HORIZON)), float(g.n_retained.iloc[-1]))
            net_ratio,contrib_ratio=_economic_ratios(frame,g.iloc[-1],list(range(observed_len,HORIZON)))
            retained[:,observed_len:] = future_n
            revenue[:,observed_len:] = future_gross*net_ratio
            contribution[:,observed_len:] = future_gross*contrib_ratio
        cost = cost_map.loc[key] if key in cost_map.index else None
        supported = cost is not None and pd.notna(cost.cac)
        spend = float(cost.acquisition_spend) if cost is not None and pd.notna(cost.acquisition_spend) else 0.
        rec = _valuation_record(key,n0,spend,observed_len,contribution,observed,supported)
        rec.update(channel=key[1],primary_need=key[2]); cell_records.append(rec)
        if key[0] not in aggregates:
            aggregates[key[0]] = {"n":0,"spend":0.,"retained":np.zeros_like(retained),"revenue":np.zeros_like(revenue),
                                  "contribution":np.zeros_like(contribution),"observed_months":observed_len}
        a=aggregates[key[0]]; a["n"]+=n0; a["spend"]+=spend
        a["retained"]+=retained; a["revenue"]+=revenue; a["contribution"]+=contribution
    cohort_records=[]
    for cohort,a in sorted(aggregates.items()):
        # Whole-cohort SQL costs include campaigns with zero conversions and
        # unallocated spend. Do not reconstruct company costs from buyer cells.
        if cohort not in company_costs.index: raise ValueError('Whole-cohort acquisition spending is missing')
        a['spend']=float(company_costs.loc[cohort,'acquisition_spend'])
        if int(company_costs.loc[cohort,'n_acquired'])!=a['n']: raise ValueError('Whole-cohort acquisition denominator differs')
        obs=np.arange(HORIZON)<a["observed_months"]
        cohort_records.append(_valuation_record((cohort,),a["n"],a["spend"],a["observed_months"],a["contribution"],obs))
        cumul=np.cumsum(a["contribution"].mean(axis=0))-a["spend"]
        for age in range(HORIZON):
            curves.append({"cohort_month":cohort,"age_month":age,"n_retained_mean":float(a["retained"][:,age].mean()),
                "net_revenue_mean":float(a["revenue"][:,age].mean()),"contribution_mean":float(a["contribution"][:,age].mean()),
                "contribution_p05":float(np.quantile(a["contribution"][:,age],.05)),
                "contribution_p95":float(np.quantile(a["contribution"][:,age],.95)),
                "cumulative_after_acquisition":float(cumul[age]),"observed":bool(obs[age])})
            curves[-1]['cumulative_after_acquisition_per_customer']=float(cumul[age]/a['n'])
    from scipy.special import expit
    fit_checks=frame.copy()
    prior=fit_checks.groupby(KEYS).n_retained.shift(1).fillna(fit_checks.n_acquired).to_numpy()
    fitted=prior*(1-expit(draws['hazard_beta']@_features(fit_checks,True).T).mean(axis=0))
    fit_checks['fitted_retained_one_step']=np.where(fit_checks.age_month==0,fit_checks.n_acquired,fitted)
    fit_checks=fit_checks[fit_checks.cohort_month.isin(sorted(frame.cohort_month.unique())[-6:])][KEYS+['age_month','n_acquired','n_retained','fitted_retained_one_step']]
    outputs={"cohort_valuation.csv":pd.DataFrame(cohort_records),"cohort_valuation_by_segment.csv":pd.DataFrame(cell_records),
             "forecast_curve.csv":pd.DataFrame(curves),"backtest.csv":backtest,"valuation_backtest.csv":value_backtest,"model_fit_checks.csv":fit_checks}
    for name,df in outputs.items(): _csv(tables/name,df)
    draw_path=output_dir/"posterior_draws.json"
    _json(draw_path,{k:v.tolist() for k,v in sorted(draws.items())})
    settings={"seed":seed,"steps":steps,"draws":DRAWS,"horizon_months":HORIZON,"discount_rate":DISCOUNT,
              "backend":"cpu","float_precision":"float64","guide":"AutoNormal","init_scale":.05,"optimizer":"ClippedAdam(0.008)"}
    versions={k:importlib.metadata.version(k) for k in ["jax","jaxlib","numpyro","numpy","pandas","scipy"]}
    summary={"model":"Conditional binomial survival + Gamma gross revenue; NumPyro SVI",
             **settings,"backtest":bt,"valuation_backtest":vbt,"diagnostic":diagnostic,"versions":versions,
             "uncertainty_label":"Approximate posterior parameter uncertainty conditional on model and fixed future economics; not a full predictive interval",
             "economics_assumption":"Future net revenue and contribution shares of payment revenue use observed channel-by-need-by-age shares, with the same group's observed renewal ages (age>=1) as fallback. Shares are fixed assumptions, not causally identified or assigned posterior uncertainty.",
             "cost_scope":"Tracked acquisition spending; organic cell CAC unsupported; whole-cohort CAC is tracked spend divided by all acquired customers, not fully loaded company cost.",
             "interpretation":"Twelve-month contribution value, not an infinite-lifetime claim. Cash payback is the first undiscounted crossing; payback_age is zero-based and payback_month counts receipts from 1. Discounting uses t=age+1. A separate flag identifies later recrossing below cost. The model shares one linear cohort trend across groups; in-sample fit diagnostics are separate from backtests. No causal long-run campaign value is inferred from customer LTV.",
             "source":"https://juanitorduz.github.io/revenue_retention_numpyro/"}
    _json(output_dir/"model_summary.json",summary)
    artifacts=["model_summary.json","posterior_draws.json"]+["tables/"+x for x in outputs]
    manifest={"schema_version":1,"settings":settings,"input_hashes":{p.name:_hash(p) for p in input_paths},
              "code_sha256":_hash(Path(__file__)),"versions":versions,
              "output_hashes":{p:_hash(output_dir/p) for p in artifacts}}
    _json(output_dir/"model_manifest.json",manifest)
    return {"artifacts":artifacts+["model_manifest.json"],"backtest":bt,"model":summary["model"]}
