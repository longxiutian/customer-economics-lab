"""Exhibits needed before the PDF must not depend on compiling that PDF."""
from pathlib import Path
import pandas as pd
from cohort_lab.holdout_report import add_holdout_chart
from cohort_lab.report_b import prepare_incremental_cash_chart

def test_six_wave_chart_needs_only_acquisition_history(tmp_path):
    tables=tmp_path/'tables';tables.mkdir()
    rows=[]
    for month in range(7,13):
        for channel in ('search','partner'):
            for need in ('save_time','build_skill'):
                rows.append(dict(test_id=f'{month}-{channel}-{need}',test_month=f'2025-{month:02}-01',
                    followup_end_at=f'2025-{month:02}-28',channel=channel,primary_need=need,icac=400-month*10))
    pd.DataFrame(rows).to_csv(tables/'channel_cac.csv',index=False)
    charts={'sources':{},'figures':{}}
    add_holdout_chart(tmp_path,charts)
    assert (tmp_path/'report/figures/channel-icac-history.png').stat().st_size>1000
    assert len(charts['figures']['channel-icac-history']['display_values'])==24
    assert not (tmp_path/'model_manifest.json').exists()
    assert not (tmp_path/'report/customer-economics-report.pdf').exists()

def test_value_cash_exhibit_exists_without_report_compilation(tmp_path):
    tables=tmp_path/'tables';tables.mkdir()
    values=[];cells=[];paths=[]
    for i,(channel,need) in enumerate([('search','save_time'),('search','build_skill'),('partner','save_time'),('partner','build_skill')]):
        key=dict(cohort_month='2025-07-01',channel=channel,primary_need=need)
        values.append(dict(**key,test_id=str(i),icac=100+i*10,ltv_before_cac_mean=240,
                           value_less_icac=140-i*10,horizon_months=12))
        cells.append(dict(**key,cac=70,payback_month=4))
        for age in range(12):paths.append(dict(**key,age_month=age,cash_after_cac_mean=20*(age+1)-70,observed=age<6))
    for name,rows in [('channel_value_decision.csv',values),('strategic_segment_breakout.csv',cells),('segment_forecast_curves.csv',paths)]:
        pd.DataFrame(rows).to_csv(tables/name,index=False)
    charts={'sources':{},'figures':{}}
    plan=prepare_incremental_cash_chart(tmp_path,charts)
    assert len(plan)==4 and plan.planning_payback_receipt.notna().all()
    assert (tmp_path/'report/figures/incremental-cash-paths.png').stat().st_size>1000
    assert not (tmp_path/'report/customer-economics-report.pdf').exists()
