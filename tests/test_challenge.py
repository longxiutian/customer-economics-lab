"""Future-interface checks use tiny observed histories, never private labels."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from cohort_lab.challenge import prediction_grid, validate_predictions, validate_truth, score_predictions, _preserve_existing


def _observed():
    return pd.DataFrame([
        dict(cohort_month='2025-11-01',channel='search',primary_need='save_time',calendar_month='2025-11-01',age_month=0,n_acquired=20,n_retained=20),
        dict(cohort_month='2025-11-01',channel='search',primary_need='save_time',calendar_month='2025-12-01',age_month=1,n_acquired=20,n_retained=15),
        dict(cohort_month='2025-12-01',channel='partner',primary_need='build_skill',calendar_month='2025-12-01',age_month=0,n_acquired=10,n_retained=10),
    ])


def _predictions():
    grid=prediction_grid(_observed());p=grid.copy()
    p['predicted_retained']=p.origin_retained.to_numpy()*np.tile(.9**np.arange(1,13),2)
    p['predicted_net_revenue']=p.predicted_retained*50
    p['predicted_contribution']=p.predicted_net_revenue*.4
    return grid,p


def test_grid_is_twelve_future_calendar_months_for_each_known_cohort():
    grid=prediction_grid(_observed())
    assert len(grid)==24
    assert grid.calendar_month.min()=='2026-01-01' and grid.calendar_month.max()=='2026-12-01'
    assert grid[grid.cohort_month=='2025-11-01'].age_month.tolist()==list(range(2,14))
    assert grid[grid.cohort_month=='2025-12-01'].age_month.tolist()==list(range(1,13))
    assert not any(c.startswith('actual') or c.startswith('predicted') for c in grid)
    assert set(grid.n_acquired)=={10,20} and set(grid.origin_retained)=={10,15}
    pd.testing.assert_frame_equal(grid,prediction_grid(_observed().sample(frac=1,random_state=7)))


def test_valid_predictions_allow_fractional_expected_counts_and_preserve_all_keys():
    grid,p=_predictions()
    checked=validate_predictions(p.sample(frac=1,random_state=1),grid)
    assert len(checked)==24 and np.all(checked.predicted_retained>0)


@pytest.mark.parametrize('mutation',['missing','extra','duplicate','blank','negative','increasing','too_many','profit','exposure','unknown'])
def test_submission_refuses_invalid_predictions(mutation):
    grid,p=_predictions()
    if mutation=='missing':p=p.iloc[:-1]
    elif mutation=='extra':p=pd.concat([p,p.iloc[[0]].assign(calendar_month='2027-01-01',age_month=14)])
    elif mutation=='duplicate':p=pd.concat([p,p.iloc[[0]]])
    elif mutation=='blank':p.loc[0,'predicted_retained']=np.nan
    elif mutation=='negative':p.loc[0,'predicted_net_revenue']=-1
    elif mutation=='increasing':p.loc[2,'predicted_retained']=p.loc[1,'predicted_retained']+.5
    elif mutation=='too_many':p.loc[0,'predicted_retained']=100
    elif mutation=='profit':p.loc[0,'predicted_contribution']=p.loc[0,'predicted_net_revenue']+1
    elif mutation=='exposure':p.loc[0,'origin_retained']+=1
    elif mutation=='unknown':p['private_label']=1
    with pytest.raises(ValueError):validate_predictions(p,grid)


def test_new_templates_do_not_overwrite_existing_learner_work(tmp_path):
    p=tmp_path/'submission_template.csv'
    _preserve_existing(p,'blank\n');_preserve_existing(p,'blank\n')
    p.write_text('my forecast\n')
    with pytest.raises(ValueError,match='different work'):_preserve_existing(p,'blank\n')
    assert p.read_text()=='my forecast\n'


def test_score_aggregates_cells_before_absolute_error_with_a_hand_calculation():
    grid=pd.DataFrame([
        dict(cohort_month='2025-01-01',channel=c,primary_need='save_time',calendar_month='2026-01-01',age_month=12,n_acquired=10,origin_retained=5)
        for c in ['search','partner']])
    truth=grid.assign(n_retained=4,net_revenue=100.,contribution=[40.,60.])
    pred=grid.assign(predicted_retained=[3.,4.],predicted_net_revenue=100.,predicted_contribution=[50.,40.])
    result=score_predictions(pred,truth,grid)
    # Aggregate forecast90 vs actual100 =>10%, not cell errors(10+20)/100=30%.
    assert result['contribution_wape']==pytest.approx(.1)
    assert result['portfolio_contribution_bias']==pytest.approx(-.1)
    assert result['retention_cell_wape']==pytest.approx(1/8)
    assert result['cohort_month_points']==1


def test_extinct_cells_remain_zero_and_zero_value_score_is_explicitly_undefined():
    grid=prediction_grid(_observed());grid['origin_retained']=0
    pred=grid.assign(predicted_retained=0.,predicted_net_revenue=0.,predicted_contribution=0.)
    truth=grid.assign(n_retained=0,net_revenue=0.,contribution=0.)
    validate_predictions(pred,grid)
    with pytest.raises(ValueError,match='positive total'):
        score_predictions(pred,truth,grid)
    pred.loc[0,'predicted_net_revenue']=10
    with pytest.raises(ValueError,match='Extinct'):
        validate_predictions(pred,grid)


def test_realized_refunds_do_not_inherit_expected_cash_constraints():
    grid=pd.DataFrame([
        dict(cohort_month='2025-01-01',channel=c,primary_need='save_time',calendar_month='2026-01-01',age_month=12,n_acquired=10,origin_retained=5)
        for c in ['search','partner']])
    truth=grid.assign(n_retained=[0,4],net_revenue=[-5.,100.],contribution=[-8.,60.])
    pred=grid.assign(predicted_retained=[0.,4.],predicted_net_revenue=[0.,100.],predicted_contribution=[0.,40.])
    validate_truth(truth,grid)
    # The extinct cell has a realized refund; aggregate actual52 vs forecast40.
    assert score_predictions(pred,truth,grid)['contribution_wape']==pytest.approx(12/52)
    # Absolute normalization remains well-defined for a negative realized total.
    result=score_predictions(pred.iloc[:1],truth.iloc[:1],grid.iloc[:1])
    assert result['contribution_wape']==1 and result['portfolio_contribution_bias']==1


@pytest.mark.parametrize('mutation',['fractional','increasing','nonfinite','missing','duplicate'])
def test_truth_rejects_invalid_membership_keys_and_nonfinite_cash(mutation):
    grid,p=_predictions()
    truth=grid.assign(n_retained=1,net_revenue=50.,contribution=20.)
    if mutation=='fractional':truth['n_retained']=1.5
    elif mutation=='increasing':truth.loc[1,'n_retained']=2
    elif mutation=='nonfinite':truth.loc[0,'contribution']=np.inf
    elif mutation=='missing':truth=truth.iloc[:-1]
    elif mutation=='duplicate':truth=pd.concat([truth,truth.iloc[[0]]])
    with pytest.raises(ValueError):validate_truth(truth,grid)


def test_models_load_on_cpu_when_an_inherited_environment_requests_cuda():
    env=os.environ.copy();env.update(JAX_PLATFORMS='cuda',JAX_ENABLE_X64='false',CUDA_VISIBLE_DEVICES='-1')
    result=subprocess.run([sys.executable,'-c',
        "from cohort_lab import model,benchmark; import jax,json; print(json.dumps({'backend':jax.default_backend(),'x64':bool(jax.config.x64_enabled)}))"],
        env=env,cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,check=True,timeout=45)
    assert json.loads(result.stdout)=={'backend':'cpu','x64':True}


def test_future_retention_conditions_on_origin_survivors_and_uses_customer_age():
    from cohort_lab import model
    # Beta(1,3): survival from age2 to3 is5/6, then6/7. Start from the
    # ten customers actually remaining, never the original100 acquisitions.
    d=model.DRAWS
    mean=np.zeros((d,5));mean[:,0]=np.log(.25/.75)
    concentration=np.zeros((d,4));concentration[:,0]=np.log(4.)
    revenue=np.zeros((d,6));revenue[:,0]=np.log(.5)
    draws={'mean_beta':mean,'concentration_beta':concentration,
           'cohort_scale':np.zeros(d),'cohort_z':np.zeros((d,24)),
           'revenue_beta':revenue,'revenue_shape':np.ones(d)}
    last=pd.Series(dict(cohort_month='2025-10-01',cohort_index=21,channel='search',
        primary_need='save_time',age_month=2,n_acquired=100,n_retained=10))
    retained,gross=model._future(draws,last,[3,4],10.)
    np.testing.assert_allclose(retained[:,0],10*5/6)
    np.testing.assert_allclose(retained[:,1],10*5/7)
    np.testing.assert_allclose(gross,retained*50)
    old,unused=model._future(draws,last,[24,25],10.)
    np.testing.assert_allclose(old[:,0],10*26/27)
    np.testing.assert_allclose(old[:,1],10*26/28)


def test_public_data_contract_has_no_generator_or_simulation_seed():
    from cohort_lab import data
    from lab import parser
    assert not hasattr(data,'generate_data') and not hasattr(data,'DEFAULT_SEED')
    with pytest.raises(SystemExit):parser().parse_args(['generate-data','--instructor'])
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'data/data_manifest.json').read_text())
    assert not {'synthetic_seed','retention_dgp','generator'}&set(manifest)
    assert manifest['dataset_version']=='3.0'
