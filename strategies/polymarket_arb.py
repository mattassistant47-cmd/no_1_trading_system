"""
Prediction market arbitrage strategy for Polymarket.
Detects edges comparing market odds vs model predictions using Kelly criterion.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger

from .base import BaseStrategy, Signal, Direction


@dataclass
class MarketEvent:
    """Prediction market event."""
    market_id: str
    question: str
    yes_price: float  # Probability YES (0-1)
    no_price: float   # Probability NO (0-1)
    volume_24h: float  # Trading volume in USD
    liquidity: float  # Available liquidity
    open_interest: float
    expiration: datetime
    category: str = ""


@dataclass
class ModelPrediction:
    """Model's probability prediction."""
    market_id: str
    model_confidence: float  # Model's estimated probability (0-1)
    method: str = ""  # "sentiment", "baserates", "hybrid"
    confidence_interval: Tuple[float, float] = (0.0, 1.0)


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""
    market_id: str
    question: str
    market_prob: float
    model_prob: float
    edge: float  # Market odds vs fair value
    kelly_fraction: float
    recommended_stake: float = 0.0
    expected_value: float = 0.0
    direction: str = ""  # "YES" or "NO"


class PolymarketArbitrage(BaseStrategy):
    """
    Arbitrage strategy on Polymarket prediction markets.

    Entry:
    - Identify market edges (market odds vs model prediction > threshold)
    - High liquidity (>$100K volume) for entry/exit
    - Position sizing via Kelly criterion

    Exit:
    - Price convergence to fair value
    - Expiration approaching (<7 days)
    - Stop loss on adverse moves

    Diversification:
    - Target 10-20 uncorrelated events
    - Spread capital across different categories
    - Risk-weighted position sizing
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Edge detection
        self.min_edge_pct = self.config.get("min_edge_pct", 0.05)  # 5%
        self.min_liquidity = self.config.get("min_liquidity", 100000)  # $100K
        self.max_markets = self.config.get("max_markets", 20)

        # Position sizing
        self.kelly_fraction = self.config.get("kelly_fraction", 0.25)  # 25% Kelly
        self.max_position_pct = self.config.get("max_position_pct", 0.05)  # 5% per trade

        # Risk management
        self.min_dte = self.config.get("min_dte", 7)  # Don't trade < 7 days
        self.correlation_threshold = self.config.get("correlation_threshold", 0.6)
        self.category_diversification = self.config.get("category_diversification", {
            "politics": 0.25,
            "sports": 0.25,
            "crypto": 0.20,
            "economics": 0.15,
            "other": 0.15,
        })

        # Market data storage
        self.active_markets: Dict[str, MarketEvent] = {}
        self.model_predictions: Dict[str, ModelPrediction] = {}
        self.active_positions: List[ArbitrageOpportunity] = []

        self._asset_class = "prediction_markets"
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate arbitrage signals from prediction markets."""
        signals = []

        try:
            # Fetch active markets
            markets = self._fetch_polymarket_data()

            if not markets:
                logger.warning("No market data available")
                return signals

            # Generate model predictions
            for market in markets:
                self._generate_market_prediction(market)

            # Find arbitrage opportunities
            opportunities = self._find_arb_opportunities(markets)

            # Diversify and size positions
            sized_opportunities = self._apply_diversification(opportunities)

            # Convert to signals
            for opp in sized_opportunities:
                if opp.expected_value > 0 and opp.edge >= self.min_edge_pct:
                    direction = Direction.LONG if opp.direction == "YES" else Direction.SHORT

                    signal = Signal(
                        symbol=opp.market_id,
                        direction=direction,
                        strength=self._calculate_arb_strength(opp),
                        strategy_name=self.name,
                        position_size=opp.recommended_stake,
                        metadata={
                            "market_question": opp.question,
                            "market_prob": opp.market_prob,
                            "model_prob": opp.model_prob,
                            "edge": opp.edge,
                            "kelly_fraction": opp.kelly_fraction,
                            "expected_value": opp.expected_value,
                            "type": "polymarket_arb",
                        }
                    )
                    signals.append(signal)
                    self.log_signal(signal)

                    self.active_positions.append(opp)

        except Exception as e:
            logger.error(f"Signal generation error in {self.name}: {e}")

        return signals

    def should_exit(
        self,
        position: Dict[str, Any],
        data: pd.DataFrame
    ) -> bool:
        """Determine if arbitrage position should exit."""
        try:
            market_id = position.get("symbol")
            if not market_id or market_id not in self.active_markets:
                return True

            market = self.active_markets[market_id]
            dte = (market.expiration - datetime.now()).days

            # Exit if approaching expiration (< min_dte)
            if dte < self.min_dte:
                logger.info(f"Exit: Expiration approaching ({dte} days)")
                return True

            # Exit if edge disappears (convergence)
            current_market_prob = market.yes_price
            model_prob = self.model_predictions.get(market_id, ModelPrediction(market_id, 0.5)).model_confidence
            current_edge = abs(current_market_prob - model_prob)

            if current_edge < (self.min_edge_pct / 2):  # Edge halved
                logger.info(f"Exit: Edge disappeared ({current_edge:.2%})")
                return True

            # Exit if liquidity drops below threshold
            if market.liquidity < (self.min_liquidity / 2):
                logger.info(f"Exit: Liquidity dried up (${market.liquidity:,.0f})")
                return True

        except Exception as e:
            logger.error(f"Exit check error: {e}")

        return False

    def _fetch_polymarket_data(self) -> List[MarketEvent]:
        """
        Fetch active markets from Polymarket API.
        In production, would call Polymarket GraphQL API.
        """
        # Placeholder - would fetch from Polymarket
        markets = []

        try:
            # Example market structure
            sample_markets = [
                MarketEvent(
                    market_id="market_001",
                    question="Will Bitcoin reach $100K by 2025?",
                    yes_price=0.72,
                    no_price=0.28,
                    volume_24h=2500000,
                    liquidity=500000,
                    open_interest=1000000,
                    expiration=datetime.now() + timedelta(days=90),
                    category="crypto"
                ),
                MarketEvent(
                    market_id="market_002",
                    question="Will Fed cut rates in Q2 2025?",
                    yes_price=0.35,
                    no_price=0.65,
                    volume_24h=1200000,
                    liquidity=300000,
                    open_interest=500000,
                    expiration=datetime.now() + timedelta(days=45),
                    category="economics"
                ),
            ]

            # Filter for minimum liquidity
            for market in sample_markets:
                if market.liquidity >= self.min_liquidity:
                    dte = (market.expiration - datetime.now()).days
                    if dte >= self.min_dte:
                        markets.append(market)
                        self.active_markets[market.market_id] = market

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")

        return markets

    def _generate_market_prediction(self, market: MarketEvent) -> None:
        """
        Generate model prediction for market using:
        - Sentiment analysis of question
        - Historical base rates
        - Hybrid approach
        """
        try:
            # Sentiment-based prediction (placeholder)
            sentiment_score = self._analyze_sentiment(market.question)
            sentiment_prob = 0.5 + (sentiment_score * 0.3)  # -30% to +30% from neutral

            # Base rate approach
            base_rate = self._get_base_rate(market.category, market.question)

            # Hybrid prediction (weighted average)
            model_prob = (sentiment_prob * 0.4 + base_rate * 0.6)
            model_prob = max(0.01, min(0.99, model_prob))  # Clamp to [0.01, 0.99]

            prediction = ModelPrediction(
                market_id=market.market_id,
                model_confidence=model_prob,
                method="hybrid",
                confidence_interval=(model_prob - 0.1, model_prob + 0.1)
            )

            self.model_predictions[market.market_id] = prediction
            logger.debug(f"Model prediction for {market.market_id}: {model_prob:.1%}")

        except Exception as e:
            logger.error(f"Prediction generation error: {e}")

    def _find_arb_opportunities(self, markets: List[MarketEvent]) -> List[ArbitrageOpportunity]:
        """Identify arbitrage opportunities."""
        opportunities = []

        try:
            for market in markets:
                prediction = self.model_predictions.get(
                    market.market_id,
                    ModelPrediction(market.market_id, 0.5)
                )

                # Edge on YES
                yes_edge = prediction.model_confidence - market.yes_price
                if yes_edge > self.min_edge_pct:
                    opp = ArbitrageOpportunity(
                        market_id=market.market_id,
                        question=market.question,
                        market_prob=market.yes_price,
                        model_prob=prediction.model_confidence,
                        edge=yes_edge,
                        kelly_fraction=self._calculate_kelly(
                            prediction.model_confidence,
                            market.yes_price
                        ),
                        direction="YES",
                        expected_value=yes_edge * market.yes_price
                    )
                    opportunities.append(opp)

                # Edge on NO
                no_edge = (1 - prediction.model_confidence) - market.no_price
                if no_edge > self.min_edge_pct:
                    opp = ArbitrageOpportunity(
                        market_id=market.market_id,
                        question=market.question,
                        market_prob=market.no_price,
                        model_prob=1 - prediction.model_confidence,
                        edge=no_edge,
                        kelly_fraction=self._calculate_kelly(
                            1 - prediction.model_confidence,
                            market.no_price
                        ),
                        direction="NO",
                        expected_value=no_edge * market.no_price
                    )
                    opportunities.append(opp)

        except Exception as e:
            logger.error(f"Opportunity detection error: {e}")

        return sorted(opportunities, key=lambda x: x.expected_value, reverse=True)

    def _apply_diversification(
        self,
        opportunities: List[ArbitrageOpportunity]
    ) -> List[ArbitrageOpportunity]:
        """Apply diversification constraints."""
        diversified = []
        category_allocation = {k: 0 for k in self.category_diversification.keys()}

        try:
            total_stake = 100000  # $100K portfolio

            for opp in opportunities[:self.max_markets]:
                market = self.active_markets[opp.market_id]
                category = market.category

                # Check category limits
                category_limit = self.category_diversification.get(category, 0.10)
                allocated_pct = category_allocation[category] / total_stake

                if allocated_pct < category_limit:
                    # Calculate stake using Kelly criterion
                    kelly_stake = (
                        total_stake *
                        opp.kelly_fraction *
                        self.kelly_fraction *
                        self.max_position_pct
                    )
                    kelly_stake = min(kelly_stake, total_stake * self.max_position_pct)

                    opp.recommended_stake = kelly_stake
                    category_allocation[category] += kelly_stake
                    diversified.append(opp)

        except Exception as e:
            logger.error(f"Diversification error: {e}")

        return diversified

    def _analyze_sentiment(self, question: str) -> float:
        """
        Analyze sentiment of market question.
        Returns score -1.0 to 1.0 (bullish/bearish).
        """
        # Placeholder - would use NLP/sentiment model
        bullish_keywords = ["will", "reach", "increase", "rally"]
        bearish_keywords = ["crash", "fall", "decline", "lose"]

        bullish_count = sum(1 for kw in bullish_keywords if kw.lower() in question.lower())
        bearish_count = sum(1 for kw in bearish_keywords if kw.lower() in question.lower())

        return (bullish_count - bearish_count) / (bullish_count + bearish_count + 1)

    def _get_base_rate(self, category: str, question: str) -> float:
        """
        Get historical base rate for category.
        Returns prior probability from historical data.
        """
        # Placeholder - would query historical outcomes
        base_rates = {
            "crypto": 0.45,
            "politics": 0.40,
            "sports": 0.50,
            "economics": 0.42,
            "other": 0.45,
        }
        return base_rates.get(category, 0.45)

    @staticmethod
    def _calculate_kelly(win_prob: float, odds: float) -> float:
        """
        Calculate Kelly fraction.
        Kelly = (p*b - q) / b, where:
        - p = probability of winning
        - q = probability of losing (1-p)
        - b = odds (probability implied odds)
        """
        if odds <= 0 or odds >= 1:
            return 0.0

        q = 1 - win_prob
        kelly = (win_prob * odds - q) / odds if odds > 0 else 0
        return max(0, min(kelly, 0.5))  # Cap at 50%

    @staticmethod
    def _calculate_arb_strength(opp: ArbitrageOpportunity) -> float:
        """Calculate signal strength based on edge and ev."""
        # Strength = edge magnitude * expected value
        strength = min(opp.edge / 0.1, 1.0) * 0.5  # Edge component (up to 0.5)
        strength += min(opp.expected_value / 0.1, 1.0) * 0.5  # EV component (up to 0.5)
        return min(strength, 1.0)
