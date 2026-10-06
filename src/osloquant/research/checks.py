"""Two automatic checks on a factor, after freqtrade's ``lookahead-analysis`` and ``recursive-analysis``.

``lookahead_check``  Compute the factor on all the data, then again on the data up to each of a few dates, and
                     compare what the two say about that date. If the verdict on a day changes when later days are
                     added, the factor looked ahead, and every backtest built on it is worthless.
``warmup_check``     Compute the factor for one date with less and less history before it. An exponential average
                     never forgets where it started, so its value, and sometimes the verdict, depends on how much
                     history was loaded. A live account loads a fixed amount, so this says whether that is enough.

Neither reads the factor's code: they only compare what it returns, so they work on any factor, written by
anyone, and catch the mistakes a reading misses (a centred rolling window, a ``shift(-1)``, a fit on the whole
sample).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from osloquant.contract.factor import Factor

RESULT_COLUMNS = ("filter_result", "score_result")


def _row(frame: pd.DataFrame | None, day: pd.Timestamp) -> pd.DataFrame:
    if frame is None or frame.empty or day not in frame.index.get_level_values("timestamp"):
        return pd.DataFrame()
    return frame.xs(day, level="timestamp")


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.select_dtypes(include=[np.number, "boolean", bool])


def _differences(a: pd.DataFrame, b: pd.DataFrame, tolerance: float) -> list[tuple[str, str, object, object]]:
    """(entity, column, value in a, value in b) wherever two frames for the same day disagree."""
    found = []
    for column in sorted(set(a.columns) & set(b.columns)):
        joined = pd.concat([a[column].rename("a"), b[column].rename("b")], axis=1)
        for entity, x, y in joined.itertuples():
            if pd.isna(x) and pd.isna(y):
                continue
            if pd.isna(x) or pd.isna(y):
                found.append((entity, column, x, y))
                continue
            if isinstance(x, (bool, np.bool_)) or isinstance(y, (bool, np.bool_)) or column in RESULT_COLUMNS and not isinstance(x, float):
                if bool(x) != bool(y):
                    found.append((entity, column, x, y))
            elif abs(float(x) - float(y)) > tolerance * max(abs(float(x)), abs(float(y)), 1e-12):
                found.append((entity, column, x, y))
    return found


def lookahead_check(factor_cls: type[Factor], start=None, end=None, dates: list | None = None, samples: int = 8, tolerance: float = 1e-9, **kwargs) -> pd.DataFrame:
    """Rows where the factor says something different about a day once the days after it are known.

    ``dates`` default to ``samples`` days spread over the second half of the factor's history. ``kwargs`` go to
    the factor (``codes``, ``entity_ids``, its own settings). An empty result means no look-ahead was found.
    """
    full = factor_cls(start_timestamp=start, end_timestamp=end, **kwargs)
    days = full.factor_df.index.get_level_values("timestamp").unique().sort_values()
    if dates is None:
        later = days[len(days) // 2 :]
        dates = list(later[np.linspace(0, len(later) - 1, min(samples, len(later))).astype(int)])
    rows = []
    for day in pd.to_datetime(dates):
        cut = factor_cls(start_timestamp=start, end_timestamp=day, **kwargs)
        for source, a, b in (
            ("result", _row(full.result_df, day), _row(cut.result_df, day)),
            ("factor", _numeric(_row(full.factor_df, day)), _numeric(_row(cut.factor_df, day))),
        ):
            for entity, column, x, y in _differences(a, b, tolerance):
                rows.append({"date": day, "entity_id": entity, "frame": source, "column": column, "with_the_future": x, "without": y})
    return pd.DataFrame(rows, columns=["date", "entity_id", "frame", "column", "with_the_future", "without"])


def _targets(factor: Factor, day: pd.Timestamp) -> dict[str, int]:
    """Each entity's verdict on ``day``: +1 a positive target, -1 a negative one, 0 neither."""
    from osloquant.contract import TargetType

    verdict = dict.fromkeys(factor.get_targets(day, TargetType.negative), -1)
    verdict.update(dict.fromkeys(factor.get_targets(day, TargetType.positive), 1))
    return verdict


def warmup_check(factor_cls: type[Factor], day, warmups=(100, 200, 400, 800), reference: int = 3000, **kwargs) -> pd.DataFrame:
    """How much the factor on ``day`` moves when only ``warmup`` calendar days of history precede it.

    One row per warm-up, against a computation with ``reference`` days of history:

    ``largest_deviation``  the largest difference in any numeric column, relative to that column's typical size
                           on the day (the mean absolute value across entities), so values near zero do not explode it
    ``not_computable``     entities with a value in the long computation and none in the short one
    ``verdicts_changed``   entities whose verdict (positive target, negative target, neither) differs
    """
    day = pd.Timestamp(day)
    base = factor_cls(start_timestamp=day - pd.Timedelta(days=reference), end_timestamp=day, **kwargs)
    base_factor, base_verdict = _numeric(_row(base.factor_df, day)), _targets(base, day)
    entities = list(base_factor.index)
    rows = []
    for warmup in warmups:
        short = factor_cls(start_timestamp=day - pd.Timedelta(days=warmup), end_timestamp=day, **kwargs)
        factor, verdict = _numeric(_row(short.factor_df, day)).reindex(base_factor.index), _targets(short, day)
        worst, worst_column = 0.0, None
        for column in sorted(set(base_factor.columns) & set(factor.columns)):
            a, b = base_factor[column].astype(float), factor[column].astype(float)
            both = a.notna() & b.notna()
            scale = float(a[both].abs().mean()) if both.any() else 0.0
            if not both.any() or scale == 0:
                continue
            deviation = float((a[both] - b[both]).abs().max() / scale)
            if deviation > worst:
                worst, worst_column = deviation, column
        missing = int((base_factor.notna().all(axis=1) & ~factor.notna().all(axis=1)).sum()) if not base_factor.empty else 0
        changed = sum(1 for e in entities if base_verdict.get(e, 0) != verdict.get(e, 0))
        rows.append(
            {
                "warmup_days": warmup,
                "largest_deviation": worst,
                "column": worst_column,
                "not_computable": missing,
                "verdicts_changed": changed,
                "entities": len(entities),
            }
        )
    return pd.DataFrame(rows)
