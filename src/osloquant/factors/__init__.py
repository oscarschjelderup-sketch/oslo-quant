"""Ready-made factors, the indicators they are built from, and the selector that combines them."""

from osloquant.contract.factor import Factor, RankScorer, ScoreFactor, Scorer, Transformer
from osloquant.factors.fundamental import GoodCompanyFactor
from osloquant.factors.target_selector import SelectMode, TargetSelector
from osloquant.factors.technical import (
    AboveMaFactor,
    BollFactor,
    BullFactor,
    CrossMaFactor,
    GoldCrossFactor,
    MomentumFactor,
    TechnicalFactor,
)
from osloquant.factors.transformers import BollTransformer, MacdTransformer, MaTransformer, MomentumTransformer

__all__ = [
    "AboveMaFactor",
    "BollFactor",
    "BollTransformer",
    "BullFactor",
    "CrossMaFactor",
    "Factor",
    "GoldCrossFactor",
    "GoodCompanyFactor",
    "MaTransformer",
    "MacdTransformer",
    "MomentumFactor",
    "MomentumTransformer",
    "RankScorer",
    "ScoreFactor",
    "Scorer",
    "SelectMode",
    "TargetSelector",
    "TechnicalFactor",
    "Transformer",
]
