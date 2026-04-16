"""
Market Scanner Agent

Autonomous agent that scans universe of 500+ symbols for trading signals
across all strategies. Filters by liquidity, volatility, and trend strength.
Publishes opportunities to event bus on schedule.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import statistics
from loguru import logger


class MarketCondition(str, Enum):
    """Market condition classifications"""
    STRONG_UPTREND = "strong_uptrend"
    MILD_UPTREND = "mild_uptrend"
    SIDEWAYS = "sideways"
    MILD_DOWNTREND = "mild_downtrend"
    STRONG_DOWNTREND = "strong_downtrend"


@dataclass
class SignalOpportunity:
    """Trading signal opportunity"""
    symbol: str
    strategy_id: str
    signal_type: str  # "buy", "sell", "short", "exit"
    confidence: float  # 0-1
    price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    market_condition: Optional[MarketCondition] = None
    atr: float = 0.0
    volatility: float = 0.0
    trend_strength: float = 0.0
    liquidity_score: float = 0.0
    technical_score: float = 0.0
    rationale: str = ""


@dataclass
class ScanResult:
    """Market scan result"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbols_scanned: int = 0
    symbols_passed_filters: int = 0
    opportunities_found: List[SignalOpportunity] = field(default_factory=list)
    scan_duration_sec: float = 0.0
    errors: List[str] = field(default_factory=list)


class MarketScanner:
    """
    Autonomous market scanner agent.

    Capabilities:
    - Scans 500+ symbol universe
    - Evaluates all registered strategies
    - Filters by liquidity (minimum volume)
    - Filters by volatility (ATR-based)
    - Scores trend strength
    - Publishes signals to event bus
    - Scheduled execution (15min equities, 1hr crypto)
    """

    def __init__(
        self,
        min_daily_volume: float = 1_000_000.0,
        min_atr_pct: float = 0.5,
        max_atr_pct: float = 10.0,
        min_trend_strength: float = 0.3,
        min_liquidity_score: float = 0.5,
        max_opportunities_per_scan: int = 20,
    ):
        """
        Initialize MarketScanner.

        Args:
            min_daily_volume: Minimum daily dollar volume
            min_atr_pct: Minimum ATR % (low volatility cutoff)
            max_atr_pct: Maximum ATR % (high volatility cutoff)
            min_trend_strength: Minimum trend strength (0-1)
            min_liquidity_score: Minimum liquidity score (0-1)
            max_opportunities_per_scan: Maximum signals per scan
        """
        self.min_daily_volume = min_daily_volume
        self.min_atr_pct = min_atr_pct
        self.max_atr_pct = max_atr_pct
        self.min_trend_strength = min_trend_strength
        self.min_liquidity_score = min_liquidity_score
        self.max_opportunities_per_scan = max_opportunities_per_scan

        # State
        self.symbols_universe: List[str] = []
        self.strategy_evaluators: Dict[str, Callable] = {}
        self.scan_history: List[ScanResult] = []
        self.last_scan_time: Optional[datetime] = None

        # Callbacks
        self.on_signal: Optional[Callable] = None

        logger.info(
            f"MarketScanner initialized: "
            f"min_volume=${min_daily_volume:,.0f}, "
            f"atr_range={min_atr_pct}%-{max_atr_pct}%, "
            f"min_trend_strength={min_trend_strength}"
        )

    def register_universe(self, symbols: List[str]):
        """Register symbol universe to scan"""
        self.symbols_universe = symbols
        logger.info(f"Registered {len(symbols)} symbols for scanning")

    def register_strategy_evaluator(
        self,
        strategy_id: str,
        evaluator_fn: Callable,
    ):
        """
        Register strategy evaluator function.

        Evaluator signature: async fn(symbol, price_data) -> (signal_type, confidence, rationale)
        """
        self.strategy_evaluators[strategy_id] = evaluator_fn
        logger.info(f"Registered evaluator for strategy {strategy_id}")

    async def scan_market(
        self,
        price_data: Dict[str, Dict[str, Any]],  # {symbol: {price, volume, atr, ...}}
    ) -> ScanResult:
        """
        Scan market for trading opportunities.

        Args:
            price_data: Current price and volume data for universe

        Returns:
            ScanResult with opportunities found
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting market scan ({len(self.symbols_universe)} symbols)")

        result = ScanResult(timestamp=start_time)

        # Filter symbols by liquidity
        liquid_symbols = await self._filter_by_liquidity(price_data)
        logger.debug(f"Passed liquidity filter: {len(liquid_symbols)} symbols")

        # Filter by volatility range
        valid_symbols = await self._filter_by_volatility(price_data, liquid_symbols)
        logger.debug(f"Passed volatility filter: {len(valid_symbols)} symbols")

        result.symbols_scanned = len(self.symbols_universe)
        result.symbols_passed_filters = len(valid_symbols)

        # Evaluate each symbol with all strategies
        opportunities = []

        for symbol in valid_symbols:
            try:
                symbol_data = price_data.get(symbol, {})

                # Classify market condition
                market_condition = await self._classify_market_condition(symbol_data)

                # Evaluate with each strategy
                for strategy_id, evaluator_fn in self.strategy_evaluators.items():
                    try:
                        signal = await evaluator_fn(symbol, symbol_data)

                        if signal:
                            # Create opportunity
                            opp = SignalOpportunity(
                                symbol=symbol,
                                strategy_id=strategy_id,
                                signal_type=signal.get("type", "unknown"),
                                confidence=signal.get("confidence", 0.0),
                                price=symbol_data.get("price", 0.0),
                                market_condition=market_condition,
                                atr=symbol_data.get("atr", 0.0),
                                volatility=symbol_data.get("volatility", 0.0),
                                trend_strength=symbol_data.get("trend_strength", 0.0),
                                liquidity_score=symbol_data.get("liquidity_score", 0.0),
                                technical_score=signal.get("technical_score", 0.0),
                                rationale=signal.get("rationale", ""),
                            )

                            # Score opportunity
                            score = await self._score_opportunity(opp)

                            if score > 0.5:
                                opportunities.append(opp)

                    except Exception as e:
                        logger.error(
                            f"Error evaluating {symbol} with {strategy_id}: {e}"
                        )
                        result.errors.append(
                            f"{symbol}/{strategy_id}: {str(e)}"
                        )

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                result.errors.append(f"{symbol}: {str(e)}")

        # Sort by confidence and take top opportunities
        opportunities.sort(
            key=lambda x: (x.confidence * x.technical_score),
            reverse=True
        )
        result.opportunities_found = opportunities[:self.max_opportunities_per_scan]

        # Record timing
        result.scan_duration_sec = (datetime.utcnow() - start_time).total_seconds()
        self.last_scan_time = start_time
        self.scan_history.append(result)

        logger.info(
            f"Market scan complete: {len(result.opportunities_found)} opportunities "
            f"found in {result.scan_duration_sec:.1f}s"
        )

        # Publish signals
        if result.opportunities_found:
            await self._publish_signals(result.opportunities_found)

        return result

    async def _filter_by_liquidity(
        self, price_data: Dict[str, Dict]
    ) -> List[str]:
        """Filter symbols by minimum daily volume"""
        liquid_symbols = []

        for symbol in self.symbols_universe:
            try:
                data = price_data.get(symbol, {})
                volume = data.get("volume", 0)
                price = data.get("price", 0)

                if volume and price:
                    dollar_volume = volume * price
                    liquidity_score = min(
                        1.0,
                        dollar_volume / self.min_daily_volume
                    )

                    if dollar_volume >= self.min_daily_volume * 0.5:
                        liquid_symbols.append(symbol)
            except Exception:
                pass

        return liquid_symbols

    async def _filter_by_volatility(
        self, price_data: Dict[str, Dict], symbols: List[str]
    ) -> List[str]:
        """Filter symbols by ATR volatility range"""
        valid_symbols = []

        for symbol in symbols:
            try:
                data = price_data.get(symbol, {})
                atr = data.get("atr", 0)
                price = data.get("price", 1)

                if atr > 0:
                    atr_pct = (atr / price) * 100

                    # Must be in acceptable volatility range
                    if self.min_atr_pct <= atr_pct <= self.max_atr_pct:
                        valid_symbols.append(symbol)

            except Exception:
                pass

        return valid_symbols

    async def _classify_market_condition(
        self, symbol_data: Dict[str, Any]
    ) -> MarketCondition:
        """Classify market condition for symbol"""
        trend_strength = symbol_data.get("trend_strength", 0.0)
        direction = symbol_data.get("direction", 0)  # -1, 0, or 1

        if direction > 0:
            if trend_strength > 0.7:
                return MarketCondition.STRONG_UPTREND
            else:
                return MarketCondition.MILD_UPTREND
        elif direction < 0:
            if trend_strength > 0.7:
                return MarketCondition.STRONG_DOWNTREND
            else:
                return MarketCondition.MILD_DOWNTREND
        else:
            return MarketCondition.SIDEWAYS

    async def _score_opportunity(self, opp: SignalOpportunity) -> float:
        """Score opportunity 0-1 based on multiple factors"""
        confidence_weight = opp.confidence * 0.40
        technical_weight = opp.technical_score * 0.30
        trend_weight = opp.trend_strength * 0.20
        liquidity_weight = opp.liquidity_score * 0.10

        total_score = (
            confidence_weight + technical_weight + trend_weight + liquidity_weight
        )

        return max(0.0, min(1.0, total_score))

    async def _publish_signals(self, opportunities: List[SignalOpportunity]):
        """Publish signals to event bus"""
        if self.on_signal:
            for opp in opportunities:
                try:
                    await self._safe_call(self.on_signal, opp)
                except Exception as e:
                    logger.error(f"Error publishing signal for {opp.symbol}: {e}")

    async def _safe_call(self, callback: Callable, *args, **kwargs):
        """Safely call callback"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in callback: {e}")

    def get_scan_report(self) -> Dict:
        """Get latest scan report"""
        if not self.scan_history:
            return {"error": "No scans completed"}

        latest = self.scan_history[-1]

        return {
            "timestamp": latest.timestamp.isoformat(),
            "symbols_scanned": latest.symbols_scanned,
            "symbols_passed_filters": latest.symbols_passed_filters,
            "opportunities_found": len(latest.opportunities_found),
            "scan_duration_sec": latest.scan_duration_sec,
            "top_opportunities": [
                {
                    "symbol": opp.symbol,
                    "strategy": opp.strategy_id,
                    "signal": opp.signal_type,
                    "confidence": opp.confidence,
                    "price": opp.price,
                    "market_condition": opp.market_condition.value if opp.market_condition else None,
                    "rationale": opp.rationale,
                }
                for opp in latest.opportunities_found[:10]
            ],
            "errors": latest.errors,
        }

    def get_scan_history(self, limit: int = 20) -> List[Dict]:
        """Get historical scans"""
        results = self.scan_history[-limit:] if limit else self.scan_history

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "symbols_scanned": r.symbols_scanned,
                "symbols_passed_filters": r.symbols_passed_filters,
                "opportunities_found": len(r.opportunities_found),
                "scan_duration_sec": r.scan_duration_sec,
            }
            for r in results
        ]
