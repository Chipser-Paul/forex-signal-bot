# Phase 8L: Conservative Development Metadata Bounds

Phase 8L creates an owner-authorized development proxy, not a reconstruction
of 2024 broker conditions. The primary evidence is a sanitized Exness support
EML stating that archived 2024 contract specifications, trading terms, margin
rules, stop distances, and execution modes cannot be supplied retrospectively.
The accompanying PDF is only a hash-bound rendition.

## Fact And Assumption Boundary

- Observed 2024 quote representation is empirical and remains limited to
  parsing representation.
- Current screenshots and broker-support records are current-only references.
- The 100-ounce, 0.001, USD, 0.01-lot, 20-lot, market/FOK/IOC baseline is an
  explicitly labelled development proxy.
- The `0.10 USD/tick/lot` value is derived from assumed `100 * 0.001`; it is
  never presented as historical tick-value evidence.
- Historical stop/freeze and margin/leverage values remain unavailable.

## Baseline Proxy

| Setting | Proxy | Classification |
|---|---:|---|
| Symbol | `XAUUSDm` | executable scope |
| Digits | `3` | empirical quote representation |
| Point/tick representation | `0.001` | development assumption |
| Contract size | `100` troy ounces/lot | current-reference proxy |
| Derived tick value | `100 * 0.001 = 0.10 USD`/lot | derived from assumed contract size |
| Minimum/step volume | `0.01` lots | current-reference proxy |
| Maximum volume | `20` lots | most restrictive current-reference day/night limit |
| Execution/filling | market, FOK/IOC | current-reference proxy |
| Spread | observed 2024 bid/ask | empirical |
| Commission | zero Standard-account reference | current-only |

## Mandatory Scenario Ladder

Every future development-only evaluation must disclose and retain all ten
preregistered scenarios: baseline, reduced maximum volume, stricter margin,
constrained free margin, FOK missed fill, partial-fill liquidity, stop/freeze
guard, minimum-volume risk failure, stale-metadata rejection, and a combined
adverse case. Cheapest-scenario selection is prohibited.

The policy may make development preparation sufficient, but this checkpoint
does not authorize strategy execution. Holdout, final validation, and Phase 9
remain blocked. Any output must be labelled development proxy material, not
historically validated evidence.

## Published Evidence

The primary EML SHA-256 is
`093bb167aad27efebafe3c0ea965c7083042d20e3b3fb1babc107747c35a1f7b`; the
secondary PDF rendition SHA-256 is
`cf86c8a9c1a81cadc99ce20013298a80270524a938321f70842da545598eb760`.
Derived records contain neither raw message content nor personal mail identity.

- `evidence-broker_metadata_unavailability-v1-f1be088c17a391c4`
- `evidence-development_metadata_bounds-v1-8dad509e60c8014a`
- `evidence-development_metadata_bounds_readiness-v1-6fa811a3200c6042`

The metadata-bounds policy fingerprint is
`54f9a9817613bf3115039dd43b66c476a72627880663d4fb6c3f59cbbde1be1f`.
