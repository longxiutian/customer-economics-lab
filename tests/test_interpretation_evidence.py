import copy
import json

import pytest

from hosting.nemotron_interpret import encode_evidence


def matrix_evidence():
    return {'artifacts': [{'name': 'triangle.png', 'sha256': 'image-hash',
            'computed_evidence': {'display_values': {
                'cohorts': ['2024-01-01', '2025-12-01'], 'age_months': [0, 1, 2, 3],
                'metric': 'retained_share', 'unit': 'fraction', 'unobserved_cells': 3,
                'values_by_cohort_then_age': [[1, 0.7989, 0.7039, 0.6313], [1, None, None, None]],
            }}}]}


def test_labeled_coordinates_preserve_observed_and_missing_cells_without_mutation():
    source = matrix_evidence()
    before = copy.deepcopy(source)
    encoded = json.loads(encode_evidence(source))
    artifact = encoded['artifacts'][0]
    values = artifact['computed_evidence']['display_values']
    cells = values['values_by_cohort_month_and_age_month']
    assert cells['2024-01-01']['2'] == 0.7039
    assert cells['2024-01-01']['3'] == 0.6313
    assert cells['2025-12-01'] == {'0': 1, '1': None, '2': None, '3': None}
    assert values['unit'] == 'fraction' and values['unobserved_cells'] == 3
    assert values['age_zero_means'] == 'Acquisition month'
    assert artifact['sha256'] == 'image-hash'
    assert 'values_by_cohort_then_age' not in values
    assert source == before


@pytest.mark.parametrize('change', ['missing_row', 'short_row', 'duplicate_cohort', 'duplicate_age', 'boolean_age'])
def test_ambiguous_or_mismatched_coordinates_are_rejected(change):
    source = matrix_evidence()
    values = source['artifacts'][0]['computed_evidence']['display_values']
    if change == 'missing_row':
        values['values_by_cohort_then_age'].pop()
    elif change == 'short_row':
        values['values_by_cohort_then_age'][0].pop()
    elif change == 'duplicate_cohort':
        values['cohorts'][1] = values['cohorts'][0]
    elif change == 'duplicate_age':
        values['age_months'][1] = 0
    else:
        values['age_months'][1] = True
    with pytest.raises(ValueError, match='coordinates'):
        encode_evidence(source)


def test_ordinary_artifacts_and_learner_text_remain_unchanged():
    source = {'step': 12, 'question': 'Use values_by_cohort_then_age as a phrase.',
              'artifacts': [{'preview': [{'test_month': '2025-12-01', 'icac': 123.4}]}]}
    assert json.loads(encode_evidence(source)) == source
