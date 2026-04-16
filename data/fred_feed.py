"""
FRED (Federal Reserve Economic Data) feed for economic indicators.

Provides access to thousands of economic time series including:
- Unemployment rate
- GDP growth
- Inflation (CPI, PCE)
- Interest rates (yield curve)
- Housing data
- Employment data
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import pandas as pd
from loguru import logger
import httpx
import asyncio


class RateLimiter:
    """Simple async rate limiter."""

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: list = []

    async def wait(self):
        """Wait until next call is allowed."""
        now = asyncio.get_event_loop().time()
        cutoff = now - self.window_seconds

        self.calls = [t for t in self.calls if t > cutoff]

        if len(self.calls) >= self.max_calls:
            sleep_time = self.calls[0] - cutoff + 0.1
            await asyncio.sleep(sleep_time)

        self.calls.append(now)


class FREDDataFeed:
    """
    Federal Reserve Economic Data (FRED) feed.

    Features:
    - Access to 500k+ economic time series
    - Real-time data updates
    - No authentication required (unlimited free access)
    - Covers US and international economic indicators
    """

    BASE_URL = "https://api.stlouisfed.org/fred"

    # Common series for trading
    COMMON_SERIES = {
        "UNRATE": "Unemployment Rate",
        "CPIAUCSL": "Consumer Price Index",
        "DGS10": "10-Year Treasury Yield",
        "DGS2": "2-Year Treasury Yield",
        "T10Y2Y": "10Y-2Y Yield Spread",
        "GDPC1": "Real GDP",
        "PAYEMS": "Total Nonfarm Payroll",
        "RSXFS": "Advance Retail Sales",
        "HOUST": "Housing Starts",
        "MORTGAGE30US": "30-Year Mortgage Rate",
        "VIXCLS": "VIX",
        "DEXUSEU": "USD/EUR Exchange Rate",
        "DEXJPUS": "USD/JPY Exchange Rate",
    }

    def __init__(self, api_key: str, **config):
        """
        Initialize FRED data feed.

        Args:
            api_key: FRED API key (free from https://fred.stlouisfed.org/docs/api/api_key.html)
            **config: Additional configuration
        """
        self.api_key = api_key
        self.config = config

        # Rate limiter: FRED allows 120 requests per minute
        self.rate_limiter = RateLimiter(max_calls=100, window_seconds=60)

        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )

        logger.info("Initialized FRED data feed")

    async def get_series(
        self,
        series_id: str,
    ) -> Optional[float]:
        """
        Get the latest value of an economic series.

        Args:
            series_id: FRED series ID (e.g., 'UNRATE')

        Returns:
            Latest value, or None if not available
        """
        try:
            data = await self.get_series_data(series_id, limit=1)
            if data.empty:
                return None
            return float(data.iloc[-1])
        except Exception as e:
            logger.error(f"Failed to get series {series_id}: {e}")
            return None

    async def get_series_data(
        self,
        series_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100000,
    ) -> pd.Series:
        """
        Get time series data.

        Args:
            series_id: FRED series ID
            start: Start date
            end: End date
            limit: Maximum number of observations

        Returns:
            Pandas Series with date index
        """
        try:
            await self.rate_limiter.wait()

            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "limit": limit,
            }

            if start:
                params["observation_start"] = start.strftime("%Y-%m-%d")
            if end:
                params["observation_end"] = end.strftime("%Y-%m-%d")

            response = await self.client.get("/series/observations", params=params)
            response.raise_for_status()

            data = response.json()
            observations = data.get("observations", [])

            if not observations:
                logger.warning(f"No data for series {series_id}")
                return pd.Series()

            # Build DataFrame
            dates = []
            values = []

            for obs in observations:
                dates.append(pd.to_datetime(obs["date"]))
                # Handle missing values
                value = obs.get("value", ".")
                if value == ".":
                    values.append(None)
                else:
                    try:
                        values.append(float(value))
                    except ValueError:
                        values.append(None)

            series = pd.Series(values, index=dates)
            series.index.name = "date"
            logger.debug(f"Retrieved {len(series)} observations for {series_id}")
            return series

        except Exception as e:
            logger.error(f"Failed to get series data {series_id}: {e}")
            raise

    async def get_multiple_series(
        self,
        series_ids: List[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get multiple series as a DataFrame.

        Args:
            series_ids: List of FRED series IDs
            start: Start date
            end: End date

        Returns:
            DataFrame with series as columns
        """
        try:
            df = None

            for series_id in series_ids:
                series = await self.get_series_data(series_id, start, end)

                if df is None:
                    df = series.to_frame(name=series_id)
                else:
                    df[series_id] = series

            return df if df is not None else pd.DataFrame()

        except Exception as e:
            logger.error(f"Failed to get multiple series: {e}")
            raise

    async def get_series_info(self, series_id: str) -> Dict[str, Any]:
        """
        Get metadata about a series.

        Args:
            series_id: FRED series ID

        Returns:
            Dict with title, units, frequency, etc.
        """
        try:
            await self.rate_limiter.wait()

            response = await self.client.get(
                "/series",
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                },
            )
            response.raise_for_status()

            data = response.json()
            series = data.get("seriess", [{}])[0]

            return {
                "id": series.get("id"),
                "title": series.get("title"),
                "units": series.get("units"),
                "frequency": series.get("frequency"),
                "last_updated": series.get("last_updated"),
                "notes": series.get("notes"),
            }

        except Exception as e:
            logger.error(f"Failed to get series info {series_id}: {e}")
            raise

    async def search_series(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search for series by keyword.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching series with ID and title
        """
        try:
            await self.rate_limiter.wait()

            response = await self.client.get(
                "/series/search",
                params={
                    "search_text": query,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "limit": limit,
                },
            )
            response.raise_for_status()

            data = response.json()
            series_list = data.get("seriess", [])

            return [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "units": s["units"],
                    "frequency": s["frequency"],
                }
                for s in series_list
            ]

        except Exception as e:
            logger.error(f"Failed to search series: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check if FRED API is accessible.

        Returns:
            True if API is responding
        """
        try:
            await self.rate_limiter.wait()
            response = await self.client.get(
                "/series",
                params={
                    "series_id": "UNRATE",
                    "api_key": self.api_key,
                    "file_type": "json",
                },
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"FRED health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    def get_common_series(self) -> Dict[str, str]:
        """
        Get mapping of common economic series IDs to descriptions.

        Returns:
            Dict mapping series ID to description
        """
        return self.COMMON_SERIES.copy()


__all__ = ["FREDDataFeed"]
