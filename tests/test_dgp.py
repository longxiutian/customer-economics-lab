"""Behavioral tests for persistent customer heterogeneity and monthly observation.

The model is intentionally not consulted here: these tests establish source
data mechanics, not that an inference model can recover its own generator.
"""
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from cohort_lab.data import (
    CHURN_COMPONENTS, DATASET_VERSION, DISRUPTION_CHURN_ODDS_MULTIPLIER,
    SCHEMAS, churn_mixture_spec, generate_data, renewal_probability,
    sample_churn_propensity, validate_data,
)


def _read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _beta_survival(alpha, beta, age):
    """Independent analytical integration of E[(1-theta)**age]."""
    return math.exp(math.lgamma(beta + age) - math.lgamma(alpha + beta + age)
                    + math.lgamma(alpha + beta) - math.lgamma(beta))


def test_beta_reference_and_mixture_survivor_selection():
    # Lee/Fader/Hardie's published parameter example, evaluated independently.
    alpha, beta = 1.08, 3.67
    assert _beta_survival(alpha, beta, 0) == pytest.approx(1)
    assert _beta_survival(alpha, beta, 1) == pytest.approx(beta / (alpha + beta))
    spec = churn_mixture_spec(0, "save_time", "search")
    weight = spec["fragile_weight"]
    s = np.asarray([(1-weight)*_beta_survival(*spec["durable"], t)
                    + weight*_beta_survival(*spec["fragile"], t) for t in range(25)])
    hazard = 1-s[1:]/s[:-1]
    assert (np.diff(s) < 0).all()
    assert (np.diff(hazard) < 0).all()
    assert hazard[-1] < hazard[0] / 3
    # No individual's theta changed; the aggregate hazard fell by selection.


def test_propensity_samples_match_mixture_moments_and_retain_variance():
    rng = random.Random(83921)
    spec = churn_mixture_spec(12, "build_skill", "partner")
    w = spec["fragile_weight"]
    means = [a/(a+b) for a, b in [spec["durable"], spec["fragile"]]]
    seconds = [a*(a+1)/((a+b)*(a+b+1)) for a, b in [spec["durable"], spec["fragile"]]]
    mean = (1-w)*means[0] + w*means[1]
    variance = (1-w)*seconds[0] + w*seconds[1] - mean**2
    theta = np.asarray([sample_churn_propensity(rng, 12, "build_skill", "partner") for _ in range(60000)])
    assert theta.mean() == pytest.approx(mean, abs=.002)
    assert theta.var() == pytest.approx(variance, abs=.001)
    assert theta.var() > .01  # Observable segments do not remove individual heterogeneity.
    assert ((theta > 0) & (theta < 1)).all()


def test_monthly_probability_reuses_propensity_and_only_calendar_shock_changes_it():
    theta = .2
    ordinary = [renewal_probability(theta, month) for month in [1, 2, 13, 16, 23]]
    assert ordinary == pytest.approx([.8]*5)
    q = 1-renewal_probability(theta, 14)
    assert q/(1-q) == pytest.approx(DISRUPTION_CHURN_ODDS_MULTIPLIER*theta/(1-theta))
    assert renewal_probability(theta, 15) == renewal_probability(theta, 14)
    assert renewal_probability(0, 14) == 1
    assert renewal_probability(1, 14) == 0


def test_generator_draws_one_latent_propensity_per_acquired_person(tmp_path, monkeypatch):
    import cohort_lab.data as module
    original = module.sample_churn_propensity
    draws = []

    def counted(rng, cohort, need, channel):
        theta = original(rng, cohort, need, channel)
        draws.append(theta)
        return theta

    monkeypatch.setattr(module, "sample_churn_propensity", counted)
    folder = tmp_path / "generated"
    manifest = generate_data(folder)
    result = validate_data(folder)
    assert len(draws) == result["acquired_people"]
    assert len(draws) < manifest["files"]["subscription_periods.csv"]["row_count"]
    assert manifest["dataset_version"] == DATASET_VERSION == "2.0"
    canonical = Path(__file__).resolve().parents[1] / "data"
    for path in sorted(folder.iterdir()):
        assert path.read_bytes() == (canonical/path.name).read_bytes(), path.name


def test_frozen_sources_have_24_monthly_cohorts_and_censoring_without_latent_leakage():
    folder = Path(__file__).resolve().parents[1] / "data"
    periods = _read(folder / "subscription_periods.csv")
    tx = {r["transaction_id"]: r for r in _read(folder / "transactions.csv")}
    attrs = _read(folder / "acquisition_attribution.csv")
    expected = {f"{year}-{month:02d}" for year in [2024, 2025] for month in range(1,13)}
    firsts = {a["person_id"]: tx[a["first_paid_transaction_id"]]["occurred_at"][:7] for a in attrs}
    assert set(firsts.values()) == expected
    histories = defaultdict(list)
    for row in periods:
        histories[row["person_id"]].append(row)
    assert set(histories) == set(firsts)
    for pid, history in histories.items():
        history.sort(key=lambda r: r["period_start"])
        assert history[0]["renewal_outcome"] == "paid"
        assert history[0]["period_start"][:7] == firsts[pid]
        assert all(r["renewal_outcome"] == "paid" for r in history[:-1])
        assert history[-1]["renewal_outcome"] in {"cancelled", "failed", "pending"}
        if history[-1]["renewal_outcome"] == "pending":
            assert history[-1]["period_start"][:7] == "2026-01"
        for left, right in zip(history, history[1:]):
            assert left["period_end"] == right["period_start"]
    assert any(r["renewal_outcome"] == "pending" for r in periods)
    assert all(r["renewal_outcome"] != "paid" or r["period_start"] < "2026-01-01" for r in periods)
    forbidden = {"theta", "latent_class", "component", "true_churn_probability", "frailty"}
    assert not any(forbidden & set(fields) for fields in SCHEMAS.values())


def test_cohort_and_observable_mix_are_distinct_mechanisms():
    # Same observed need/channel still contains a mixture and changes by entry month.
    first = churn_mixture_spec(0, "save_time", "search")
    last = churn_mixture_spec(23, "save_time", "search")
    other = churn_mixture_spec(0, "build_skill", "partner")
    assert 0 < last["fragile_weight"] < first["fragile_weight"] < 1
    assert other["fragile_weight"] < first["fragile_weight"]
    assert first["durable"] == last["durable"] == CHURN_COMPONENTS["durable"]
