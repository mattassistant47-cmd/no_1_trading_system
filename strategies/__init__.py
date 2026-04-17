"""
Trading strategies module for autonomous multi-asset trading system.
Provides StrategyRegistry and all available strategy implementations.
"""

from typing import Dict, Type, List
from abc import ABC

from .base import BaseStrategy, Signal

from .momentum import MultiTimeframeMomentum
from .mean_reversion import StatisticalMeanReversion
from .crypto_momentum import CryptoMomentum
from .options_wheel import OptionsWheel
from .polymarket_arb import PolymarketArbitrage
from .ensemble import EnsembleStrategy
from .breakout import Breakout
from .trend_following import TrendFollowing
from .pairs_trading import PairsTrading
from .volatility_regime import VolatilityRegime

__version__ = "1.0.0"

__all__ = [
    "BaseStrategy",
    "Signal",
    "MultiTimeframeMomentum",
    "StatisticalMeanReversion",
    "CryptoMomentum",
    "OptionsWheel",
    "PolymarketArbitrage",
    "EnsembleStrategy",
    "Breakout",
    "TrendFollowing",
    "PairsTrading",
    "VolatilityRegime",
    "StrategyRegistry",
]


class StrategyRegistry:
    """
    Central registry for trading strategies.
    Manages strategy instantiation, discovery, and lifecycle.
    """

    _strategies: Dict[str, Type[BaseStrategy]] = {
        "momentum": MultiTimeframeMomentum,
        "mean_reversion": StatisticalMeanReversion,
        "crypto_momentum": CryptoMomentum,
        "options_wheel": OptionsWheel,
        "polymarket_arb": PolymarketArbitrage,
        "ensemble": EnsembleStrategy,
        "breakout": Breakout,
        "trend_following": TrendFollowing,
        "pairs_trading": PairsTrading,
        "volatility_regime": VolatilityRegime,
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]) -> None:
        """Register a new strategy class."""
        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError(
                f"{strategy_class} must inherit from BaseStrategy"
            )
        cls._strategies[name] = strategy_class

    @classmethod
    def get(cls, name: str) -> Type[BaseStrategy]:
        """Retrieve a strategy class by name."""
        if name not in cls._strategies:
            raise ValueError(
                f"Strategy '{name}' not found. "
                f"Available: {list(cls._strategies.keys())}"
            )
        return cls._strategies[name]

    @classmethod
    def instantiate(
        cls, name: str, config: dict = None
    ) -> BaseStrategy:
        """Instantiate a strategy with optional configuration."""
        strategy_class = cls.get(name)
        return strategy_class(config or {})

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered strategy names."""
        return list(cls._strategies.keys())

    @classmethod
    def get_all_strategies(cls) -> Dict[str, Type[BaseStrategy]]:
        """Return all registered strategies."""
        return cls._strategies.copy()
