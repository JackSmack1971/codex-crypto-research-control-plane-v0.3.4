# Decision notes

Load only the section relevant to the current routing problem.

## Bar-selection ladder

- Interval or date range → **Custom/Aggregate Bars** for that market.
- One specified date → **Daily Ticker Summary** when the catalog contains one for that market.
- Immediately previous session/day → **Previous Day Bar**.
- One date across an entire supported market → **Daily Market Summary** when present.

Do not substitute one rung for another merely because it is easier to call.

## Clock and freshness semantics

- Stocks, options, indices, and forex aggregate descriptions use **ET** where the snapshot states it.
- Crypto custom bars use **UTC** in the snapshot.
- `Updated in real time`, `End-of-day`, `Updated daily`, `Updated every 2 weeks`, `Updated monthly`, and `Updated as needed` are distinct contracts.
- Market Status being real-time does not make price bars or indicators real-time.

## Historical-window boundary

Compare the requested window with the selected row's `basic_limit`. If the request exceeds the stated history, do not promise that Basic can satisfy it.

Futures Aggregate Bars are a deliberate special case: the snapshot states **`8-hour historical; history 2 years`**. Preserve both qualifiers unless current Massive documentation resolves how they interact. Current official Massive documentation on 2026-09-28 still showed Basic recency as 8-hour historical and history as 2 years.

## Shared paths can have market-specific limits

The same REST path can appear under multiple markets with different snapshot limits. In particular, `/v3/reference/tickers` and `/v3/reference/tickers/{ticker}` have market-specific freshness/history entries. Always filter by market before using a shared path's plan limit.

## Stock filing chooser

- Annual business/risk narrative → **10-K Sections**
- Institutional quarterly holdings → **13-F Filings**
- Material-event categorization → **8-K Disclosures**
- Parsed material-event text → **8-K Text**
- Filing discovery → **SEC EDGAR Index**
- Initial insider ownership → **Form 3**
- Insider ownership changes → **Form 4**
- Risk taxonomy → **Risk Categories**
- Comparable filing risk factors → **Risk Factors**

Taxonomy endpoints describe categories; they are not substitutes for filing-instance endpoints.

## Deprecated stock corporate-action endpoints

The snapshot contains deprecated Dividends and Splits rows alongside newer stock-native replacements. Prefer the non-deprecated row when it fulfills the request; keep deprecated rows only for legacy-path recognition.

## Current-doc escalation

Verify current Massive documentation/tooling when the request asks what is included **now/today**, when parameters or response fields are needed, when a ticker-format or pagination rule matters, or when the snapshot is otherwise insufficient. Do not silently fill those gaps from model memory.
