"""
Self-Evolution Engine Module

Autonomous strategy optimization, performance tracking, and portfolio rotation
for continuous system improvement and risk-adjusted allocation management.
"""

from evolution.optimizer import StrategyOptimizer
from evolution.performance import PerformanceTracker
from evolution.rotator import StrategyRotator
from evolution.walk_forward import WalkForwardAnalyzer

__all__ = [
    "StrategyOptimizer",
    "PerformanceTracker",
    "StrategyRotator",
    "WalkForwardAnalyzer",
]
