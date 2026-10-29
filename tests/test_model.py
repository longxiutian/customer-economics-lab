import numpy as np
import pandas as pd
import pytest

from cohort_lab.model import _backtest, _future, _validate, _valuation_record, _economic_ratios, _valuation_backtest, cash_payback, discounted_value


def test_cash_and_discounting_use_different_clocks():
    flows=np.array([15.,10.,8.])
    assert discounted_value(flows,0)==33
    assert discounted_value(flows,.1)==pytest.approx(15/1.1+10/1.1**2+8/1.1**3)
    assert cash_payback(flows,26)==2
    assert cash_payback(flows,34) is None
    assert cash_payback(np.array([30.,-10.,15.]),25)==0


def test_net_value_subtracts_acquisition_once_and_uses_original_people():
    flows=np.tile([20.,30.,60.,0.,0.,0.,0.,0.,0.,0.,0.,0.],(400,1))
    record=_valuation_record(('2024-01-01',),2,80.,3,flows,np.arange(12)<3)
    before=(20/1.01+30/1.01**2+60/1.01**3)/2
    assert record['ltv_before_cac_mean']==pytest.approx(before)
    assert record['net_ltv_mean']==pytest.approx(before-40)
    assert record['ltv_to_cac_mean']==pytest.approx(before/40)
    assert record['payback_month']==3 and record['payback_age']==2
    assert record['payback_status']=='observed'
    assert record['forecast_share']==pytest.approx(0)


def test_unknown_organic_cost_is_not_free_acquisition():
    flows=np.ones((400,12))*20
    record=_valuation_record(('2024-01-01',),2,0.,12,flows,np.ones(12,dtype=bool),False)
    assert np.isnan(record['cac']) and np.isnan(record['net_ltv_mean'])
    assert record['payback_status']=='unsupported'
    assert record['payback_month'] is None


def test_first_crossing_is_distinguished_from_staying_recovered():
    flows=np.tile([30.,-10.,0.,0.,0.,0.,0.,0.,0.,0.,0.,0.],(400,1))
    record=_valuation_record(('2024-01-01',),1,25,12,flows,np.ones(12,dtype=bool))
    assert record['payback_month']==1 and record['payback_age']==0
    assert record['cash_payback_recrosses_below_cost'] is True
    assert record['p_expected_cash_balance_nonnegative_at_horizon']==0


def test_negative_value_does_not_produce_a_misleading_forecast_percentage():
    record=_valuation_record(('2024-01-01',),1,25,12,-np.ones((400,12)),np.ones(12,dtype=bool))
    assert np.isnan(record['forecast_share'])


def test_payback_status_boundary_uses_age_but_reports_receipt_number():
    flows=np.tile([10.,10.,10.,0.,0.,0.,0.,0.,0.,0.,0.,0.],(400,1))
    observed=_valuation_record(('2024-01-01',),1,25,3,flows,np.arange(12)<3)
    forecast=_valuation_record(('2024-01-01',),1,25,2,flows,np.arange(12)<2)
    assert observed['payback_month']==forecast['payback_month']==3
    assert observed['payback_age']==forecast['payback_age']==2
    assert observed['payback_status']=='observed' and forecast['payback_status']=='forecast'


def frame_fixture():
    records=[]
    for ci in range(3):
        for age in range(8-ci):
            n=100-age*8
            records.append(dict(cohort_month=f'2024-{ci+1:02d}-01',cohort_index=ci,age_month=age,
                calendar_month=f'2024-{ci+age+1:02d}-01',channel='search',primary_need='save_time',
                n_acquired=100,n_retained=n,gross_payment_revenue=n*50,net_revenue=n*49,contribution=n*20))
    return pd.DataFrame(records)


@pytest.mark.parametrize('mutation',['duplicate','increasing_survival','changing_denominator','missing_age'])
def test_invalid_retention_panels_fail(mutation):
    f=frame_fixture()
    if mutation=='duplicate': f=pd.concat([f,f.iloc[:1]])
    elif mutation=='increasing_survival': f.loc[2,'n_retained']=99
    elif mutation=='changing_denominator': f.loc[2,'n_acquired']=105
    elif mutation=='missing_age': f=f.drop(index=2)
    with pytest.raises(ValueError): _validate(f)


def constant_draws():
    h=np.zeros((400,5)); h[:,0]=np.log(.2/.8)
    c=np.zeros((400,4)); c[:,0]=np.log(4.)
    r=np.zeros((400,6)); r[:,0]=np.log(.5)
    return {'mean_beta':h,'concentration_beta':c,'cohort_scale':np.zeros(400),'cohort_z':np.zeros((400,24)),
            'revenue_beta':r,'revenue_shape':np.full(400,4.)}


def test_forecast_starts_at_last_observed_remaining_count():
    f=frame_fixture().iloc[0]
    retained,revenue=_future(constant_draws(),f,[3,4],80)
    expected=80*np.cumprod(1-.8/(4+np.array([3,4])-1))
    np.testing.assert_allclose(retained[0],expected)
    np.testing.assert_allclose(revenue[0],expected*50)


def test_forecast_economics_preserve_age_specific_margins():
    f=frame_fixture()
    f['net_revenue']=f.gross_payment_revenue
    f['contribution']=f.gross_payment_revenue*np.where(f.age_month==0,.1,.5)
    net,margin=_economic_ratios(f,f.iloc[0],[1,2,11])
    np.testing.assert_allclose(net,[1,1,1])
    np.testing.assert_allclose(margin,[.5,.5,.5])


def test_zero_revenue_retained_cell_is_rejected_instead_of_silently_dropped():
    f=frame_fixture();f.loc[1,'gross_payment_revenue']=0
    with pytest.raises(ValueError,match='zero payment'): _validate(f)


def test_source_style_cash_arithmetic_uses_original_acquired_customers():
    for n,cac,cumulative,wanted in [(100,50,3375,-16.25),(160,40,6936,3.35)]:
        assert (cumulative-n*cac)/n==pytest.approx(wanted)


def test_chronological_backtest_does_not_condition_on_held_out_survivors(monkeypatch):
    seen=[]
    def fake_fit(train,seed,steps):
        seen.append(train.copy())
        return constant_draws(),{}
    monkeypatch.setattr('cohort_lab.model._posterior',fake_fit)
    f=frame_fixture()
    b1,s1=_backtest(f,12,200)
    cutoff=s1['training_last_calendar_month']
    changed=f.copy()
    changed.loc[changed.calendar_month>cutoff,'n_retained']=1
    changed.loc[changed.calendar_month>cutoff,'gross_payment_revenue']=999999
    b2,_=_backtest(changed,12,200)
    assert all((x.calendar_month<=cutoff).all() for x in seen)
    np.testing.assert_array_equal(b1.pred_retained,b2.pred_retained)
    np.testing.assert_array_equal(b1.pred_revenue,b2.pred_revenue)
    assert not b1.actual_revenue.equals(b2.actual_revenue)


def test_year_end_ltv_backtest_uses_only_training_economics(monkeypatch):
    monkeypatch.setattr('cohort_lab.model._posterior',lambda *a,**kw:(constant_draws(),{}))
    records=[]
    for ci in range(12):
        for age in range(24-ci):
            n=max(1,100-age*4)
            records.append(dict(cohort_month=str(pd.Timestamp('2024-01-01')+pd.DateOffset(months=ci))[:10],cohort_index=ci,age_month=age,
                calendar_month=str(pd.Timestamp('2024-01-01')+pd.DateOffset(months=ci+age))[:10],
                channel='search',primary_need='save_time',n_acquired=100,n_retained=n,
                gross_payment_revenue=n*50,net_revenue=n*49,contribution=n*20))
    f=pd.DataFrame(records)
    costs=pd.DataFrame({'cohort_month':sorted(f.cohort_month.unique()),'acquisition_spend':[5000]*12,'n_acquired':[100]*12}).set_index('cohort_month')
    before,summary=_valuation_backtest(f,costs,1,200)
    f.loc[f.calendar_month>summary['training_last_calendar_month'],'contribution']=-99999
    after,_=_valuation_backtest(f,costs,1,200)
    np.testing.assert_array_equal(before.pred_net_ltv,after.pred_net_ltv)
    assert not before.actual_net_ltv.equals(after.actual_net_ltv)
    expected=before[before.actual_payback_month>before.observed_months_at_origin]
    assert summary['n_payback_after_origin']==len(expected)
    assert summary['n_payback_after_origin']+summary['n_payback_already_observed']==len(before)
    assert 'forecast_tail_value_wape' in summary

