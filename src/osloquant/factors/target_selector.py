"""Combining factors into one list of targets."""

from __future__ import annotations

from enum import Enum

from osloquant.contract import TargetType
from osloquant.contract.factor import Factor


class SelectMode(Enum):
    #: long when every factor is positive, short when any factor is negative
    condition_and = "condition_and"
    #: long when any factor is positive, short when every factor is negative
    condition_or = "condition_or"


class TargetSelector:
    """Ask several factors at once.

    >>> selector = TargetSelector(factors=[AboveMaFactor(window=200), GoodCompanyFactor()])
    >>> selector.get_targets("2026-10-01")
    """

    def __init__(self, factors: list[Factor] | None = None, select_mode: SelectMode = SelectMode.condition_and) -> None:
        self.factors: list[Factor] = list(factors or [])
        self.select_mode = SelectMode(select_mode)

    def add_factor(self, factor: Factor) -> None:
        self.factors.append(factor)

    def _combine(self, sets: list[set[str]], every: bool) -> list[str]:
        if not sets:
            return []
        combined = set.intersection(*sets) if every else set.union(*sets)
        return sorted(combined)

    def get_targets(self, timestamp, target_type: TargetType = TargetType.positive) -> list[str]:
        target_type = TargetType(target_type)
        sets = [set(f.get_targets(timestamp, target_type)) for f in self.factors]
        every = (self.select_mode == SelectMode.condition_and) == (target_type == TargetType.positive)
        return self._combine(sets, every=every)

    def get_open_long_targets(self, timestamp) -> list[str]:
        return self.get_targets(timestamp, TargetType.positive)

    def get_open_short_targets(self, timestamp) -> list[str]:
        return self.get_targets(timestamp, TargetType.negative)
