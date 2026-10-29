"""Observed-only future forecast interface; no evaluation outcomes are shipped."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ['cohort_month', 'channel', 'primary_need', 'calendar_month', 'age_month']
CELL = KEYS[:3]
PREDICTIONS = ['predicted_retained', 'predicted_net_revenue', 'predicted_contribution']
FUTURE_MONTHS = 12


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False)+'\n',encoding='utf-8')


def _preserve_existing(path: Path, content: str) -> None:
    """Do not overwrite a learner's filled template or a previous prediction."""
    expected=content.encode('utf-8')
    if path.exists() and path.read_bytes()!=expected:
        raise ValueError(f'{path.name} already contains different work; preserve it and use a new output folder')
    if not path.exists():path.write_bytes(expected)


def prediction_grid(observed: pd.DataFrame) -> pd.DataFrame:
    """Create dates and keys using only the last public observation per cell."""
    required = CELL+['calendar_month','age_month','n_acquired','n_retained']
    if set(required)-set(observed): raise ValueError('Observed cohort table lacks challenge fields')
    if observed.duplicated(CELL+['age_month']).any(): raise ValueError('Duplicate observed cohort ages')
    origin = pd.to_datetime(observed.calendar_month).max()
    rows=[]
    for key,g in observed.groupby(CELL,sort=True):
        g=g.sort_values('age_month'); last=g.iloc[-1]
        if pd.Timestamp(last.calendar_month)!=origin:
            raise ValueError('Every challenge cell must be observed through the common cutoff')
        if len(g.n_acquired.unique())!=1 or last.n_retained<0 or last.n_retained>last.n_acquired:
            raise ValueError('Invalid original or remaining customer exposure')
        for step in range(1,FUTURE_MONTHS+1):
            rows.append(dict(zip(CELL,key)) | {
                'calendar_month':(origin+pd.DateOffset(months=step)).strftime('%Y-%m-%d'),
                'age_month':int(last.age_month)+step,'n_acquired':int(last.n_acquired),
                'origin_retained':int(last.n_retained)})
    return pd.DataFrame(rows).sort_values(KEYS).reset_index(drop=True)


def write_template(output_dir: Path) -> dict:
    from .analysis import validate_analysis
    output=Path(output_dir);validate_analysis(output)
    source=output/'tables/cohort_age_summary.csv'
    frame=prediction_grid(pd.read_csv(source))
    folder=output/'challenge';folder.mkdir(parents=True,exist_ok=True)
    _preserve_existing(folder/'prediction_grid.csv',frame.to_csv(index=False,lineterminator='\n'))
    for column in PREDICTIONS:frame[column]=np.nan
    _preserve_existing(folder/'submission_template.csv',frame.to_csv(index=False,lineterminator='\n'))
    receipt={'version':1,'scope':'Next twelve calendar months for the existing observed acquisition cohorts; no new cohorts or future labels.',
        'origin_month':str(pd.to_datetime(frame.calendar_month).min()-pd.DateOffset(months=1))[:10],
        'future_months':FUTURE_MONTHS,'rows':len(frame),'cohort_input_sha256':_sha(source),
        'code_sha256':_sha(Path(__file__)),
        'output_hashes':{name:_sha(output/name) for name in ['challenge/prediction_grid.csv','challenge/submission_template.csv']},
        'artifacts':['challenge/prediction_grid.csv','challenge/submission_template.csv','challenge/template_manifest.json']}
    _write_json(folder/'template_manifest.json',receipt)
    return receipt


def validate_predictions(predictions: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Reject missing/extra cells, fabricated exposure and impossible membership."""
    if set(KEYS+PREDICTIONS)-set(predictions):raise ValueError('Missing required forecast columns')
    if predictions.duplicated(KEYS).any():raise ValueError('Duplicate prediction keys')
    if set(KEYS+['origin_retained','n_acquired'])-set(grid):raise ValueError('Invalid prediction grid')
    allowed=set(KEYS+PREDICTIONS+['origin_retained','n_acquired'])
    if set(predictions)-allowed:raise ValueError('Unexpected forecast columns')
    for col in PREDICTIONS:
        if not pd.api.types.is_numeric_dtype(predictions[col]) or not np.isfinite(predictions[col]).all():
            raise ValueError('Predictions must be finite numeric values, without blank cells')
        if (predictions[col]<0).any():raise ValueError('This business requires nonnegative predicted amounts and counts')
    joined=grid.merge(predictions,on=KEYS,how='outer',indicator=True,suffixes=('','_submitted'),validate='one_to_one')
    if not joined._merge.eq('both').all():raise ValueError('Predictions do not match the published future grid')
    for col in ['origin_retained','n_acquired']:
        if col+'_submitted' in joined and not np.array_equal(joined[col],joined[col+'_submitted']):
            raise ValueError('Submitted observed exposure differs from the grid')
    ordered=joined.sort_values(KEYS)
    for _,g in ordered.groupby(CELL,sort=True):
        counts=g.predicted_retained.to_numpy()
        if (counts>g.origin_retained.to_numpy()+1e-8).any() or (np.diff(counts)>1e-8).any():
            raise ValueError('Predicted membership must not increase or exceed origin survivors')
        if ((counts==0)&((g.predicted_net_revenue>0)|(g.predicted_contribution>0))).any():
            raise ValueError('Extinct membership cannot generate future receipts in this business')
    if (ordered.predicted_contribution>ordered.predicted_net_revenue+1e-8).any():
        raise ValueError('Contribution cannot exceed net revenue under recorded nonnegative variable costs')
    return ordered[KEYS+['n_acquired','origin_retained']+PREDICTIONS].reset_index(drop=True)


def baseline_predictions(output_dir: Path) -> dict:
    """Forecast an additional twelve calendar months with the fitted public model."""
    from .model import _future, _economic_ratios, _validate
    from .report import _validate_model_outputs
    output=Path(output_dir)
    write_template(output);_validate_model_outputs(output)
    frame=_validate(pd.read_csv(output/'tables/cohort_age_summary.csv'))
    draws={k:np.asarray(v) for k,v in json.loads((output/'posterior_draws.json').read_text()).items()}
    grid=pd.read_csv(output/'challenge/prediction_grid.csv')
    rows=[]
    for key,g in frame.groupby(CELL,sort=True):
        last=g.iloc[-1]
        future=grid[(grid.cohort_month==key[0]) & (grid.channel==key[1]) & (grid.primary_need==key[2])].copy()
        ages=future.age_month.astype(int).tolist()
        retained,gross=_future(draws,last,ages,float(last.n_retained))
        net_ratio,contrib_ratio=_economic_ratios(frame,last,ages)
        future['predicted_retained']=retained.mean(axis=0)
        future['predicted_net_revenue']=(gross*net_ratio).mean(axis=0)
        future['predicted_contribution']=(gross*contrib_ratio).mean(axis=0)
        rows.append(future)
    predictions=validate_predictions(pd.concat(rows,ignore_index=True),grid)
    target=output/'challenge/baseline_predictions.csv'
    _preserve_existing(target,predictions.to_csv(index=False,float_format='%.10f',lineterminator='\n'))
    receipt={'version':1,'model':'Hierarchical shifted-Beta-Geometric retention + Gamma revenue; CPU NumPyro',
        'scope':'Remaining contribution during the next twelve calendar months, separate from first-twelve-receipt LTV.',
        'future_outcomes_read':False,'code_sha256':_sha(Path(__file__)),
        'model_manifest_sha256':_sha(output/'model_manifest.json'),
        'template_manifest_sha256':_sha(output/'challenge/template_manifest.json'),
        'predictions_sha256':_sha(target),'rows':len(predictions),
        'artifacts':['challenge/baseline_predictions.csv','challenge/baseline_manifest.json']}
    _write_json(output/'challenge/baseline_manifest.json',receipt)
    return receipt


def validate_truth(truth: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Validate realized outcomes without imposing expected-value cash rules.

    Refunds can make realized net revenue/contribution negative, including in a
    cell with no remaining members. Never edit an answer key to fit a forecast.
    """
    actual=['n_retained','net_revenue','contribution']
    if set(KEYS+actual)-set(truth):raise ValueError('Evaluation truth lacks required keys/outcomes')
    if truth.duplicated(KEYS).any():raise ValueError('Duplicate evaluation truth keys')
    for col in actual:
        if not pd.api.types.is_numeric_dtype(truth[col]) or not np.isfinite(truth[col]).all():
            raise ValueError('Realized outcomes must be finite numeric values')
    counts=truth.n_retained.to_numpy()
    if (counts<0).any() or not np.equal(counts,np.floor(counts)).all():
        raise ValueError('Realized retained counts must be nonnegative integers')
    known=[c for c in ['origin_retained','n_acquired'] if c in truth]
    joined=grid.merge(truth[KEYS+actual+known],on=KEYS,how='outer',indicator=True,
                      suffixes=('','_submitted'),validate='one_to_one')
    if not joined._merge.eq('both').all():raise ValueError('Evaluation truth does not match the future grid')
    for col in known:
        if not np.array_equal(joined[col],joined[col+'_submitted']):
            raise ValueError('Evaluation observed exposure differs from the grid')
    ordered=joined.sort_values(KEYS)
    for _,g in ordered.groupby(CELL,sort=True):
        if (g.n_retained>g.origin_retained).any() or (np.diff(g.n_retained)>0).any():
            raise ValueError('Realized membership must not increase or exceed origin survivors')
    return ordered[KEYS+['n_acquired','origin_retained']+actual].reset_index(drop=True)


def score_predictions(predictions: pd.DataFrame, truth: pd.DataFrame, grid: pd.DataFrame) -> dict:
    """Transparent scoring rule; callers must supply their own evaluation truth.

    The public repository does not contain the 2026 answer key. This same
    function supports instructor scoring and genuinely held-out historical
    practice data; it never searches the filesystem for labels.
    """
    predicted=validate_predictions(predictions,grid)
    actual_names=['n_retained','net_revenue','contribution']
    actual=validate_truth(truth,grid).rename(columns=dict(zip(actual_names,PREDICTIONS)))
    joined=predicted.merge(actual,on=KEYS,validate='one_to_one',suffixes=('_forecast','_actual'))
    company_cohorts=joined.groupby(['cohort_month','calendar_month'],sort=True)[
        ['predicted_contribution_forecast','predicted_contribution_actual']].sum()
    actual_contribution=float(company_cohorts.predicted_contribution_actual.abs().sum())
    if actual_contribution<=0:raise ValueError('Contribution WAPE requires positive total absolute actual contribution')
    difference=company_cohorts.predicted_contribution_forecast-company_cohorts.predicted_contribution_actual
    retained_denominator=float(joined.predicted_retained_actual.sum())
    retention_wape=(float((joined.predicted_retained_forecast-joined.predicted_retained_actual).abs().sum())/retained_denominator
                    if retained_denominator>0 else None)
    return {'primary_metric':'cohort-month contribution WAPE',
        'contribution_wape':float(difference.abs().sum()/actual_contribution),
        'retention_cell_wape':retention_wape,
        'portfolio_contribution_bias':float(difference.sum()/actual_contribution),
        'rows':len(joined),'cohort_month_points':len(company_cohorts),
        'aggregation':'Sum channel/need predictions and truth within each acquisition cohort and future calendar month before absolute contribution error.',
        'ranking':'Lower primary WAPE is better; secondary diagnostics do not change the ranking.',
        'normalization':'Sum absolute actual cohort-month contribution, after aggregating channel/need cells; signed portfolio bias uses the same denominator.',
        'cash_scope':'Future contribution before acquisition cost; all acquisition cost predates this forecast window.'}
