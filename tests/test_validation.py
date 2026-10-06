"""The overfitting tests, on cases whose answer is known."""

import math

import numpy as np
import pytest

from osloquant.research.validation import (
    backtest_overfitting,
    bootstrap_mean,
    deflated_sharpe,
    effective_trials,
    expected_max_sharpe,
    probabilistic_sharpe,
    sharpe,
)


def test_sharpe_and_its_probability_for_normal_returns():
    rng = np.random.default_rng(0)
    skilled = rng.normal(0.01, 0.05, 2000)  # a per-period Sharpe of 0.2, seen 2 000 times
    assert sharpe(skilled) == pytest.approx(0.2, abs=0.03)
    assert probabilistic_sharpe(skilled) > 0.999
    noise = rng.normal(0.0, 0.05, 2000)
    assert 0.05 < probabilistic_sharpe(noise) < 0.95  # no skill: the probability lands anywhere in between
    assert math.isnan(sharpe(np.ones(10)))  # no variation, no ratio


def test_the_expected_best_of_many_matches_the_paper_and_simulation():
    # with one trial there is nothing to deflate; with more, the hurdle grows with the spread of the trials
    assert expected_max_sharpe(1, 0.04) == 0.0
    assert expected_max_sharpe(10, 0.04) < expected_max_sharpe(100, 0.04) < expected_max_sharpe(1000, 0.04)
    # simulate: the best of 100 skill-free strategies with Sharpe ratios spread N(0, 0.1)
    rng = np.random.default_rng(1)
    best = rng.normal(0, 0.1, (20000, 100)).max(axis=1).mean()
    assert expected_max_sharpe(100, 0.01) == pytest.approx(best, rel=0.03)


def test_the_best_of_many_noise_strategies_is_not_called_skilled():
    # 100 times over: twenty years of months, 200 strategies, none with skill, and the best one picked
    rng = np.random.default_rng(2)
    undeflated, deflated, best, hurdles = [], [], [], []
    for _ in range(100):
        trials = rng.normal(0, 0.01, (240, 200))
        sharpes = trials.mean(axis=0) / trials.std(axis=0, ddof=1)
        pick = int(np.argmax(sharpes))
        result = deflated_sharpe(trials[:, pick], trials=200)
        undeflated.append(probabilistic_sharpe(trials[:, pick]))
        deflated.append(result["dsr"])
        best.append(sharpes[pick])
        hurdles.append(result["hurdle"])
    assert np.mean(np.array(undeflated) > 0.95) > 0.95  # on its own the winner nearly always looks convincing
    assert np.mean(np.array(deflated) > 0.95) < 0.05  # deflated, it nearly never does
    assert np.mean(hurdles) == pytest.approx(np.mean(best), rel=0.05)  # the hurdle is where the best of noise lands


def test_a_real_edge_survives_deflation():
    rng = np.random.default_rng(3)
    trials = rng.normal(0, 0.01, (240, 50))
    trials[:, 7] += 0.006  # one strategy with a per-period Sharpe of about 0.6
    sharpes = np.array([sharpe(trials[:, i]) for i in range(50)])
    assert int(np.argmax(sharpes)) == 7
    assert deflated_sharpe(trials[:, 7], trials=50)["dsr"] > 0.99


def test_correlated_trials_count_for_less():
    rng = np.random.default_rng(6)
    base = rng.normal(0, 0.01, (240, 1))
    assert effective_trials(np.repeat(base, 24, axis=1)) == pytest.approx(1.0)  # the same strategy 24 times
    assert effective_trials(rng.normal(0, 0.01, (240, 24))) == pytest.approx(24, rel=0.05)  # 24 unrelated ones
    similar = base + rng.normal(0, 0.01, (240, 24))  # correlation about one half
    assert 9 < effective_trials(similar) < 16
    flat = np.column_stack([rng.normal(0, 0.01, (240, 3)), np.zeros(240)])  # a strategy that never traded
    assert effective_trials(flat) == pytest.approx(4, rel=0.1)


def test_pbo_is_high_for_noise_and_low_for_a_persistent_edge():
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 0.01, (320, 20))
    overfit = backtest_overfitting(noise, blocks=8)
    assert overfit.splits == math.comb(8, 4)
    assert 0.3 < overfit.pbo < 0.7  # picking the best of noise is a coin flip out of sample
    assert overfit.degradation < 0.3  # and keeps little of its in-sample Sharpe

    persistent = noise.copy()
    persistent[:, 3] += 0.004
    sound = backtest_overfitting(persistent, blocks=8)
    assert sound.pbo < 0.05 and sound.probability_of_loss < 0.05


def test_pbo_refuses_what_it_cannot_judge():
    with pytest.raises(ValueError, match="even"):
        backtest_overfitting(np.zeros((100, 3)), blocks=5)
    with pytest.raises(ValueError, match="at least two"):
        backtest_overfitting(np.zeros((100, 1)), blocks=4)
    with pytest.raises(ValueError, match="too few"):
        backtest_overfitting(np.zeros((10, 3)), blocks=8)


def test_bootstrap_interval_covers_the_true_mean_and_says_when_it_is_not_positive():
    rng = np.random.default_rng(5)
    positive = rng.normal(0.01, 0.03, 240)
    result = bootstrap_mean(positive, samples=1000)
    assert result["low"] < 0.01 < result["high"] and result["p_not_positive"] < 0.01
    zero = rng.normal(0.0, 0.03, 240)
    assert 0.05 < bootstrap_mean(zero, samples=1000)["p_not_positive"] < 0.95
    assert bootstrap_mean(positive, samples=200, seed=1) == bootstrap_mean(positive, samples=200, seed=1)  # repeatable
