#!/usr/bin/env python3
"""Instructor diagnostic: perturb variational initialization and compare value intervals."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from cohort_lab.analysis import validate_analysis
from cohort_lab.model import _validate,_posterior,_future,_economic_ratios,discounted_value,KEYS,DRAWS,HORIZON


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    validate_analysis(output)
    frame=_validate(pd.read_csv(output/'tables/cohort_age_summary.csv'))
    latest=frame[frame.cohort_month==frame.cohort_month.max()]
    records=[]
    for steps,scale in [(1200,.05),(3000,.02),(3000,.2)]:
        draws,diagnostic=_posterior(frame,20261116,steps,init_scale=scale)
        total=np.zeros((DRAWS,HORIZON));n=0
        for _,g in latest.groupby(KEYS):
            observed=min(len(g),HORIZON);total[:,:observed]+=g.contribution.to_numpy()[:observed]
            ages=list(range(observed,HORIZON));_,gross=_future(draws,g.iloc[-1],ages,float(g.n_retained.iloc[-1]))
            _,ratio=_economic_ratios(frame,g.iloc[-1],ages)
            total[:,observed:]+=gross*ratio;n+=int(g.n_acquired.iloc[0])
        value=discounted_value(total)/n
        record={'steps':steps,'init_scale':scale,'latest_cohort':str(latest.cohort_month.iloc[0]),
                'ltv_mean':float(value.mean()),'p05':float(np.quantile(value,.05)),
                'p95':float(np.quantile(value,.95)),'width':float(np.quantile(value,.95)-np.quantile(value,.05)),
                'diagnostic':diagnostic}
        records.append(record);print(json.dumps(record),flush=True)
    comparison={'width_relative_difference':abs(records[1]['width']-records[2]['width'])/max(records[1]['width'],records[2]['width']),
                'mean_relative_difference':abs(records[1]['ltv_mean']-records[2]['ltv_mean'])/records[1]['ltv_mean']}
    receipt={'records':records,'comparison':comparison,
             'interpretation':'Sensitivity of approximate posterior parameter intervals; this does not establish full predictive coverage or eliminate structural uncertainty.'}
    (output/'model_stability.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(comparison),flush=True)


if __name__=='__main__':main()
