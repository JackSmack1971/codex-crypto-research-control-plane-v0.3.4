# Provenance

## Primary snapshot

- Title: **Massive – endpoints included on the Basic plan (REST)**
- Provider named by source: **Massive**
- Snapshot date: **2026-09-28**
- Source shape: uploaded Markdown documentation pack
- Scope: only endpoint pages where the Basic plan showed **Included**
- Source endpoint entries: **96**
- Covered markets: stocks, options, indices, forex, crypto, futures, and U.S. macro/economy

`endpoint-catalog.json` is the single machine-readable representation of those 96 transformed entries. Method/path strings and `basic_limit` wording are preserved from the supplied skill's source-derived tables.

## Transformation policy

The package compresses source descriptions into `best_for` routing text while preserving operationally important endpoint paths and plan-limit wording. It intentionally does not claim query parameters, response schemas, authentication behavior, or current plan status when those facts are absent from the snapshot.

One visibly truncated transformed description for `GET /fed/v1/treasury-yields` read only **"Historical U.S."**. Its `best_for` text was repaired on 2026-09-28 from current official Massive endpoint documentation; the method/path and Basic limit were not changed.
