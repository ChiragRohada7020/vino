"""
Signal Detection Module
=======================

Configurable signal definitions for combining pivot proximity with
other indicator conditions.

Strategies are defined as configurable dictionaries so users can
easily add/modify strategies without changing core logic.
"""

from typing import Dict, List, Callable, Any
from dataclasses import dataclass


@dataclass
class SignalConfig:
    """Configuration for a signal strategy."""
    name: str
    description: str
    pivot_levels: List[str]
    willy_zone: List[str]
    willy_signal: List[str]
    enabled: bool = True


# Default signal strategies
DEFAULT_STRATEGIES: Dict[str, SignalConfig] = {
    'bullish_setup': SignalConfig(
        name='bullish_setup',
        description='Price near support + Willy bullish crossover',
        pivot_levels=['S1', 'S2', 'S3', 'S4', 'S5'],
        willy_zone=['Oversold', 'Neutral'],
        willy_signal=['Bullish Cross'],
        enabled=True
    ),
    'bearish_setup': SignalConfig(
        name='bearish_setup',
        description='Price near resistance + Willy bearish crossover',
        pivot_levels=['R1', 'R2', 'R3', 'R4', 'R5'],
        willy_zone=['Overbought', 'Neutral'],
        willy_signal=['Bearish Cross'],
        enabled=True
    ),
    'strong_bullish': SignalConfig(
        name='strong_bullish',
        description='Price at strong support + Willy oversold + bullish crossover',
        pivot_levels=['S3', 'S4', 'S5'],
        willy_zone=['Oversold'],
        willy_signal=['Bullish Cross'],
        enabled=False
    ),
    'strong_bearish': SignalConfig(
        name='strong_bearish',
        description='Price at strong resistance + Willy overbought + bearish crossover',
        pivot_levels=['R3', 'R4', 'R5'],
        willy_zone=['Overbought'],
        willy_signal=['Bearish Cross'],
        enabled=False
    )
}


def match_strategy(
    pivot_name: str,
    willy_zone: str,
    willy_signal: str,
    strategies: Dict[str, SignalConfig] = None
) -> List[str]:
    """
    Match a scan result against configured strategies.

    Parameters
    ----------
    pivot_name : str
        Name of the nearest pivot level (e.g., 'S1', 'R2')
    willy_zone : str
        Current Willy zone ('Overbought', 'Oversold', 'Neutral')
    willy_signal : str
        Current Willy signal ('Bullish Cross', 'Bearish Cross', 'No Signal')
    strategies : Dict[str, SignalConfig], optional
        Custom strategies (uses DEFAULT_STRATEGIES if None)

    Returns
    -------
    List[str]
        List of matching strategy names
    """
    if strategies is None:
        strategies = DEFAULT_STRATEGIES

    matches = []

    for name, config in strategies.items():
        if not config.enabled:
            continue

        pivot_match = pivot_name in config.pivot_levels
        zone_match = willy_zone in config.willy_zone
        signal_match = willy_signal in config.willy_signal

        if pivot_match and zone_match and signal_match:
            matches.append(name)

    return matches


def get_strategy_names() -> List[str]:
    """Get list of all strategy names."""
    return list(DEFAULT_STRATEGIES.keys())


def get_enabled_strategies() -> Dict[str, SignalConfig]:
    """Get only enabled strategies."""
    return {k: v for k, v in DEFAULT_STRATEGIES.items() if v.enabled}
