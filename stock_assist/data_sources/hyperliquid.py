"""Read-only Hyperliquid Info API helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


INFO_URL = "https://api.hyperliquid.xyz/info"
HYPURRSCAN_API_URL = "https://test.hypurrscan.io"
DEFAULT_TIMEOUT = 12


class HyperliquidError(RuntimeError):
    """Raised when the Hyperliquid read-only API cannot return usable data."""


@dataclass(frozen=True)
class PerpMarket:
    coin: str
    mark_px: float | None
    prev_day_px: float | None
    funding: float | None
    open_interest: float | None
    day_notional_volume: float | None

    @property
    def change_24h_pct(self) -> float | None:
        if self.mark_px is None or self.prev_day_px in (None, 0):
            return None
        return (self.mark_px - self.prev_day_px) / self.prev_day_px * 100


@dataclass(frozen=True)
class PerpPosition:
    coin: str
    side: str
    size: float | None
    entry_px: float | None
    liquidation_px: float | None
    position_value: float | None
    unrealized_pnl: float | None
    return_on_equity: float | None
    leverage: str
    margin_used: float | None
    mark_px: float | None

    @property
    def liquidation_distance_pct(self) -> float | None:
        if self.mark_px in (None, 0) or self.liquidation_px is None:
            return None
        if self.side == "long":
            return (self.mark_px - self.liquidation_px) / self.mark_px * 100
        if self.side == "short":
            return (self.liquidation_px - self.mark_px) / self.mark_px * 100
        return None


@dataclass(frozen=True)
class MarketPosition:
    user: str
    coin: str
    side: str
    size: float | None
    abs_size: float | None
    entry_px: float | None
    liquidation_px: float | None
    notional: float | None
    distance_pct: float | None
    leverage: float | None


def fetch_market_snapshot(dex: str = "") -> dict[str, PerpMarket]:
    payload = _post_info({"type": "metaAndAssetCtxs", "dex": dex})
    if not isinstance(payload, list) or len(payload) != 2:
        raise HyperliquidError("Unexpected metaAndAssetCtxs response shape.")

    meta, contexts = payload
    universe = meta.get("universe", []) if isinstance(meta, dict) else []
    markets: dict[str, PerpMarket] = {}
    for item, ctx in zip(universe, contexts):
        if not isinstance(item, dict) or not isinstance(ctx, dict):
            continue
        coin = str(item.get("name", "")).upper()
        if not coin:
            continue
        markets[coin] = PerpMarket(
            coin=coin,
            mark_px=_to_float(ctx.get("markPx")),
            prev_day_px=_to_float(ctx.get("prevDayPx")),
            funding=_to_float(ctx.get("funding")),
            open_interest=_to_float(ctx.get("openInterest")),
            day_notional_volume=_to_float(ctx.get("dayNtlVlm")),
        )
    return markets


def fetch_account_state(address: str, dex: str = "") -> dict[str, Any]:
    if not address.startswith("0x"):
        raise HyperliquidError(f"Hyperliquid address must start with 0x: {address}")
    payload = _post_info({"type": "clearinghouseState", "user": address, "dex": dex})
    if not isinstance(payload, dict):
        raise HyperliquidError("Unexpected clearinghouseState response shape.")
    return payload


def parse_positions(state: dict[str, Any], markets: dict[str, PerpMarket]) -> list[PerpPosition]:
    positions: list[PerpPosition] = []
    for asset_position in state.get("assetPositions", []):
        raw = asset_position.get("position", {}) if isinstance(asset_position, dict) else {}
        coin = str(raw.get("coin", "")).upper()
        size = _to_float(raw.get("szi"))
        side = "flat"
        if size is not None and size > 0:
            side = "long"
        elif size is not None and size < 0:
            side = "short"
        leverage_payload = raw.get("leverage") if isinstance(raw.get("leverage"), dict) else {}
        leverage = ""
        if leverage_payload:
            leverage = f"{leverage_payload.get('type', '')} {leverage_payload.get('value', '')}x".strip()
        positions.append(
            PerpPosition(
                coin=coin,
                side=side,
                size=abs(size) if size is not None else None,
                entry_px=_to_float(raw.get("entryPx")),
                liquidation_px=_to_float(raw.get("liquidationPx")),
                position_value=_to_float(raw.get("positionValue")),
                unrealized_pnl=_to_float(raw.get("unrealizedPnl")),
                return_on_equity=_to_float(raw.get("returnOnEquity")),
                leverage=leverage,
                margin_used=_to_float(raw.get("marginUsed")),
                mark_px=markets.get(coin).mark_px if coin in markets else None,
            )
        )
    return positions


def fetch_top_positions(market: str, limit: int = 25, side: str = "all") -> list[MarketPosition]:
    payload = _get_hypurrscan(
        f"/positions/top/{market}",
        {"limit": str(_clamp_limit(limit)), "side": side},
    )
    rows = payload.get("positions", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise HyperliquidError("Unexpected top positions response shape.")
    return [_parse_market_position(row) for row in rows if isinstance(row, dict)]


def fetch_liquidation_risk(
    market: str,
    limit: int = 25,
    side: str = "all",
    min_notional: float | None = None,
    max_distance_pct: float | None = None,
) -> list[MarketPosition]:
    params = {"limit": str(_clamp_limit(limit)), "side": side}
    if min_notional is not None:
        params["min_notional"] = str(min_notional)
    if max_distance_pct is not None:
        params["max_distance_pct"] = str(max_distance_pct)
    payload = _get_hypurrscan(f"/positions/liquidation-risk/{market}", params)
    if not isinstance(payload, dict):
        raise HyperliquidError("Unexpected liquidation-risk response shape.")
    rows = payload.get("largest_under_threshold") or payload.get("closest") or []
    if not isinstance(rows, list):
        raise HyperliquidError("Unexpected liquidation-risk rows shape.")
    return [_parse_market_position(row) for row in rows if isinstance(row, dict)]


def _post_info(body: dict[str, Any]) -> Any:
    try:
        response = requests.post(INFO_URL, json=body, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HyperliquidError(f"Hyperliquid API request failed: {exc}") from exc
    except ValueError as exc:
        raise HyperliquidError("Hyperliquid API returned non-JSON data.") from exc


def _get_hypurrscan(path: str, params: dict[str, str]) -> Any:
    try:
        response = requests.get(f"{HYPURRSCAN_API_URL}{path}", params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HyperliquidError(f"HypurrScan API request failed: {exc}") from exc
    except ValueError as exc:
        raise HyperliquidError("HypurrScan API returned non-JSON data.") from exc


def _parse_market_position(row: dict[str, Any]) -> MarketPosition:
    size = _scaled_float(row.get("size"))
    abs_size = _scaled_float(row.get("abs_size"))
    return MarketPosition(
        user=str(row.get("user", "")).lower(),
        coin=str(row.get("coin", "")).upper(),
        side=str(row.get("side", "")),
        size=size,
        abs_size=abs_size,
        entry_px=_scaled_float(row.get("entry_price")),
        liquidation_px=_scaled_float(row.get("liquidation_price")),
        notional=_scaled_float(row.get("notional")),
        distance_pct=_scaled_float(row.get("distance_pct")),
        leverage=_scaled_leverage(row.get("leverage")),
    )


def _scaled_float(value: Any) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return parsed / 1_000_000


def _scaled_leverage(value: Any) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return parsed / 1_000_000 if parsed > 1_000 else parsed


def _clamp_limit(limit: int) -> int:
    return max(1, min(1000, int(limit)))


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
