"""
Financial data analysis: compute technical indicators and aggregate metrics.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_moving_averages(
    prices: pd.DataFrame,
    windows: tuple[int, ...] = (5, 20, 60),
) -> dict[str, float | None]:
    """Compute moving averages from a price DataFrame sorted by trade_date ascending.

    Returns dict like {"ma5": 72000.0, "ma20": 71500.0, "ma60": None}.
    """
    result = {}
    for w in windows:
        key = f"ma{w}"
        if len(prices) >= w:
            result[key] = round(prices["close"].tail(w).mean(), 2)
        else:
            result[key] = None
    return result


def compute_rsi(prices: pd.DataFrame, period: int = 14) -> float | None:
    """Compute the Relative Strength Index for the most recent period."""
    if len(prices) < period + 1:
        return None

    closes = prices["close"].values
    deltas = pd.Series(closes).diff().dropna()
    recent = deltas.tail(period)

    gains = recent.clip(lower=0).mean()
    losses = (-recent.clip(upper=0)).mean()

    if losses == 0:
        return 100.0
    rs = gains / losses
    return round(100 - 100 / (1 + rs), 2)


def compute_change_pct(prices: pd.DataFrame) -> float | None:
    """Compute the latest daily change percentage."""
    if len(prices) < 2:
        return None
    prev = prices["close"].iloc[-2]
    curr = prices["close"].iloc[-1]
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)


def compute_roe(eps: float | None, bps: float | None) -> float | None:
    """Estimate ROE = EPS / BPS * 100."""
    if eps is None or bps is None or bps == 0:
        return None
    return round(eps / bps * 100, 2)


def analyze_stock(
    prices: pd.DataFrame,
    fundamentals: dict,
) -> dict:
    """Run all analyses for a single stock and return a flat metrics dict."""
    metrics = {}

    # Moving averages
    metrics.update(compute_moving_averages(prices))

    # RSI
    metrics["rsi14"] = compute_rsi(prices)

    # Daily change %
    metrics["change_pct"] = compute_change_pct(prices)

    # Fundamentals pass-through
    for key in ("per", "pbr", "eps", "bps", "dividend_yield"):
        metrics[key] = fundamentals.get(key)

    # Derived
    metrics["roe"] = compute_roe(fundamentals.get("eps"), fundamentals.get("bps"))
    metrics["roa"] = None  # requires financial statements; placeholder
    metrics["debt_ratio"] = None  # requires balance sheet; placeholder

    return metrics
