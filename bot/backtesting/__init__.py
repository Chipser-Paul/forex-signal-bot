"""Historical domain exports, loaded only when explicitly requested."""
from importlib import import_module

_EXPORT_MODULES = {
    "causal_quotes": "data",
    "align_observed_spread_to_mid_bars": "data",
    "classify_fidelity": "data",
    "iter_normalized_quote_chunks": "data",
    "normalize_bid_ask_bars": "data",
    "normalize_quotes": "data",
    "spread_statistics": "data",
    "adverse_fill_price": "costs",
    "commission_for_fill": "costs",
    "deterministic_slippage_points": "costs",
    "rollover_instants": "costs",
    "swap_for_rollover": "costs",
    "HistoricalExecutionEngine": "engine",
    "classify_phase1_legacy_inventory": "legacy",
    "REQUIRED_RESULT_FILES": "outputs",
    "RunDescriptor": "outputs",
    "build_summary": "outputs",
    "configuration_fingerprint": "outputs",
    "normalized_bundle_hash": "outputs",
    "write_result_bundle": "outputs",
    "BidAskBar": "models",
    "BrokerMetadataCatalog": "models",
    "BrokerSymbolMetadata": "models",
    "CommissionKind": "models",
    "CommissionSchedule": "models",
    "CostSource": "models",
    "DatasetDiagnostics": "models",
    "EXECUTABLE_SYMBOL": "models",
    "EXECUTION_MODEL_VERSION": "models",
    "FidelityClass": "models",
    "HistoricalAccountState": "models",
    "HistoricalExecutionError": "models",
    "HistoricalExecutionPolicy": "models",
    "HistoricalPosition": "models",
    "HistoricalQuote": "models",
    "MidBar": "models",
    "LedgerEntry": "models",
    "LedgerEventType": "models",
    "RunMode": "models",
    "Side": "models",
    "SimulatedFill": "models",
    "SlippageKind": "models",
    "SlippageModel": "models",
    "SpreadObservation": "models",
    "SwapCalculation": "models",
    "SwapSchedule": "models",
}
__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value
