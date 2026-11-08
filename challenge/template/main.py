"""Runnable interface example: pooled constant-hazard retention and cash rates.

This is NOT the released hierarchical sBG + Gamma reference model. Replace
predict() with your model and select it using historical validation only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

KEYS = ['cohort_month','channel','primary_need','calendar_month','age_month']
EXPOSURES = ['n_acquired','origin_retained']
PREDICTIONS = ['predicted_retained','predicted_net_revenue','predicted_contribution']


def predict(tables: dict[str,pd.DataFrame], prediction_grid: pd.DataFrame, *, seed: int) -> pd.DataFrame:
    """Use only the supplied observed tables; return one forecast per grid row.

    Example assumptions: constant monthly retention within channel/need;
    stationary cash contribution per paid month; no customer heterogeneity.
    seed is accepted for the common interface; this example is deterministic.
    """
    grid = prediction_grid.copy(deep=True)
    origin = pd.Period(grid.calendar_month.min(),freq='M') - 1
    people = tables['people'][['person_id','primary_need']]
    campaigns = tables['campaign_spend'][['campaign_id','channel']].drop_duplicates()
    if campaigns.campaign_id.duplicated().any():
        raise ValueError('A campaign has conflicting channels')
    acquisition = tables['acquisition_attribution'].merge(people,on='person_id',validate='one_to_one')
    acquisition = acquisition.merge(campaigns,left_on='credited_campaign_id',right_on='campaign_id',how='left',validate='many_to_one')
    acquisition['channel'] = acquisition.channel.fillna(acquisition.source_type)
    subjects = acquisition[['person_id','channel','primary_need']]
    periods = tables['subscription_periods'].merge(subjects,on='person_id',validate='many_to_one')
    periods['month'] = pd.to_datetime(periods.period_start).dt.to_period('M')
    periods = periods[(periods.month<=origin) & periods.renewal_outcome.ne('pending')].copy()
    first = periods.loc[periods.renewal_outcome.eq('paid')].groupby('person_id').month.min()
    periods['first_paid_month'] = periods.person_id.map(first)
    renewals = periods[periods.month>periods.first_paid_month].copy()
    renewals['success'] = renewals.renewal_outcome.eq('paid').astype(int)
    segments = ['channel','primary_need']
    renewal_rates = renewals.groupby(segments).success.agg(['sum','count'])
    # Beta(1,1) smoothing is an explicit example choice, not private knowledge.
    renewal_rates['q'] = (renewal_rates['sum']+1)/(renewal_rates['count']+2)
    paid_months = periods[periods.renewal_outcome.eq('paid')].groupby(segments).size()
    cash = tables['transactions'].merge(subjects,on='person_id',validate='many_to_one').copy()
    if (pd.to_datetime(cash.occurred_at).dt.to_period('M')>origin).any():
        raise ValueError('Transactions after the forecast origin were supplied')
    cash['net'] = cash.gross_amount-cash.discount_amount-cash.refund_amount
    cash['contribution'] = cash.net-cash.variable_cost
    rates = cash.groupby(segments)[['net','contribution']].sum().div(paid_months,axis=0)
    result = []
    for row in grid.itertuples(index=False):
        segment = (row.channel,row.primary_need)
        if segment not in rates.index or segment not in renewal_rates.index:
            raise ValueError('Example model needs observed paid cycles and renewals in each segment')
        q = float(renewal_rates.loc[segment,'q'])
        ahead = pd.Period(row.calendar_month,freq='M').ordinal-origin.ordinal
        retained = float(row.origin_retained)*q**ahead
        net = max(0.0,float(rates.loc[segment,'net']))
        contribution = min(net,max(0.0,float(rates.loc[segment,'contribution'])))
        result.append((retained,retained*net,retained*contribution))
    grid[PREDICTIONS] = pd.DataFrame(result,index=grid.index,columns=PREDICTIONS)
    return grid[KEYS+EXPOSURES+PREDICTIONS]


def load_tables(data_dir: Path, contract: dict) -> dict[str,pd.DataFrame]:
    expected = contract['input_tables']
    if {p.name for p in data_dir.glob('*.csv')} != {name+'.csv' for name in expected}:
        raise ValueError('Supply exactly the eight permitted observed CSVs')
    tables = {}
    for name, fields in expected.items():
        dtypes = {field:('string' if kind in {'VARCHAR','DATE','TIMESTAMP'} else
                         'Int64' if kind=='INTEGER' else 'float64') for field,kind in fields.items()}
        table = pd.read_csv(data_dir/(name+'.csv'),dtype=dtypes)
        if list(table.columns)!=list(fields):
            raise ValueError('Unexpected source schema: '+name)
        tables[name] = table
    return tables


def validate_output(predictions: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(predictions,pd.DataFrame) or set(predictions)!=set(KEYS+EXPOSURES+PREDICTIONS):
        raise ValueError('Return exactly the required grid and prediction columns')
    if predictions.duplicated(KEYS).any():
        raise ValueError('Duplicate prediction keys')
    ordered = predictions.sort_values(KEYS).reset_index(drop=True)
    expected = grid.sort_values(KEYS).reset_index(drop=True)
    pd.testing.assert_frame_equal(ordered[KEYS+EXPOSURES],expected[KEYS+EXPOSURES],check_dtype=False)
    values = ordered[PREDICTIONS].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any():
        raise ValueError('Predictions must be finite and nonnegative')
    if (ordered.predicted_retained>ordered.origin_retained+1e-8).any():
        raise ValueError('Predicted retained count exceeds origin survivors')
    if (ordered.groupby(KEYS[:3]).predicted_retained.diff().dropna()>1e-8).any():
        raise ValueError('Expected membership must not increase')
    if ((ordered.predicted_retained==0) & ((ordered.predicted_net_revenue>0)|(ordered.predicted_contribution>0))).any():
        raise ValueError('Zero expected members must have zero expected receipts')
    if (ordered.predicted_contribution>ordered.predicted_net_revenue+1e-8).any():
        raise ValueError('Contribution exceeds net revenue')
    return ordered[KEYS+EXPOSURES+PREDICTIONS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--prediction-grid',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=20261116)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.receipt.json').exists():
        parser.error('Use a new output path; existing forecasts are preserved')
    contract_path = Path(__file__).with_name('submission-contract.json')
    contract = json.loads(contract_path.read_text())
    tables = load_tables(args.data_dir,contract)
    grid = pd.read_csv(args.prediction_grid)
    started = time.monotonic()
    predictions = validate_output(predict(tables,grid.copy(deep=True),seed=args.seed),grid)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    predictions.to_csv(args.output,index=False,float_format='%.10f',lineterminator='\n')
    sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    receipt = {'model':'Example pooled constant hazard; not the released sBG reference',
               'rows':len(predictions),'seed':args.seed,'elapsed_seconds':time.monotonic()-started,
               'source_sha256':sha(__file__),'uv_lock_sha256':sha(Path(__file__).with_name('uv.lock')),
               'contract_sha256':sha(contract_path),'prediction_grid_sha256':sha(args.prediction_grid),
               'input_sha256':{name:sha(args.data_dir/(name+'.csv')) for name in tables},
               'prediction_sha256':sha(args.output),'future_outcomes_read':False}
    args.output.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'validated','rows':len(predictions),'output':str(args.output)}))


if __name__ == '__main__':
    main()
