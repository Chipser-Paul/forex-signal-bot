# Synthetic DXY Basket Documentation

## Overview

The system uses a synthetic DXY (US Dollar Index) constructed from 6 major currency pairs using ICE basket weights. This allows correlation analysis without requiring a real DXY symbol from the broker.

## Basket Composition

The synthetic DXY is constructed from the following pairs with ICE basket weights:

| Pair | Weight | Inversion | Notes |
|------|--------|------------|-------|
| EURUSDm | 0.576 (57.6%) | Yes | Largest weight, inverted (EUR/USD moves opposite to DXY) |
| USDJPYm | 0.136 (13.6%) | No | Direct correlation with DXY |
| GBPUSDm | 0.119 (11.9%) | Yes | Inverted (GBP/USD moves opposite to DXY) |
| USDCADm | 0.091 (9.1%) | No | Direct correlation with DXY |
| USDSEKm | 0.042 (4.2%) | No | Direct correlation with DXY |
| USDCHFm | 0.036 (3.6%) | No | Direct correlation with DXY |

**Total Weight: 100%**

## Calculation Method

1. **Data Fetching**: Fetch OHLCV data for each pair at the specified timeframe (default H1)
2. **Minimum Bars Check**: Requires at least 80% of requested bars per pair
3. **Weight Redistribution**: If a pair is unavailable, its weight is redistributed proportionally to available pairs
4. **Inversion**: For inverted pairs (EURUSDm, GBPUSDm), the close price is inverted (1/close)
5. **Weighted Sum**: Each pair's closes are multiplied by its adjusted weight and summed
6. **Alignment**: Arrays are aligned to the minimum length across all pairs

## Implementation Location

File: `bot/analysis/dxy_filter.py`
Function: `get_synthetic_dxy(timeframe="H1", bars=100)`

## Validation Status

**Current Status**: Documented but not validated against real DXY

**Validation Requirements**:
To validate the synthetic DXY against real DXY, the following would be needed:
1. Access to a real DXY symbol (DXY, USDX, USDXm, USDOLLAR, or USDX.i) from the broker
2. Historical data for the same time period for both synthetic and real DXY
3. Correlation analysis to measure the relationship strength

**Validation Method**:
```python
# Pseudocode for validation
real_dxy = fetch_ohlcv("DXY", "H1", bars=100)
synthetic_dxy, pairs_used = get_synthetic_dxy("H1", 100)

# Calculate correlation
correlation = np.corrcoef(real_dxy["close"], synthetic_dxy)[0, 1]

# Acceptable threshold: correlation > 0.8
if correlation > 0.8:
    print("✓ Synthetic DXY is reliable")
else:
    print("✗ Synthetic DXY needs adjustment")
```

## Known Limitations

1. **Pair Availability**: If broker doesn't provide all 6 pairs, the basket becomes less representative
2. **Weight Redistribution**: When pairs are missing, the remaining pairs' weights are artificially increased
3. **No Real-Time Validation**: Without access to real DXY, we cannot confirm the synthetic accuracy
4. **Broker-Specific Pricing**: Different brokers may have slightly different pricing, affecting correlation

## Recommendations

1. **Priority**: If broker provides a real DXY symbol, use it instead of synthetic
2.**Fallback**: Synthetic DXY is acceptable for general correlation analysis when real DXY unavailable
3. **Monitoring**: Periodically validate synthetic vs real if both become available
4. **Threshold**: Consider reducing reliance on DXY correlation if validation shows <0.7 correlation

## Current Usage

- Gate 7: DXY Correlation Check (for XAU symbols only)
- Confluence Scorer: Adds 1 point if DXY confirms bias
- Risk Management: May reduce position size if DXY conflicts with bias

## References

- ICE (Intercontinental Exchange) DXY basket methodology
- Standard DXY basket composition as of 2024
