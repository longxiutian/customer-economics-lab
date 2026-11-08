import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from cohort_lab.challenge import validate_predictions
from scripts.create_challenge_repository import create

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('submission_example',ROOT/'challenge/template/main.py')
example=importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


@pytest.fixture(scope='module')
def inputs():
    contract=json.loads((ROOT/'challenge/submission-contract.json').read_text())
    return example.load_tables(ROOT/'data',contract),pd.read_csv(ROOT/'challenge/prediction_grid.csv')


def test_real_eight_table_example_is_reproducible_and_preserves_inputs(inputs):
    tables,grid=inputs
    before={k:v.copy(deep=True) for k,v in tables.items()}
    original_grid=grid.copy(deep=True)
    first=example.predict(tables,grid,seed=20261116)
    second=example.predict(tables,grid,seed=20261116)
    pd.testing.assert_frame_equal(first,second)
    checked=validate_predictions(first,grid)
    assert len(checked)==1152
    assert checked.predicted_contribution.sum()>0
    assert checked.predicted_retained.max()<=grid.origin_retained.max()
    for name in before:pd.testing.assert_frame_equal(tables[name],before[name])
    pd.testing.assert_frame_equal(grid,original_grid)


def test_future_transactions_are_rejected(inputs):
    tables,grid=inputs
    altered={k:v.copy(deep=True) for k,v in tables.items()}
    altered['transactions'].loc[0,'occurred_at']='2026-02-01 00:00:00'
    with pytest.raises(ValueError,match='after the forecast origin'):
        example.predict(altered,grid,seed=20261116)


def test_template_validator_rejects_omitted_grid_rows(inputs):
    tables,grid=inputs
    predictions=example.predict(tables,grid,seed=20261116)
    with pytest.raises(AssertionError):
        example.validate_output(predictions.iloc[1:],grid)


def test_scaffold_is_separate_complete_and_does_not_overwrite(tmp_path):
    with pytest.raises(ValueError,match='outside'):
        create(ROOT/'outputs/team')
    destination=tmp_path/'team'
    receipt=create(destination)
    assert not receipt['published'] and not receipt['lesson_advanced']
    assert {'main.py','uv.lock','pyproject.toml','submission-contract.json','prediction_grid.csv'}<=set(receipt['files'])
    (destination/'main.py').write_text('student work')
    with pytest.raises(ValueError,match='existing work'):
        create(destination)
    assert (destination/'main.py').read_text()=='student work'
