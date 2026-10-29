"""Hierarchical shifted-Beta-Geometric retention and Gamma revenue forecasts.

Persistent customer heterogeneity is integrated out of the conditional renewal
likelihood. Source generation is separate from the inference workflow. The Gamma
revenue component adapts Orduz; his neural-network approach is a separately
labelled validation comparison, never the source of executive valuations.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

# The released classroom model has a fixed CPU/float64 execution contract.
# Override inherited accelerator defaults before JAX is imported.
os.environ["JAX_PLATFORMS"] = "cpu"
os.environ["JAX_ENABLE_X64"] = "true"
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

KEYS = ["cohort_month", "channel", "primary_need"]
HORIZON = 12
DISCOUNT = 0.01
DRAWS = 400
MEAN_FEATURES = ['intercept', 'build_skill', 'partner', 'organic', 'cohort_trend']
CONCENTRATION_FEATURES = ['intercept', 'build_skill', 'partner', 'organic']
REVENUE_FEATURES = ['intercept', 'log1p_age', 'cohort_trend', 'build_skill', 'partner', 'organic']


def _retention_features(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    # Explicit whitelist: no latent simulator truth, outcomes or post-acquisition
    # engagement/feedback may enter the inference design matrix.
    x = np.column_stack([np.ones(len(frame)), (frame.primary_need == 'build_skill').astype(float),
                         (frame.channel == 'partner').astype(float), (frame.channel == 'organic').astype(float),
                         (frame.cohort_index.to_numpy(float)-11.5)/11.5])
    return x, x[:, :4]


def sbg_survival(alpha: np.ndarray, beta: np.ndarray, age: np.ndarray) -> np.ndarray:
    """P(still subscribed after age renewal decisions); S(0)=1."""
    from scipy.special import betaln
    return np.exp(betaln(alpha, beta + age) - betaln(alpha, beta))


def _sbg_parameters(draws: dict, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    from scipy.special import expit
    x, xc = _retention_features(frame)
    ci = frame.cohort_index.to_numpy(int)
    if (ci < 0).any() or (ci >= 24).any():
        raise ValueError('Forecast cohort must be among the 24 observed acquisition cohorts')
    mu = expit(draws['mean_beta'] @ x.T + draws['cohort_scale'][:, None] * draws['cohort_z'][:, ci])
    phi = np.exp(draws['concentration_beta'] @ xc.T)
    return mu * phi, (1-mu) * phi, mu, phi


def _hazard_draws(draws: dict, frame: pd.DataFrame) -> np.ndarray:
    alpha, beta, _, _ = _sbg_parameters(draws, frame)
    return alpha / (alpha + beta + np.maximum(frame.age_month.to_numpy(float), 1) - 1)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _csv(path: Path, frame: pd.DataFrame) -> None:
    frame=frame.copy()
    for col in frame.columns:
        if col.endswith('payback_month') or col == 'payback_age': frame[col]=frame[col].astype('Int64')
    frame.to_csv(path, index=False, float_format="%.10f", lineterminator="\n")


def discounted_value(contribution: np.ndarray, rate: float = DISCOUNT) -> np.ndarray:
    """Month age zero is the first receipt, at end-of-month t=1."""
    a = np.asarray(contribution, dtype=float)
    return np.sum(a / (1 + rate) ** np.arange(1, a.shape[-1] + 1), axis=-1)


def cash_payback(contribution: np.ndarray, acquisition_spend: float) -> int | None:
    crossed = np.flatnonzero(np.cumsum(np.asarray(contribution)) >= acquisition_spend)
    return int(crossed[0]) if len(crossed) else None


def _features(frame: pd.DataFrame) -> np.ndarray:
    age = frame.age_month.to_numpy(dtype=float)
    return np.column_stack([
        np.ones(len(frame)), np.log1p(age),
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
    if not set(frame.channel).issubset({'search','partner','organic'}):
        raise ValueError('Unsupported channel; unknown labels must not become the Search reference')
    if not set(frame.primary_need).issubset({'save_time','build_skill'}):
        raise ValueError('Unsupported primary need; unknown labels must not become the saving-time reference')
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


def _dispersed_initial_strategy(initial: dict):
    """Seeded, independent site/chain starts, jittered in unconstrained space."""
    import jax
    import jax.numpy as jnp
    from functools import partial
    from numpyro.distributions import biject_to
    from numpyro.infer.initialization import init_to_uniform
    def initialize(site):
        if site['type']=='sample' and not site['is_observed']:
            if site['name'] not in initial: return init_to_uniform(site)
            transform=biject_to(site['fn'].support)
            base=transform.inv(jnp.asarray(initial[site['name']]))
            jitter=jax.random.uniform(site['kwargs']['rng_key'],shape=base.shape,minval=-.5,maxval=.5)
            return transform(base+jitter)
    # NumPyro distinguishes a configured strategy (partial) from a factory.
    return partial(initialize)


def _posterior(frame: pd.DataFrame, seed: int, steps: int, init_scale: float = .05) -> tuple[dict, dict]:
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS
    from numpyro.diagnostics import summary as mcmc_summary

    numpyro.enable_x64()
    if jax.default_backend() != 'cpu' or not jax.config.x64_enabled:
        raise RuntimeError('The release inference requires CPU JAX with float64 enabled')
    f = frame.copy()
    f['previous_retained'] = f.groupby(KEYS, sort=True).n_retained.shift(1)
    h = f[(f.age_month > 0) & (f.previous_retained > 0)]
    r = f[(f.n_retained > 0) & (f.gross_payment_revenue > 0)]
    if len(h) < 12 or len(r) < 12:
        raise ValueError('Insufficient mature cohort cells for the two-part model')
    xh, xc = _retention_features(h)
    xr = _features(r)
    ci = h.cohort_index.to_numpy(int)
    age = h.age_month.to_numpy(float)
    prev = h.previous_retained.to_numpy(float)
    survivors = h.n_retained.to_numpy(float)
    alive = r.n_retained.to_numpy(float)
    gross = r.gross_payment_revenue.to_numpy(float) / 100.0
    br = np.linalg.lstsq(xr, np.log(gross/alive), rcond=None)[0]

    def specification():
        mean_beta = numpyro.sample('mean_beta', dist.Normal(jnp.array([-2.5,0.,0.,0.,0.]), jnp.array([1.,.5,.5,.5,.5])).to_event(1))
        concentration_beta = numpyro.sample('concentration_beta', dist.Normal(jnp.array([jnp.log(4.),0.,0.,0.]), jnp.array([1.,.5,.5,.5])).to_event(1))
        cohort_scale = numpyro.sample('cohort_scale', dist.HalfNormal(.25))
        cohort_z = numpyro.sample('cohort_z', dist.Normal(jnp.zeros(24), 1.).to_event(1))
        mu = jax.nn.sigmoid(jnp.asarray(xh) @ mean_beta + cohort_scale*cohort_z[jnp.asarray(ci)])
        phi = jnp.exp(jnp.asarray(xc) @ concentration_beta)
        hazard = mu*phi/(phi+jnp.asarray(age)-1)
        numpyro.sample('survivors', dist.Binomial(total_count=jnp.asarray(prev), probs=1-hazard), obs=jnp.asarray(survivors))
        revenue_beta = numpyro.sample('revenue_beta', dist.Normal(jnp.array([-.5,.1,0.,0.,0.,0.]), .8).to_event(1))
        shape = numpyro.sample('revenue_shape', dist.LogNormal(jnp.log(4.), .8))
        mean_per_retained = jnp.exp(jnp.asarray(xr) @ revenue_beta)
        numpyro.sample('revenue', dist.Gamma(jnp.asarray(alive)*shape, shape/mean_per_retained), obs=jnp.asarray(gross))

    initial = {'mean_beta':jnp.array([-2.,0.,0.,0.,0.]),
               'concentration_beta':jnp.array([jnp.log(4.),0.,0.,0.]),
               'cohort_scale':jnp.asarray(max(init_scale,.02)), 'cohort_z':jnp.zeros(24),
               'revenue_beta':jnp.asarray(br), 'revenue_shape':jnp.asarray(4.)}
    # Four sequential chains work on a single CPU device. The command's step
    # budget maps to warmup and sampling rather than a variational optimizer.
    samples_per_chain = max(1000, steps//3)
    kernel = NUTS(specification, target_accept_prob=.95, init_strategy=_dispersed_initial_strategy(initial))
    sampler = MCMC(kernel, num_warmup=samples_per_chain, num_samples=samples_per_chain,
                   num_chains=4, chain_method='sequential', progress_bar=False)
    sampler.run(jax.random.PRNGKey(seed))
    chained = {k:np.asarray(v) for k,v in sampler.get_samples(group_by_chain=True).items()}
    diagnostics = mcmc_summary(chained, prob=.90, group_by_chain=True)
    flat = {k:v.reshape((-1,)+v.shape[2:]) for k,v in chained.items()}
    indices = np.linspace(0,4*samples_per_chain-1,DRAWS,dtype=int)
    draws = {k:v[indices] for k,v in flat.items()}
    if any(not np.isfinite(v).all() for v in flat.values()):
        raise RuntimeError('Nonfinite MCMC parameter draws; no forecast released')
    parameter_rows = []
    for name, values in sorted(flat.items()):
        dimensions = list(np.ndindex(values.shape[1:])) if values.ndim>1 else [()]
        for index in dimensions:
            vector = values[(slice(None),)+index]
            suffix = index[0] if index else None
            role = {'mean_beta':'churn_mean', 'concentration_beta':'churn_concentration',
                    'cohort_scale':'cohort_scale', 'cohort_z':'cohort_effect',
                    'revenue_beta':'revenue', 'revenue_shape':'revenue_dispersion'}[name]
            if name == 'mean_beta':
                label = MEAN_FEATURES[suffix]; prior = 'Normal(-2.5,1)' if suffix==0 else 'Normal(0,0.5)'
                interpretation = 'Log-odds coefficient for mean individual churn propensity: '+label
            elif name == 'concentration_beta':
                label = CONCENTRATION_FEATURES[suffix]; prior = 'Normal(log(4),1)' if suffix==0 else 'Normal(0,0.5)'
                interpretation = 'Log-concentration coefficient (larger concentration means less dispersion at fixed mean): '+label
            elif name == 'cohort_z':
                label = str(pd.Timestamp('2024-01-01')+pd.DateOffset(months=suffix))[:7]
                prior = 'Normal(0,1)'; interpretation = 'Standardized cohort effect; multiply by cohort_scale for log-odds shift'
            elif name == 'cohort_scale':
                label = ''; prior='HalfNormal(0.25)'; interpretation='Standard deviation of shared cohort log-odds deviations'
            elif name == 'revenue_beta':
                label=REVENUE_FEATURES[suffix]; center=[-.5,.1,0,0,0,0][suffix]
                prior=f'Normal({center},0.8)'
                interpretation=('Log gross revenue per retained member in $100 units at age zero, Search, saving-time need and centered cohort trend'
                                if suffix==0 else 'Log-multiplier of gross revenue per retained member for one unit of '+label)
            else:
                label=''; prior='LogNormal(log(4),0.8)'; interpretation='Gamma shape per retained member; governs revenue dispersion'
            stat=diagnostics[name]
            parameter_rows.append({'parameter':name+('['+label+']' if label else ''), 'role':role,
                'prior':prior,'mean':float(vector.mean()),'sd':float(vector.std(ddof=1)),
                'p05':float(np.quantile(vector,.05)), 'p95':float(np.quantile(vector,.95)),
                'r_hat':float(np.asarray(stat['r_hat'])[index]),'ess':float(np.asarray(stat['n_eff'])[index]),
                'interpretation':interpretation})
    hazard_mean = _hazard_draws(draws,h).mean(axis=0)
    if any(not np.isfinite([row['r_hat'],row['ess']]).all() for row in parameter_rows):
        raise RuntimeError('Nonfinite MCMC convergence diagnostics; no forecast released')
    revenue_mean=(np.exp(draws['revenue_beta'] @ xr.T)*alive).mean(axis=0)
    revenue_variance=((np.exp(draws['revenue_beta'] @ xr.T)**2)*alive/draws['revenue_shape'][:,None]).mean(axis=0)
    divergence_count = int(np.asarray(sampler.get_extra_fields()['diverging']).sum())
    return draws, {'inference':'NumPyro NUTS', 'chains':4,'warmup_per_chain':samples_per_chain,
        'samples_per_chain':samples_per_chain,'target_accept':.95,'forecast_draws':DRAWS,
        'initialization':'Independent seeded Uniform(-0.5,0.5) jitter around declared centers in unconstrained parameter space, separately for each chain/site',
        'max_r_hat':max(x['r_hat'] for x in parameter_rows),'min_ess':min(x['ess'] for x in parameter_rows),
        'divergences':divergence_count,'parameter_summary':parameter_rows,
        'n_retention_cells':len(h),'n_revenue_cells':len(r),
        'retention_pearson_dispersion':round(float(np.sum((survivors-prev*(1-hazard_mean))**2/np.maximum(prev*hazard_mean*(1-hazard_mean),1e-9))/max(len(h)-35,1)),8),
        'revenue_pearson_dispersion':round(float(np.sum((gross-revenue_mean)**2/np.maximum(revenue_variance,1e-9))/max(len(r)-7,1)),8),
        'actual_backend':jax.default_backend(),'actual_x64':bool(jax.config.x64_enabled),'init_scale':init_scale}


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
    rows = pd.DataFrame([{**exemplar.to_dict(), "age_month": a} for a in ages])
    if not ages:
        return np.empty((DRAWS, 0)), np.empty((DRAWS, 0))
    hazard = _hazard_draws(draws, rows)
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
               "retention_wape":float(abs(b.actual_retained-b.pred_retained).sum()/max(b.actual_retained.sum(),1)),
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
            "p_expected_cash_balance_nonnegative_at_horizon": float(np.mean(contrib.sum(axis=1)>=spend)) if supported_cac else np.nan,
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
    baseline_matched=pending.dropna(subset=['actual_payback_month','baseline_payback_month'])
    return result,{'training_last_calendar_month':str(cutoff),'n_forecast_cohorts':len(result),
                  'ltv_mae':float(abs(result.actual_ltv_before_cac-result.pred_ltv_before_cac).mean()),
                  'baseline_ltv_mae':float(abs(result.actual_ltv_before_cac-result.baseline_ltv_before_cac).mean()),
                  'forecast_tail_value_mae':float(abs(result.actual_forecast_tail_value-result.pred_forecast_tail_value).mean()),
                  'forecast_tail_value_wape':float(abs(result.actual_forecast_tail_value-result.pred_forecast_tail_value).sum()/result.actual_forecast_tail_value.sum()),
                  'payback_mae_months_for_both_recovered':float(abs(matched.actual_payback_month-matched.pred_payback_month).mean()) if len(matched) else None,
                  'n_both_recovered':len(matched),'n_payback_after_origin':len(pending),'n_payback_already_observed':int((result.actual_payback_month<=result.observed_months_at_origin).sum()),
                  'n_payback_not_recovered_within_horizon':int(result.actual_payback_month.isna().sum()),
                  'n_forecast_missed_actual_recovery':int(pending.pred_payback_month.isna().sum()),
                  'baseline_payback_mae_months_for_both_recovered':float(abs(baseline_matched.actual_payback_month-baseline_matched.baseline_payback_month).mean()) if len(baseline_matched) else None,
                  'n_baseline_both_recovered':len(baseline_matched),
                  'training_only_economics':True,'diagnostic':diagnostic,
                  'baseline':'Naive frozen last-three-period renewal rate and revenue per retained customer; a one-period cohort uses an explicit 0.8 renewal fallback.',
                  'limitation':'One historical year-end origin, not proof of accuracy for every future cohort or business regime.'}


def fit_and_forecast(output_dir: Path, seed: int = 20261116, steps: int = 3000) -> dict:
    output_dir = Path(output_dir)
    tables = output_dir/"tables"
    input_paths = [tables/"cohort_age_summary.csv", tables/"cohort_acquisition_costs.csv",tables/"cohort_cash_economics.csv"]
    if steps < 3000:
        raise ValueError("At least a 3000-step budget is required (1000 NUTS warmup and draws per chain)")
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
        required_checks={'max_r_hat','min_ess','divergences','retention_pearson_dispersion','revenue_pearson_dispersion'}
        if not required_checks.issubset(check): raise RuntimeError(f'{label}: required diagnostics missing')
        if not np.isfinite([check[k] for k in required_checks]).all():
            raise RuntimeError(f'{label}: nonfinite MCMC diagnostics; no report released')
        if check['max_r_hat']>1.01 or check['min_ess']<400 or check['divergences']:
            raise RuntimeError(f'{label}: MCMC diagnostics failed (R-hat={check["max_r_hat"]:.4f}, ESS={check["min_ess"]:.1f}, divergences={check["divergences"]}); no report released')
        # Misspecification is reported, not hidden by tuning the simulator or
        # refusing every imperfect fit. Numerical convergence and fit differ.
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
                "n_retained_p05":float(np.quantile(a["retained"][:,age],.05)),
                "n_retained_p95":float(np.quantile(a["retained"][:,age],.95)),
                "net_revenue_mean":float(a["revenue"][:,age].mean()),"contribution_mean":float(a["contribution"][:,age].mean()),
                "contribution_p05":float(np.quantile(a["contribution"][:,age],.05)),
                "contribution_p95":float(np.quantile(a["contribution"][:,age],.95)),
                "cumulative_after_acquisition":float(cumul[age]),"observed":bool(obs[age])})
            curves[-1]['cumulative_after_acquisition_per_customer']=float(cumul[age]/a['n'])
    from scipy.special import expit
    fit_checks=frame.copy()
    prior=fit_checks.groupby(KEYS).n_retained.shift(1).fillna(fit_checks.n_acquired).to_numpy()
    fitted=prior*(1-_hazard_draws(draws,fit_checks).mean(axis=0))
    fit_checks['fitted_retained_one_step']=np.where(fit_checks.age_month==0,fit_checks.n_acquired,fitted)
    observed_checks=fit_checks[fit_checks.age_month>0].copy()
    hmean=_hazard_draws(draws,observed_checks).mean(axis=0)
    observed_checks['conditional_variance']=prior[fit_checks.age_month.to_numpy()>0]*hmean*(1-hmean)
    calendar_checks=observed_checks.groupby('calendar_month',sort=True).agg(
        actual_retained=('n_retained','sum'),fitted_retained=('fitted_retained_one_step','sum'),
        conditional_variance=('conditional_variance','sum'),n_risk_cells=('n_retained','size')).reset_index()
    calendar_checks['residual_members']=calendar_checks.actual_retained-calendar_checks.fitted_retained
    calendar_checks['standardized_residual']=calendar_checks.residual_members/np.sqrt(calendar_checks.conditional_variance.clip(lower=1e-9))
    fit_checks=fit_checks[fit_checks.cohort_month.isin(sorted(frame.cohort_month.unique())[-6:])][KEYS+['age_month','n_acquired','n_retained','fitted_retained_one_step']]
    cells=frame[KEYS+['cohort_index']].drop_duplicates().reset_index(drop=True)
    alpha,beta,mu,phi=_sbg_parameters(draws,cells)
    heterogeneity=cells[KEYS].copy()
    heterogeneity['mean_churn_mean']=mu.mean(axis=0)
    heterogeneity['mean_churn_p05']=np.quantile(mu,.05,axis=0)
    heterogeneity['mean_churn_p95']=np.quantile(mu,.95,axis=0)
    heterogeneity['variance_churn_mean']=(mu*(1-mu)/(phi+1)).mean(axis=0)
    heterogeneity['concentration_mean']=phi.mean(axis=0)
    heterogeneity['alpha_mean']=alpha.mean(axis=0);heterogeneity['beta_mean']=beta.mean(axis=0)
    mature_keys=set(map(tuple,frame.loc[frame.age_month>0,KEYS].drop_duplicates().to_numpy()))
    heterogeneity['no_observed_renewals']=[tuple(row) not in mature_keys for row in cells[KEYS].to_numpy()]
    outputs={"cohort_valuation.csv":pd.DataFrame(cohort_records),"cohort_valuation_by_segment.csv":pd.DataFrame(cell_records),
             "forecast_curve.csv":pd.DataFrame(curves),"backtest.csv":backtest,"valuation_backtest.csv":value_backtest,"model_fit_checks.csv":fit_checks,
             "parameter_summary.csv":pd.DataFrame(diagnostic['parameter_summary']),"heterogeneity_by_cell.csv":heterogeneity,
             "calendar_fit_checks.csv":calendar_checks}
    for name,df in outputs.items(): _csv(tables/name,df)
    draw_path=output_dir/"posterior_draws.json"
    _json(draw_path,{k:v.tolist() for k,v in sorted(draws.items())})
    settings={"seed":seed,"steps":steps,"draws":DRAWS,"horizon_months":HORIZON,"discount_rate":DISCOUNT,
              "backend":"cpu","float_precision":"float64","inference":"NUTS","init_scale":.05,
              "chains":4,"warmup_per_chain":max(1000,steps//3),"samples_per_chain":max(1000,steps//3),"target_accept":.95,
              "initialization":"Seeded independent per-chain/site Uniform(-0.5,0.5) jitter in unconstrained parameter space"}
    versions={k:importlib.metadata.version(k) for k in ["jax","jaxlib","numpyro","numpy","pandas","scipy"]}
    summary={"model":"Hierarchical shifted-Beta-Geometric retention + Gamma gross revenue; NumPyro NUTS",
             **settings,"backtest":bt,"valuation_backtest":vbt,"diagnostic":diagnostic,"versions":versions,
             "uncertainty_label":"Posterior parameter uncertainty conditional on the single-Beta model and fixed future economics; not a full predictive interval",
             "economics_assumption":"Future net revenue and contribution shares of payment revenue use observed channel-by-need-by-age shares, with the same group's observed renewal ages (age>=1) as fallback. Shares are fixed assumptions, not causally identified or assigned posterior uncertainty.",
             "cost_scope":"Tracked acquisition spending; organic cell CAC unsupported. Whole-cohort blended CAC is tracked spend divided by all acquired customers, including organic control buyers; it is not paid-only acquisition efficiency or fully loaded company cost.",
             "interpretation":"Twelve-month contribution value, not an infinite-lifetime claim. Forecast cash payback is the first undiscounted crossing of the posterior-mean contribution path, not a distribution of realized payback times; payback_age is zero-based and payback_month counts receipts from 1. Discounting uses t=age+1. A separate flag identifies later recrossing below cost. Cohort random effects partially pool departures from the shared linear cohort trend. December 2025 has no observed renewal decisions; its retention forecast is inferred from other cohorts. No causal long-run campaign value is inferred from customer LTV.",
             "model_description":{
                 "retention":"Each member has a persistent churn propensity. Within a cohort/need/channel cell, propensities follow one Beta distribution. After t-1 renewals, churn hazard is alpha/(alpha+beta+t-1); observed survivors follow a Binomial with the previous survivor count as its risk set.",
                 "heterogeneity":"Mean propensity varies with need, channel, cohort trend and a partially pooled cohort effect. Concentration varies with need and channel. Variance is mu*(1-mu)/(phi+1). Falling aggregate churn can reflect survivor selection, not improvement in each individual's loyalty.",
                 "revenue":"Gross payment revenue follows a Gamma distribution with shape proportional to observed retained members. Expected revenue per retained member varies with log age, cohort trend, need and channel. Observed age-aligned net and contribution shares translate future gross revenue into economics.",
                 "censoring":"Pending renewals and future ages are unobserved, not failures. Age zero establishes acquisition and supplies no renewal trial. Churn is absorbing in this business.",
                 "forecast":"Keep observed revenue and contribution; forecast recursively from the last observed survivors. All cohorts are valued over the same 12 monthly receipts, discounting at 1% per month. Forecast bands and the probability of nonnegative expected cash cover parameter uncertainty, not renewal/revenue process noise or all future business risk.",
                 "source_adaptation":"Retention extends Fader-Hardie sBG with mean/concentration parameterization, logit/log covariate links, a non-centered cohort effect on mean churn, grouped conditional Binomial renewal likelihood and NUTS estimation. Revenue adapts Orduz's Gamma structure but uses observed active counts in fitting, an additional per-member shape multiplier, a mean link without an age-by-cohort interaction, need/channel covariates and $100 scaling. Conditional on observed activity, the revenue and retention likelihoods have independent parameter blocks. The separate Orduz-inspired 4-hidden-unit Bayesian neural network is a retention comparison only; its cumulative-count likelihood is changed to conditional renewal trials."},
             "source":"https://juanitorduz.github.io/revenue_retention_numpyro/",
             "retention_source":"https://www.brucehardie.com/notes/016/"}
    _json(output_dir/"model_summary.json",summary)
    artifacts=["model_summary.json","posterior_draws.json"]+["tables/"+x for x in outputs]
    manifest={"schema_version":1,"settings":settings,"input_hashes":{p.name:_hash(p) for p in input_paths},
              "code_sha256":_hash(Path(__file__)),"versions":versions,
              "output_hashes":{p:_hash(output_dir/p) for p in artifacts}}
    _json(output_dir/"model_manifest.json",manifest)
    return {"artifacts":artifacts+["model_manifest.json"],"backtest":bt,"model":summary["model"]}
