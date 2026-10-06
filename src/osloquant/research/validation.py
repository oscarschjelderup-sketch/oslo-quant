"""Telling an edge from luck.

Three tests, each answering a question a backtest by itself cannot:

``deflated_sharpe``     Bailey & López de Prado (2014), "The Deflated Sharpe Ratio". How likely is it that the true
                        Sharpe ratio is above zero, given that the best of N tried strategies was picked? With many
                        tries the best one looks good by chance alone; this charges for that.
``backtest_overfitting``  Bailey, Borwein, López de Prado & Zhu (2017), "The Probability of Backtest Overfitting",
                        by combinatorially symmetric cross-validation (CSCV). Split the history into blocks, pick the
                        best configuration on half of them, and see where it ranks on the other half. Done for every
                        way of halving: the share of splits in which the pick lands in the bottom half is the PBO.
``bootstrap_mean``      A stationary block bootstrap (Politis & Romano 1994) of a mean return, for an interval that
                        respects the clustering of returns in time.

Only the standard library and numpy: the normal distribution comes from ``statistics.NormalDist``.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def sharpe(returns: np.ndarray) -> float:
    """Per-period Sharpe ratio (mean over standard deviation, no annualising)."""
    returns = np.asarray(returns, dtype=float)
    returns = returns[~np.isnan(returns)]
    if len(returns) < 2:
        return float("nan")
    sd = returns.std(ddof=1)
    return float(returns.mean() / sd) if sd > 0 else float("nan")


def expected_max_sharpe(trials: int, variance: float) -> float:
    """The Sharpe ratio the best of ``trials`` strategies is expected to show when none has any skill.

    ``variance`` is the variance of the per-period Sharpe ratios across the trials (eq. 6 of the paper).
    """
    if trials < 2 or variance <= 0:
        return 0.0
    return math.sqrt(variance) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / trials) + EULER_GAMMA * _N.inv_cdf(1 - 1 / (trials * math.e)))


def probabilistic_sharpe(returns: np.ndarray, benchmark: float = 0.0) -> float:
    """Probability that the true per-period Sharpe ratio exceeds ``benchmark``, allowing for skew and fat tails."""
    returns = np.asarray(returns, dtype=float)
    returns = returns[~np.isnan(returns)]
    n = len(returns)
    if n < 3:
        return float("nan")
    sr = sharpe(returns)
    centred = returns - returns.mean()
    sd = returns.std(ddof=0)
    skew = float((centred**3).mean() / sd**3)
    kurtosis = float((centred**4).mean() / sd**4)  # 3 for a normal distribution
    denominator = 1 - skew * sr + (kurtosis - 1) / 4 * sr**2
    if denominator <= 0:
        return float("nan")
    return _N.cdf((sr - benchmark) * math.sqrt(n - 1) / math.sqrt(denominator))


def effective_trials(trial_returns: np.ndarray) -> float:
    """How many independent trials a set of correlated ones is worth: rho + (1 - rho) M, with M trials whose
    returns have an average pairwise correlation of rho (Bailey & López de Prado 2014, section 3).

    Twenty-four settings of one momentum strategy are not twenty-four chances to be lucky.
    """
    matrix = np.asarray(trial_returns, dtype=float)
    matrix = matrix[~np.isnan(matrix).any(axis=1)]
    trials = matrix.shape[1]
    if trials < 2:
        return float(trials)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(matrix.T)
    # a trial that never moved has no correlation with anything; it counts as independent
    off_diagonal = corr[~np.eye(trials, dtype=bool)]
    rho = float(np.nanmean(off_diagonal)) if np.isfinite(off_diagonal).any() else 0.0
    rho = float(np.clip(rho, 0.0, 1.0))
    return rho + (1 - rho) * trials


def deflated_sharpe(returns: np.ndarray, trials: float, variance: float | None = None) -> dict:
    """The deflated Sharpe ratio of ``returns``, picked as the best of ``trials`` (independent) strategies.

    The hurdle is the Sharpe ratio the best of that many skill-free strategies would be expected to show.
    ``variance`` is the variance of their Sharpe ratios; by default 1 / (T - 1), the sampling variance of an
    estimated Sharpe ratio whose true value is zero. (The paper also allows the variance across the trials
    actually run; that overstates it when the trials include opposite strategies, such as momentum and reversal.)

    Returns the probability that the strategy has skill, and the hurdle its Sharpe ratio was measured against.
    """
    returns = np.asarray(returns, dtype=float)
    returns = returns[~np.isnan(returns)]
    if variance is None:
        variance = 1.0 / max(len(returns) - 1, 1)
    hurdle = expected_max_sharpe(max(int(round(trials)), 1), variance)
    return {"dsr": probabilistic_sharpe(returns, hurdle), "sharpe": sharpe(returns), "hurdle": hurdle, "trials": float(trials)}


@dataclass
class OverfittingResult:
    #: the probability of backtest overfitting: the share of splits where the in-sample best is in the bottom half out of sample
    pbo: float
    splits: int
    #: per split: the in-sample best's Sharpe in sample and out of sample
    in_sample_sharpe: np.ndarray
    out_of_sample_sharpe: np.ndarray
    #: per split: logit of the in-sample best's relative rank out of sample (> 0: above the median)
    logits: np.ndarray

    @property
    def degradation(self) -> float:
        """How much of the in-sample Sharpe the pick keeps out of sample, on average (1: all of it)."""
        keep = self.out_of_sample_sharpe / np.where(self.in_sample_sharpe == 0, np.nan, self.in_sample_sharpe)
        return float(np.nanmedian(keep))

    @property
    def probability_of_loss(self) -> float:
        """The share of splits where the in-sample best lost money out of sample."""
        return float((self.out_of_sample_sharpe < 0).mean())


def backtest_overfitting(returns: np.ndarray, blocks: int = 16) -> OverfittingResult:
    """PBO by CSCV. ``returns`` is periods x configurations: one column per variant that was tried.

    The rows are cut into ``blocks`` contiguous blocks (an even number). For every way of choosing half of them as
    the in-sample set, the configuration with the best in-sample Sharpe is found and ranked out of sample.
    """
    matrix = np.asarray(returns, dtype=float)
    periods, configs = matrix.shape
    if blocks % 2 or blocks < 2:
        raise ValueError("blocks must be an even number of at least 2")
    if configs < 2:
        raise ValueError("overfitting can only be judged among at least two configurations")
    usable = periods - periods % blocks
    if usable < 2 * blocks:
        raise ValueError(f"{periods} periods are too few for {blocks} blocks")
    cut = matrix[periods - usable :].reshape(blocks, usable // blocks, configs)
    # the sums the Sharpe ratio of any union of blocks is made of
    sums, squares, counts = np.nansum(cut, axis=1), np.nansum(cut**2, axis=1), np.sum(~np.isnan(cut), axis=1)

    def sharpe_of(chosen: list[int]) -> np.ndarray:
        n, s, q = counts[chosen].sum(axis=0), sums[chosen].sum(axis=0), squares[chosen].sum(axis=0)
        mean = s / n
        sd = np.sqrt(np.maximum(q / n - mean**2, 0) * n / np.maximum(n - 1, 1))
        return np.where(sd > 0, mean / np.where(sd > 0, sd, 1), np.nan)

    in_best, out_best, logits = [], [], []
    everything = set(range(blocks))
    for chosen in itertools.combinations(range(blocks), blocks // 2):
        rest = sorted(everything - set(chosen))
        in_sharpes, out_sharpes = sharpe_of(list(chosen)), sharpe_of(rest)
        if np.all(np.isnan(in_sharpes)):
            continue
        best = int(np.nanargmax(in_sharpes))
        # relative rank out of sample: 1 is the best of the configurations, 1/(N+1) the worst
        valid = out_sharpes[~np.isnan(out_sharpes)]
        rank = float((valid < out_sharpes[best]).sum() + 1) if not np.isnan(out_sharpes[best]) else 1.0
        omega = rank / (len(valid) + 1)
        in_best.append(in_sharpes[best])
        out_best.append(out_sharpes[best])
        logits.append(math.log(omega / (1 - omega)))
    logits_array = np.array(logits)
    return OverfittingResult(
        pbo=float((logits_array <= 0).mean()),
        splits=len(logits),
        in_sample_sharpe=np.array(in_best),
        out_of_sample_sharpe=np.array(out_best),
        logits=logits_array,
    )


def bootstrap_mean(returns: np.ndarray, block: float = 3.0, samples: int = 5000, seed: int = 0) -> dict:
    """Stationary block bootstrap of the mean of ``returns``.

    Blocks have geometric lengths with mean ``block`` periods. Returns the 2.5 % and 97.5 % quantiles of the mean
    and the share of resamples whose mean is at or below zero.
    """
    returns = np.asarray(returns, dtype=float)
    returns = returns[~np.isnan(returns)]
    n = len(returns)
    if n < 2:
        return {"low": float("nan"), "high": float("nan"), "p_not_positive": float("nan")}
    rng = np.random.default_rng(seed)
    p = 1.0 / block
    means = np.empty(samples)
    for k in range(samples):
        index = np.empty(n, dtype=int)
        index[0] = rng.integers(n)
        starts = rng.random(n) < p
        jumps = rng.integers(n, size=n)
        for t in range(1, n):
            index[t] = jumps[t] if starts[t] else (index[t - 1] + 1) % n
        means[k] = returns[index].mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return {"low": float(low), "high": float(high), "p_not_positive": float((means <= 0).mean())}
