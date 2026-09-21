# Synthetic DXY Basket

Phase 6 defines the fallback synthetic index as the documented geometric basket:

`50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036`

Broker mappings are explicit and suffix-preserving. The default read-only map is
`EURUSDm`, `USDJPYm`, `GBPUSDm`, `USDCADm`, `USDSEKm`, and `USDCHFm`. These data
symbols are never executable instruments.

All six positive finite closes are required. They are aligned by Phase 2
`available_at` timestamps using bounded backward causal joins; missing, stale,
future, or malformed constituents produce `DATA_UNSAFE`. Weights are never
redistributed. A deliberately configured direct DXY series may take priority only
after the same causal and freshness checks.

The strategy uses normalized trailing slope to classify DXY as bullish, bearish,
or neutral. For gold, inverse agreement is supporting evidence and same-direction
movement is a veto. This relationship is probabilistic, not guaranteed, and is not
counted again in the setup score.

The formula and interpretation have unit and causal regression coverage under
`tests/phase6/test_dxy_regime.py`. No comparison with a broker index or
profitability validation was performed in Phase 6.
