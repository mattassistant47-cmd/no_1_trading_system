"""
Trading strategies module for autonomous multi-asset trading system.
Provides StrategyRegistry and all available strategy implementations.
"""

from typing import Dict, Type, List
from abc import ABC

from .base import BaseStrategy, Signal

def _lazy_import(name):
    """Lazy import to avoid failing on optional dependencies like pandas_ta."""
    import importlib
    try:
        mod = importlib.import_module(f".{name}", __package__)
        return mod
    except (ImportError, ModuleNotFoundError):
        return None

# Lazy imports — these may fail if pandas_ta is not installed
try:
    from .momentum import MultiTimeframeMomentum
except ImportError:
    MultiTimeframeMomentum = None

try:
    from .mean_reversion import StatisticalMeanReversion
except ImportError:
    StatisticalMeanReversion = None

try:
    from .crypto_momentum import CryptoMomentum
except ImportError:
    CryptoMomentum = None

try:
    from .options_wheel import OptionsWheel
except ImportError:
    OptionsWheel = None

try:
    from .polymarket_arb import PolymarketArbitrage
except ImportError:
    PolymarketArbitrage = None

try:
    from .ensemble import EnsembleStrategy
except ImportError:
    EnsembleStrategy = None

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
