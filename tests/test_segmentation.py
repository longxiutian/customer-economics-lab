"""Independent arithmetic for a fair, descriptive segmentation comparison."""
from pathlib import Path
import duckdb
import pytest


def test_equal_customer_sample_and_cohort_centered_variance():
    con=duckdb.connect(':memory:')
    con.execute("CREATE TABLE lab_settings AS SELECT TIMESTAMP '2026-01-01' AS data_as_of")
    con.execute("CREATE TABLE acquired_customers(person_id VARCHAR,cohort_month DATE,channel VARCHAR,primary_need VARCHAR,age_band VARCHAR,region VARCHAR)")
    con.execute("CREATE TABLE customer_month(person_id VARCHAR,age_month INTEGER,contribution DOUBLE,retained INTEGER)")
    con.execute("CREATE TABLE experiment_assignments(person_id VARCHAR)")
    for cohort,shift in [('2024-01-01',0),('2025-01-01',100)]:
        for i,value in enumerate([10.,10.,30.,30.]):
            pid=f'{cohort}-{i}'
            con.execute('INSERT INTO acquired_customers VALUES (?,?,?,?,?,?)',[pid,cohort,'search' if i%2 else 'partner','save_time' if i<2 else 'build_skill','young' if i%2 else 'older','east' if i%2 else 'west'])
            con.executemany('INSERT INTO customer_month VALUES (?,?,?,?)',[(pid,age,value+shift if age==0 else 0,0 if i<2 else 1) for age in range(6)])
    for pid,channel in [('experimental','search'),('organic','organic')]:
        con.execute("INSERT INTO acquired_customers VALUES (?,'2024-01-01',?,'save_time','young','east')",[pid,channel])
        con.executemany('INSERT INTO customer_month VALUES (?,?,?,?)',[(pid,age,10000,1) for age in range(6)])
    con.execute("INSERT INTO experiment_assignments VALUES ('experimental')")
    text=(Path(__file__).resolve().parents[1]/'sql/01_views.sql').read_text()
    part='CREATE OR REPLACE VIEW segmentation_subjects AS'+text.split('CREATE OR REPLACE VIEW segmentation_subjects AS',1)[1].split('CREATE OR REPLACE VIEW cohort_totals AS',1)[0]
    con.execute(part)
    records=con.execute('SELECT scheme,n_customers,n_groups,pooled_variance,weighted_within_variance,variance_reduction,cohort_centered_variance_reduction FROM segmentation_comparison').fetchall()
    assert len(records)==4
    for scheme,n,k,pooled,within,reduction,centered in records:
        assert n==8 and k==2
        assert pooled==pytest.approx(2600)
        if scheme=='primary_need':
            assert within==pytest.approx(2500)
            assert reduction==pytest.approx(1-2500/2600)
            assert centered==pytest.approx(1)
        else:
            assert within==pytest.approx(2600)
            assert centered==pytest.approx(0)
    # Nonrenewing customers remain in the original denominator with later zeros.
    need=con.execute("SELECT n,mean_contribution,retained_share FROM segmentation_profile WHERE scheme='primary_need' AND segment='save_time'").fetchone()
    assert need==pytest.approx((4,60,0))
    con.close()


def test_within_group_retention_excludes_treatment_and_control_buyers():
    con=duckdb.connect(':memory:')
    con.execute('CREATE TABLE customer_month(person_id VARCHAR,cohort_month DATE,channel VARCHAR,primary_need VARCHAR,age_month INTEGER,retained INTEGER)')
    con.execute('CREATE TABLE experiment_assignments(person_id VARCHAR,arm VARCHAR)')
    for pid,retained in [('regular1',1),('regular2',0),('treated',1),('control',1)]:
        con.execute("INSERT INTO customer_month VALUES (?,'2025-05-01','search','save_time',5,?)",[pid,retained])
    con.execute("INSERT INTO experiment_assignments VALUES ('treated','treatment'),('control','control')")
    text=(Path(__file__).resolve().parents[1]/'sql/01_views.sql').read_text()
    con.execute('CREATE OR REPLACE VIEW cohort_age_ex_tests AS'+text.split('CREATE OR REPLACE VIEW cohort_age_ex_tests AS',1)[1])
    row=con.execute('SELECT n_acquired,n_retained,retained_share FROM cohort_age_ex_tests').fetchone()
    assert row==pytest.approx((2,1,.5))
    con.close()
