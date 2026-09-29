from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


def _read_json(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"expected_object:{path}")
    return obj


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"row_not_object:{path}:{idx}")
            rows.append(obj)
    return rows


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_materialized(path: str | Path) -> dict[str, Any]:
    data = Path(path)
    meta = data.with_name(data.stem + ".meta.json")
    if not meta.is_file():
        raise ValueError(f"missing_materialization_metadata:{meta}")
    obj = _read_json(meta)
    if obj.get("materialization_status") != "VERIFIED":
        raise ValueError(f"materialization_not_verified:{meta}")
    if obj.get("data_digest") != _sha256(data):
        raise ValueError(f"materialized_digest_mismatch:{data}")
    rows = sum(1 for line in data.read_text(encoding="utf-8").splitlines() if line.strip())
    if obj.get("row_count") != rows:
        raise ValueError(f"materialized_row_count_mismatch:{data}")
    return obj


def _num(row: dict[str, Any], *names: str) -> float | None:
    for name in names:
        if name in row and row[name] not in (None, ""):
            try:
                value = float(row[name])
                if math.isfinite(value):
                    return value
            except (TypeError, ValueError):
                pass
    return None


def _ticker(row: dict[str, Any]) -> str | None:
    for key in ("ticker", "T", "symbol"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def _ts(row: dict[str, Any]) -> int | None:
    value = _num(row, "t", "t_2", "timestamp")
    return int(value) if value is not None else None


def _pct_change(last: float, first: float) -> float | None:
    return last / first - 1.0 if first not in (0, None) else None


def _stdev(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _percentile_ranks(values: dict[str, float], reverse: bool = False) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]), reverse=reverse)
    n = len(ordered)
    if n <= 1:
        return {key: 0.5 for key, _ in ordered}
    ranks: dict[str, float] = {}
    for idx, (key, _) in enumerate(ordered):
        pct = idx / (n - 1)
        ranks[key] = 1.0 - pct if reverse else pct
    return ranks


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    n = len(b)
    aug = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-10:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        aug[col] = [value / div for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [aug[row][j] - factor * aug[col][j] for j in range(n + 1)]
    return [aug[i][-1] for i in range(n)]


def _ols_residual_sum(y: list[float], xs: list[list[float]], tail: int = 20) -> float | None:
    if len(y) < 30 or len(xs) != len(y):
        return None
    p = len(xs[0]) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for yi, row in zip(y, xs):
        design = [1.0] + row
        for i in range(p):
            xty[i] += design[i] * yi
            for j in range(p):
                xtx[i][j] += design[i] * design[j]
    for i in range(1, p):
        xtx[i][i] += 1e-8
    beta = _solve(xtx, xty)
    if beta is None:
        return None
    residuals = []
    for yi, row in zip(y, xs):
        design = [1.0] + row
        residuals.append(yi - sum(beta[i] * design[i] for i in range(p)))
    return sum(residuals[-tail:])


def _history_by_ticker(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ticker = _ticker(row)
        if ticker and _ts(row) is not None and _num(row, "c", "close") is not None:
            out[ticker].append(row)
    for ticker in out:
        out[ticker].sort(key=lambda row: (_ts(row) or 0))
    return dict(out)


def _returns(rows: list[dict[str, Any]]) -> dict[int, float]:
    result: dict[int, float] = {}
    prev: float | None = None
    for row in rows:
        close = _num(row, "c", "close")
        ts = _ts(row)
        if close is None or ts is None:
            continue
        if prev not in (None, 0):
            result[ts] = close / prev - 1.0
        prev = close
    return result


def _momentum(rows: list[dict[str, Any]], days: int) -> float | None:
    closes = [_num(row, "c", "close") for row in rows]
    closes = [value for value in closes if value is not None]
    if len(closes) <= days:
        return None
    return _pct_change(closes[-1], closes[-days - 1])


def _feature_rows(history: dict[str, list[dict[str, Any]]], current: dict[str, dict[str, Any]], tickers: list[str], min_obs: int) -> tuple[list[dict[str, Any]], list[str]]:
    qualified = [ticker for ticker in tickers if len(history.get(ticker, [])) >= min_obs]
    return_maps = {ticker: _returns(history[ticker]) for ticker in qualified}
    all_ts = sorted({ts for ticker in qualified for ts in return_maps[ticker]})
    market_return: dict[int, float] = {}
    for ts in all_ts:
        vals = [return_maps[ticker][ts] for ticker in qualified if ts in return_maps[ticker]]
        if vals:
            market_return[ts] = _mean(vals)
    btc = return_maps.get("X:BTCUSD", {})
    eth = return_maps.get("X:ETHUSD", {})

    features: list[dict[str, Any]] = []
    for ticker in qualified:
        rows = history[ticker]
        ret_map = return_maps[ticker]
        aligned = [ts for ts in sorted(ret_map) if ts in btc and ts in eth and ts in market_return]
        y = [ret_map[ts] for ts in aligned[-60:]]
        xs = [[btc[ts], eth[ts], market_return[ts]] for ts in aligned[-60:]]
        residual = None if ticker in {"X:BTCUSD", "X:ETHUSD"} else _ols_residual_sum(y, xs)
        mom20 = _momentum(rows, 20)
        mom60 = _momentum(rows, 60)
        returns20 = list(ret_map.values())[-20:]
        vol20 = _stdev(returns20) * math.sqrt(365.0) if returns20 else None
        trend_quality = mom20 / vol20 if mom20 is not None and vol20 not in (None, 0) else None
        cutoff = current[ticker]
        volume = _num(cutoff, "v", "volume") or 0.0
        vwap = _num(cutoff, "vw", "vwap")
        close = _num(cutoff, "c", "close")
        open_ = _num(cutoff, "o", "open")
        dollar_volume = volume * (vwap or close or 0.0)
        vwap_pressure = close / vwap - 1.0 if close not in (None, 0) and vwap not in (None, 0) else 0.0
        current_return = close / open_ - 1.0 if close not in (None, 0) and open_ not in (None, 0) else 0.0
        closes = [_num(row, "c", "close") for row in rows[-20:]]
        closes = [v for v in closes if v is not None]
        sma20 = _mean(closes) if closes else None
        above_sma20 = bool(close is not None and sma20 is not None and close > sma20)
        features.append({
            "ticker": ticker,
            "history_observations": len(rows),
            "current_return": current_return,
            "momentum_20": mom20 or 0.0,
            "momentum_60": mom60 or 0.0,
            "realized_vol_20": vol20 or 0.0,
            "trend_quality": trend_quality or 0.0,
            "residual_momentum_20": residual if residual is not None else ((mom20 or 0.0) - _mean([_momentum(history[t], 20) or 0.0 for t in qualified])),
            "dollar_volume": dollar_volume,
            "vwap_pressure": vwap_pressure,
            "above_sma20": above_sma20,
        })
    return features, qualified


def _macro_summary(paths: dict[str, str | None]) -> tuple[dict[str, Any], str, list[str]]:
    families: dict[str, Any] = {}
    limitations: list[str] = []
    available = 0
    for family, path in paths.items():
        if not path:
            limitations.append(f"macro_family_unavailable:{family}")
            continue
        rows = _read_jsonl(path)
        hist = _history_by_ticker(rows)
        moments = {ticker: _momentum(values, 20) for ticker, values in hist.items()}
        moments = {ticker: value for ticker, value in moments.items() if value is not None}
        if not moments:
            limitations.append(f"macro_family_insufficient_history:{family}")
            continue
        available += 1
        families[family] = {"series": len(moments), "median_momentum_20": _median(list(moments.values()))}
        if family == "fx":
            usd_signals = []
            for ticker, value in moments.items():
                code = ticker.split(":", 1)[-1]
                if len(code) >= 6 and code[:3] == "USD":
                    usd_signals.append(value)
                elif len(code) >= 6 and code[3:6] == "USD":
                    usd_signals.append(-value)
            families[family]["usd_factor_20"] = _mean(usd_signals) if usd_signals else None
    coverage = "COMPLETE" if available == 3 else ("DEGRADED" if available else "UNAVAILABLE")
    return {"coverage": coverage, "families": families}, coverage, limitations


def _write_new_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _write_new_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    body = "".join(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the repository-owned deterministic daily crypto research pipeline over verified materialized Massive MCP datasets.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--attempt-id", required=True)
    ap.add_argument("--research-cutoff", required=True)
    ap.add_argument("--crypto-universe", required=True)
    ap.add_argument("--crypto-cutoff", required=True)
    ap.add_argument("--crypto-history", required=True)
    ap.add_argument("--fx-history")
    ap.add_argument("--stock-history")
    ap.add_argument("--index-history")
    ap.add_argument("--data-quality", required=True)
    ap.add_argument("--capability-evaluation", required=True)
    ap.add_argument("--config", default="config/daily-model.json")
    ap.add_argument("--out-dir", default="research/pipeline")
    ap.add_argument("--created-at", help="Fixed forecast-payload creation time for deterministic replay qualification.")
    args = ap.parse_args()

    try:
        cutoff = datetime.fromisoformat(args.research_cutoff.replace("Z", "+00:00"))
        dq = _read_json(args.data_quality)
        caps = _read_json(args.capability_evaluation)
        if dq.get("status") == "BLOCK":
            raise ValueError("data_quality_BLOCK")
        if caps.get("status") == "BLOCKED":
            raise ValueError("capability_evaluation_BLOCKED")
        config = _read_json(args.config)
        for path in [args.crypto_universe, args.crypto_cutoff, args.crypto_history, args.fx_history, args.stock_history, args.index_history]:
            if path:
                _verify_materialized(path)
        universe_rows = _read_jsonl(args.crypto_universe)
        cutoff_rows = _read_jsonl(args.crypto_cutoff)
        history_rows = _read_jsonl(args.crypto_history)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"PIPELINE_BLOCKED:{exc}")
        return 2

    active = set()
    for row in universe_rows:
        ticker = _ticker(row)
        active_value = row.get("active", True)
        active_bool = active_value is True or str(active_value).lower() in {"true", "1", "yes"}
        if ticker and active_bool:
            active.add(ticker)
    excluded = set(config.get("excluded_usd_pairs", []))
    current: dict[str, dict[str, Any]] = {}
    for row in cutoff_rows:
        ticker = _ticker(row)
        if not ticker or not ticker.endswith("USD") or ticker in excluded:
            continue
        if active and ticker not in active:
            continue
        current[ticker] = row
    liquidity = {}
    for ticker, row in current.items():
        volume = _num(row, "v", "volume") or 0.0
        vwap = _num(row, "vw", "vwap") or _num(row, "c", "close") or 0.0
        liquidity[ticker] = volume * vwap
    top_n = int(config.get("eligible_top_n", 25))
    selected = [ticker for ticker, _ in sorted(liquidity.items(), key=lambda item: (item[1], item[0]), reverse=True)[:top_n]]
    for anchor in ("X:BTCUSD", "X:ETHUSD"):
        if anchor in current and anchor not in selected:
            selected.append(anchor)

    history = _history_by_ticker(history_rows)
    features, qualified = _feature_rows(history, current, selected, int(config.get("minimum_history_observations", 60)))
    if len(qualified) < 5 or "X:BTCUSD" not in qualified or "X:ETHUSD" not in qualified:
        print(f"PIPELINE_BLOCKED:insufficient_history_coverage:qualified={len(qualified)}:btc={'X:BTCUSD' in qualified}:eth={'X:ETHUSD' in qualified}")
        return 2

    values = {row["ticker"]: row for row in features}
    med_mom = _median([row["momentum_20"] for row in features])
    rank_inputs = {
        "relative_momentum": {row["ticker"]: row["momentum_20"] - med_mom for row in features},
        "trend_quality": {row["ticker"]: row["trend_quality"] for row in features},
        "residual_momentum": {row["ticker"]: row["residual_momentum_20"] for row in features},
        "liquidity": {row["ticker"]: row["dollar_volume"] for row in features},
        "volatility_quality": {row["ticker"]: -row["realized_vol_20"] for row in features},
    }
    ranks = {name: _percentile_ranks(vals) for name, vals in rank_inputs.items()}
    weights = config["factor_weights"]
    factor_rows = []
    for ticker in qualified:
        score = sum(float(weights[name]) * ranks[name][ticker] for name in weights)
        factor_rows.append({
            "ticker": ticker,
            "score": score,
            "component_ranks": {name: ranks[name][ticker] for name in weights},
        })
    factor_rows.sort(key=lambda row: (row["score"], row["ticker"]), reverse=True)

    breadth = _mean([1.0 if row["current_return"] > 0 else 0.0 for row in features])
    above20 = _mean([1.0 if row["above_sma20"] else 0.0 for row in features])
    dispersion = _stdev([row["current_return"] for row in features])
    total_liq = sum(row["dollar_volume"] for row in features)
    top5 = sum(sorted((row["dollar_volume"] for row in features), reverse=True)[:5])
    concentration = top5 / total_liq if total_liq else 0.0
    btc_mom20 = values["X:BTCUSD"]["momentum_20"]
    btc_leadership = values["X:BTCUSD"]["current_return"] - _median([row["current_return"] for row in features])
    if breadth >= 0.60 and above20 >= 0.60 and btc_mom20 > 0:
        market_state = "RISK_ON"
    elif breadth <= 0.40 and above20 <= 0.40 and btc_mom20 < 0:
        market_state = "RISK_OFF"
    else:
        market_state = "TRANSITION"
    market_state_obj = {
        "state": market_state,
        "breadth_advancing": breadth,
        "above_sma20": above20,
        "return_dispersion": dispersion,
        "top5_dollar_volume_concentration": concentration,
        "btc_leadership": btc_leadership,
        "btc_momentum_20": btc_mom20,
        "assets": len(features),
    }

    macro, macro_coverage, macro_limits = _macro_summary({"fx": args.fx_history, "stocks": args.stock_history, "indices": args.index_history})
    relative_rows = sorted(
        ({"ticker": row["ticker"], "residual_momentum_20": row["residual_momentum_20"], "momentum_20": row["momentum_20"]} for row in features),
        key=lambda row: (row["residual_momentum_20"], row["ticker"]), reverse=True,
    )

    regime_multiplier = float(config["regime_gross_multipliers"][market_state])
    gross_target = float(config.get("research_gross_target", 0.50)) * regime_multiplier
    max_weight = float(config.get("max_research_weight", 0.10))
    positives = [row for row in factor_rows if row["score"] > 0.5] or factor_rows[:5]
    raw = {row["ticker"]: max(row["score"] - 0.5, 0.01) for row in positives}
    denom = sum(raw.values()) or 1.0
    research_weights = {ticker: min(max_weight, gross_target * value / denom) for ticker, value in raw.items()}
    risk = {
        "market_state": market_state,
        "gross_target": gross_target,
        "max_research_weight": max_weight,
        "suggested_research_weights": research_weights,
        "note": "Research-only sizing output; not an execution instruction and not a brokerage action.",
    }

    limitations = list(macro_limits)
    if caps.get("status") == "DEGRADED":
        limitations.extend(caps.get("degradations", []))
    if dq.get("status") == "DEGRADED":
        limitations.append("data_quality_status:DEGRADED")
    status = "DEGRADED" if limitations else "COMPLETE"

    out = Path(args.out_dir) / args.attempt_id
    artifacts = {
        "feature_store": (out / "feature-store.jsonl").as_posix(),
        "market_state": (out / "market-state.json").as_posix(),
        "factors": (out / "factors.json").as_posix(),
        "relative_value": (out / "relative-value.json").as_posix(),
        "macro_regime": (out / "macro-regime.json").as_posix(),
        "ensemble": (out / "ensemble.json").as_posix(),
        "risk": (out / "risk.json").as_posix(),
        "forecast_payload": (out / "forecast-payload.json").as_posix(),
    }
    try:
        _write_new_jsonl(Path(artifacts["feature_store"]), features)
        _write_new_json(Path(artifacts["market_state"]), market_state_obj)
        _write_new_json(Path(artifacts["factors"]), {"weights": weights, "assets": factor_rows})
        _write_new_json(Path(artifacts["relative_value"]), {"assets": relative_rows})
        _write_new_json(Path(artifacts["macro_regime"]), macro)
        _write_new_json(Path(artifacts["ensemble"]), {"assets": factor_rows, "regime_multiplier": regime_multiplier})
        _write_new_json(Path(artifacts["risk"]), risk)
        created_at = args.created_at or datetime.now(cutoff.tzinfo).isoformat().replace("+00:00", "Z")
        forecast_payload = {
            "forecast_id": f"{args.attempt_id}-next-day-v1",
            "run_id": args.run_id,
            "created_at": created_at,
            "research_cutoff": args.research_cutoff,
            "target_horizon": "next UTC-day close",
            "universe": f"top-{top_n} eligible USD-quoted crypto by cutoff-day dollar-volume proxy with >= {config.get('minimum_history_observations', 60)} history observations",
            "predictions": [
                {"asset": row["ticker"], "score": 2.0 * row["score"] - 1.0, "rank_score": row["score"]}
                for row in factor_rows
            ],
            "source_artifacts": [args.data_quality, args.capability_evaluation] + [value for key, value in artifacts.items() if key != "forecast_payload"],
        }
        _write_new_json(Path(artifacts["forecast_payload"]), forecast_payload)
        result = {
            "run_id": args.run_id,
            "attempt_id": args.attempt_id,
            "status": status,
            "research_cutoff": args.research_cutoff,
            "eligible_assets": len(selected),
            "history_qualified_assets": len(qualified),
            "market_state": market_state,
            "macro_coverage": macro_coverage,
            "artifacts": artifacts,
            "limitations": sorted(set(limitations)),
        }
        _write_new_json(out / "pipeline-result.json", result)
    except FileExistsError as exc:
        print(f"IMMUTABLE_CONFLICT:{exc}")
        return 3

    print((out / "pipeline-result.json").as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
