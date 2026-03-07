"""AI Sentiment Factor (15% weight).

Uses Claude API to analyze earnings call transcripts, SEC filings, and news.
This is an auxiliary signal — weight is deliberately capped because sentiment
has a short half-life.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional

from trading.db import TradingDatabase


# Cache sentiment scores to avoid redundant API calls
_sentiment_cache: dict[str, tuple[float, datetime]] = {}
_CACHE_TTL_HOURS = 24  # sentiment expires after 24 hours


class SentimentFactor:
    """Score stocks by AI-analyzed sentiment from public sources."""

    def __init__(self, db: Optional[TradingDatabase] = None):
        self.db = db
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
            )
        return self._client

    def score(self, news_data: dict[str, list[str]]) -> dict[str, float]:
        """Calculate sentiment score for each symbol.

        Args:
            news_data: {symbol: [list of recent news headlines / summaries]}

        Returns:
            {symbol: score} in range [-1.0, +1.0]
        """
        scores = {}

        for symbol, texts in news_data.items():
            if not texts:
                continue

            # Check cache
            cached = self._get_cached(symbol)
            if cached is not None:
                scores[symbol] = cached
                continue

            score = self._analyze_sentiment(symbol, texts)
            if score is not None:
                scores[symbol] = score
                _sentiment_cache[symbol] = (score, datetime.utcnow())

        return scores

    def _get_cached(self, symbol: str) -> Optional[float]:
        if symbol in _sentiment_cache:
            score, timestamp = _sentiment_cache[symbol]
            if datetime.utcnow() - timestamp < timedelta(hours=_CACHE_TTL_HOURS):
                return score
            del _sentiment_cache[symbol]
        return None

    def _analyze_sentiment(self, symbol: str, texts: list[str]) -> Optional[float]:
        """Call Claude API to analyze sentiment of financial texts."""
        combined = "\n---\n".join(texts[:10])  # limit to 10 most recent

        prompt = f"""Analyze the financial sentiment of the following news and documents
about {symbol}. Consider:
1. Overall tone (bullish/bearish/neutral)
2. Forward-looking statements and guidance
3. Risk factors mentioned
4. Management confidence level

Return ONLY a JSON object with this exact format:
{{"score": <float between -1.0 and 1.0>, "confidence": <float 0-1>, "summary": "<one sentence>"}}

Where -1.0 = extremely bearish, 0 = neutral, +1.0 = extremely bullish.

Documents:
{combined}"""

        try:
            client = self._get_client()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Extract JSON from response
            if "{" in text and "}" in text:
                json_str = text[text.index("{"):text.rindex("}") + 1]
                result = json.loads(json_str)
                score = float(result.get("score", 0))
                return max(-1.0, min(1.0, score))
        except Exception:
            pass

        return None

    def analyze_earnings_call(self, symbol: str, transcript: str) -> Optional[float]:
        """Specialized analysis for earnings call transcripts."""
        return self._analyze_sentiment(symbol, [
            f"EARNINGS CALL TRANSCRIPT for {symbol}:\n{transcript[:5000]}"
        ])

    def analyze_sec_filing(self, symbol: str, filing_text: str) -> Optional[float]:
        """Specialized analysis for SEC filings (10-K, 10-Q, 8-K)."""
        return self._analyze_sentiment(symbol, [
            f"SEC FILING for {symbol}:\n{filing_text[:5000]}"
        ])
