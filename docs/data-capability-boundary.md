# Data capability boundary

This is the evidence contract for the Massive-backed end-of-day research system.

## Three independent capability facts

Never collapse these into one boolean:

1. **Discovery** — current Massive MCP endpoint documentation says a route exists.
2. **Dated snapshot** — the bundled Basic catalog marks the capability `INCLUDED` or `UNKNOWN` for its snapshot date.
3. **Authenticated access** — the active Massive account actually retrieves the data.

Only authenticated success establishes effective access. `NOT_ENTITLED` takes precedence over a static snapshot. Direct-network fallback is forbidden.

## Severity classes

`config/daily-capabilities.json` defines operational severity.

### CORE

The daily crypto-core forecast requires:

- point-in-time crypto universe;
- cutoff-day grouped crypto EOD cross-section;
- sufficient crypto historical bars for the selected eligible universe plus BTC/ETH anchors.

A denied, incomplete, transient-only, post-cutoff, or unmaterialized CORE dataset blocks the run.

### ENRICHMENT

FX, stock macro proxies, and index macro proxies deepen cross-asset regime analysis. When inaccessible under the authenticated plan, the run may continue as `DEGRADED` if all CORE requirements pass. Missing enrichment must reduce coverage/confidence and cannot be imputed as neutral evidence.

### EVENT_OPTIONAL

SEC/institutional, short-interest, and options-proxy families are event-driven by default. Inaccessibility is recorded as unavailable, not as `no signal`. A registered research design may explicitly elevate one to required status for that experiment.

## Supported research families

When effectively accessible and materialized, the architecture can support point-in-time universe control, crypto OHLC/volume/VWAP/trade-count aggregates, U.S. equities, indices, FX, EOD option-contract data, SEC filings/holdings/insider/risk-factor data, and stock short data.

## Crypto limitations

The supplied crypto Basic guide constrains crypto to end-of-day data with two years of history and excludes crypto trades/last trade, snapshots, WebSockets, and flat files. Massive MCP discovery may still expose those broader endpoint families; discoverability is not entitlement.

## Unsupported claims without new governed data

Do not claim direct evidence for order-book depth/imbalance, liquidations, perpetual funding/basis, futures OI, native-crypto options positioning, whale or wallet activity, exchange flows, stablecoin issuance/flows, social/news sentiment, or real-time catalysts.

## Transaction-cost boundary

EOD data does not establish executable spread, depth, market impact, funding, or borrow. Research must expose turnover and sensitivity to pessimistic cost scenarios instead of presenting one precise net-performance estimate.
