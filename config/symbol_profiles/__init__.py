from copy import deepcopy

from .base import DEFAULT_PROFILE
from .btcusdm import PROFILE as BTCUSDM_PROFILE
from .xauusdm import PROFILE as XAUUSDM_PROFILE


SYMBOL_PROFILES = {
    "XAUUSDm": XAUUSDM_PROFILE,
    "BTCUSDm": BTCUSDM_PROFILE,
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def get_symbol_profile(symbol: str) -> dict:
    override = SYMBOL_PROFILES.get(symbol, {})
    return _deep_merge(DEFAULT_PROFILE, override)


__all__ = ["get_symbol_profile", "DEFAULT_PROFILE", "SYMBOL_PROFILES"]
