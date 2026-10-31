"""Independent arithmetic and isolation checks for acquisition-only evidence."""
from pathlib import Path
import shutil
import pandas as pd
import duckdb
import pytest
from test_data_sql import _read,_write,_seal,hand_data
from cohort_lab.analysis import build_views

ROOT=Path(__file__).resolve().parents[1]

def calculated(bt=20,bc=5):
    con=duckdb.connect()
    con.execute("""CREATE TABLE channel_holdouts AS SELECT * FROM (VALUES
      ('x','search','save_time',TIMESTAMP '2025-07-01',TIMESTAMP '2025-08-01','treatment',100,?,250.0,50.0),
      ('x','search','save_time',TIMESTAMP '2025-07-01',TIMESTAMP '2025-08-01','control',50,?,15.0,5.0))
      t(test_id,channel,primary_need,assigned_at,followup_end_at,arm,n_assigned,n_buyers,media_spend,other_acquisition_spend)""",[bt,bc])
    sql=(ROOT/'sql/01_views.sql').read_text(encoding='utf-8')
    con.execute('CREATE OR REPLACE VIEW channel_cac AS'+sql.split('CREATE OR REPLACE VIEW channel_cac AS',1)[1])
    result=con.execute('SELECT * FROM channel_cac').df().iloc[0];con.close();return result

def test_unequal_arms_scale_both_background_and_costs():
    r=calculated()
    assert r.expected_background_buyers==10 and r.incremental_buyers==10
    assert r.incremental_spend==260 and r.credited_cac==15 and r.icac==26
    assert r.incremental_buyers_se==pytest.approx(100*(.2*.8/100+.1*.9/50)**.5)

def test_weak_or_nonpositive_lift_does_not_invent_finite_bound():
    assert pd.isna(calculated(bt=11).icac_ci_upper)
    assert pd.isna(calculated(bt=10).icac)
    assert pd.isna(calculated(bt=8).icac)

def test_pilot_changes_cannot_change_customer_model_or_accounting_inputs(hand_data,tmp_path):
    first=tmp_path/'first';second=tmp_path/'second';build_views(hand_data,first)
    rows=_read(hand_data/'channel_holdouts.csv')
    rows[0].update(n_assigned='100',n_buyers='50',media_spend='99999.00',other_acquisition_spend='500.00')
    _write(hand_data,'channel_holdouts.csv',rows);_seal(hand_data)
    build_views(hand_data,second)
    for name in ['customer_month','cohort_age_summary','cohort_acquisition_costs','cohort_cash_economics','company_totals','friction_subjects','segmentation_profile']:
        assert (first/'tables'/f'{name}.csv').read_bytes()==(second/'tables'/f'{name}.csv').read_bytes()
    assert (first/'tables/channel_cac.csv').read_bytes()!=(second/'tables/channel_cac.csv').read_bytes()

def test_legacy_sources_are_absent_and_pilots_have_no_customer_link():
    from cohort_lab.data import SCHEMAS
    assert 'experiment_assignments.csv' not in SCHEMAS
    assert not (ROOT/'data/experiment_assignments.csv').exists()
    assert not {'person_id','contribution','net_revenue','retained'} & set(SCHEMAS['channel_holdouts.csv'])
    for name in ['people.csv','transactions.csv','subscription_periods.csv','product_events.csv','feedback.csv','acquisition_attribution.csv']:
        assert not pd.read_csv(ROOT/'data'/name).person_id.str.startswith('PX').any()
    assert not pd.read_csv(ROOT/'data/campaign_spend.csv').campaign_id.str.startswith('TEST-').any()
