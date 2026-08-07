"""Bounded symbol registry for the intraday evidence layer."""

from __future__ import annotations

import re

from stock_assist.intraday.evidence_contracts import InstrumentRef

_BENCHMARKS: dict[str, tuple[str, str]] = {
    "000688": ("SH", "科创50"),
    "000001": ("SH", "上证指数"),
    "000300": ("SH", "沪深300"),
    "399006": ("SZ", "创业板指"),
    "399001": ("SZ", "深证成指"),
}
_BENCHMARK_ALIASES = {
    "科创50": "000688",
    "上证指数": "000001",
    "沪深300": "000300",
    "创业板": "399006",
    "创业板指": "399006",
    "深证成指": "399001",
}


def resolve_instrument(symbol: str, *, benchmark: bool = False) -> InstrumentRef:
    """Resolve a stock, ETF, or bounded benchmark without guessing ambiguity."""

    raw = str(symbol or "").strip().upper()
    raw = _BENCHMARK_ALIASES.get(raw, raw)
    code, explicit_market = _split_symbol(raw)
    if code in _BENCHMARKS and (benchmark or explicit_market == _BENCHMARKS[code][0]):
        market, name = _BENCHMARKS[code]
        if explicit_market and explicit_market != market:
            raise ValueError(f"benchmark_market_mismatch:{symbol}")
        return _instrument(code, market, "index", name)
    if benchmark:
        raise ValueError(f"unsupported_benchmark:{symbol}")
    if code in _BENCHMARKS and explicit_market is None:
        qualified = benchmark_registry()[code]
        raise ValueError(
            f"ambiguous_symbol:{code}; use an explicit stock suffix or index {qualified}"
        )
    market = explicit_market or _market_from_code(code)
    kind = "etf" if code.startswith(("5", "159")) else "stock"
    return _instrument(code, market, kind, None)


def resolve_benchmark(symbol: str) -> InstrumentRef:
    return resolve_instrument(symbol, benchmark=True)


def _split_symbol(raw: str) -> tuple[str, str | None]:
    if re.fullmatch(r"\d{6}", raw):
        return raw, None
    match = re.fullmatch(r"(?:(SH|SZ)[.]?)?(\d{6})(?:[.](SH|SZ))?", raw)
    if not match:
        raise ValueError(f"unsupported_symbol:{raw or 'empty'}")
    prefix, code, suffix = match.groups()
    if prefix and suffix and prefix != suffix:
        raise ValueError(f"symbol_market_mismatch:{raw}")
    return code, suffix or prefix


def _market_from_code(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("0", "2", "3", "159")):
        return "SZ"
    raise ValueError(f"unsupported_a_share_market:{code}")


def _instrument(
    code: str,
    market: str,
    kind: str,
    name: str | None,
) -> InstrumentRef:
    if market not in {"SH", "SZ"}:
        raise ValueError(f"unsupported_market:{market}")
    return InstrumentRef(
        code=code,
        qualified_symbol=f"{code}.{market}",
        market=market,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        eastmoney_secid=f"{'1' if market == 'SH' else '0'}.{code}",
        tencent_symbol=f"{market.lower()}{code}",
        display_name=name,
    )


def benchmark_registry() -> dict[str, str]:
    return {code: f"{code}.{market}" for code, (market, _) in _BENCHMARKS.items()}
