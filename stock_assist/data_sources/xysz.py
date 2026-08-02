"""AmazingData adapter for the Xingyao Shuzhi data source."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from stock_assist.data_sources.contracts import (
    PriceBasis,
    ProviderResult,
    ProviderStatus,
)
from stock_assist.env import load_project_env

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DAILY_KLINE_SCHEMA_VERSION = "daily-ohlcv/v1"
# AmazingData 1.1.8 query_kline hard-codes cq_flag=0. Keep that provider
# semantic explicit instead of asking downstream rules to infer it from prices.
AMAZINGDATA_DAILY_PRICE_BASIS: PriceBasis = "unadjusted"
PRICE_DISCONTINUITY_LIMIT = 0.35


class AmazingDataError(RuntimeError):
    """Raised when AmazingData cannot be configured or queried."""


@dataclass(frozen=True)
class AmazingDataConfig:
    """Connection settings loaded from environment variables."""

    username: str
    password: str
    host: str = "101.230.159.234"
    backup_host: str | None = "140.206.44.234"
    port: int = 8600
    cache_dir: Path = Path("data/amazingdata")
    permission_start: str | None = "2026-05-22"
    permission_end: str | None = "2027-05-22"

    @classmethod
    def from_env(cls) -> "AmazingDataConfig":
        load_project_env()
        missing = [
            name
            for name in ("AD_USERNAME", "AD_PASSWORD")
            if not os.environ.get(name)
        ]
        if missing:
            names = ", ".join(missing)
            raise AmazingDataError(f"Missing required environment variable(s): {names}")

        return cls(
            username=os.environ["AD_USERNAME"],
            password=os.environ["AD_PASSWORD"],
            host=os.environ.get("AD_HOST", "101.230.159.234"),
            backup_host=os.environ.get("AD_BACKUP_HOST", "140.206.44.234"),
            port=int(os.environ.get("AD_PORT", "8600")),
            cache_dir=Path(os.environ.get("AD_CACHE_DIR", "data/amazingdata")),
            permission_start=os.environ.get("AD_PERMISSION_START", "2026-05-22"),
            permission_end=os.environ.get("AD_PERMISSION_END", "2027-05-22"),
        )

    @property
    def hosts(self) -> list[str]:
        return [host for host in [self.host, self.backup_host] if host]

    @property
    def permission_days_remaining(self) -> int | None:
        if not self.permission_end:
            return None
        try:
            end_date = datetime.strptime(self.permission_end, "%Y-%m-%d").date()
        except ValueError:
            return None
        return (end_date - date.today()).days


class AmazingDataClient:
    """Small, lazy wrapper around the AmazingData SDK."""

    def __init__(self, config: AmazingDataConfig | None = None) -> None:
        self.config = config or AmazingDataConfig.from_env()
        self._ad: Any | None = None
        self._base_data: Any | None = None
        self._info_data: Any | None = None
        self._market_data: Any | None = None
        self._calendar: list[int] | None = None
        self._logged_in = False
        self._active_host: str | None = None
        self._verbose = os.environ.get("AD_VERBOSE", "").lower() in {"1", "true", "yes"}

    def _call_sdk(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        if self._verbose:
            return func(*args, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return func(*args, **kwargs)

    def _host_reachable(self, host: str) -> bool:
        try:
            with socket.create_connection((host, self.config.port), timeout=3):
                return True
        except OSError:
            return False

    def login(self) -> None:
        """Authenticate once and initialize the SDK module."""

        if self._logged_in:
            return
        try:
            import AmazingData as ad
        except ImportError as exc:
            raise AmazingDataError(
                "AmazingData is not installed. Install tgw first, then AmazingData."
            ) from exc

        errors: list[str] = []
        for host in self.config.hosts:
            if not self._host_reachable(host):
                errors.append(f"{host}: TCP {self.config.port} unreachable")
                continue
            try:
                self._call_sdk(
                    ad.login,
                    username=self.config.username,
                    password=self.config.password,
                    host=host,
                    port=self.config.port,
                )
                self._active_host = host
                break
            except Exception as exc:
                errors.append(f"{host}: {exc}")
        else:
            raise AmazingDataError("AmazingData login failed for all configured hosts: " + "; ".join(errors))

        self._ad = ad
        self._logged_in = True

    def logout(self) -> None:
        """Best-effort logout for long-running scripts."""

        if self._ad is not None and self._logged_in:
            logout = getattr(self._ad, "logout", None)
            if callable(logout):
                self._call_sdk(logout, self.config.username)
        self._logged_in = False

    @property
    def ad(self) -> Any:
        self.login()
        return self._ad

    @property
    def base_data(self) -> Any:
        if self._base_data is None:
            self._base_data = self._call_sdk(self.ad.BaseData)
        return self._base_data

    @property
    def info_data(self) -> Any:
        if self._info_data is None:
            self._info_data = self._call_sdk(self.ad.InfoData)
        return self._info_data

    @property
    def calendar(self) -> list[int]:
        if self._calendar is None:
            self._calendar = list(self._call_sdk(self.base_data.get_calendar))
        return self._calendar

    @property
    def market_data(self) -> Any:
        if self._market_data is None:
            self._market_data = self._call_sdk(self.ad.MarketData, self.calendar)
        return self._market_data

    def get_code_list(self, security_type: str = "EXTRA_STOCK_A") -> list[str]:
        return list(self._call_sdk(self.base_data.get_code_list, security_type=security_type))

    def get_code_info(self, security_type: str = "EXTRA_STOCK_A") -> Any:
        return self._call_sdk(self.base_data.get_code_info, security_type=security_type)

    def get_stock_basic(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(self.info_data.get_stock_basic, list(codes))

    def query_daily_kline(
        self,
        codes: Iterable[str],
        begin_date: int,
        end_date: int,
    ) -> dict[str, Any]:
        period = self.ad.constant.Period.day.value
        return self._call_sdk(
            self.market_data.query_kline,
            code_list=list(codes),
            begin_date=begin_date,
            end_date=end_date,
            period=period,
        )

    def query_daily_kline_result(
        self,
        codes: Iterable[str],
        begin_date: int,
        end_date: int,
    ) -> ProviderResult[dict[str, pd.DataFrame]]:
        """Query and normalize daily bars before they leave the adapter."""

        requested_codes = list(codes)
        raw = self.query_daily_kline(requested_codes, begin_date, end_date)
        return normalise_daily_kline_result(
            raw,
            requested_codes=requested_codes,
            fetched_at=datetime.now(tz=SHANGHAI_TZ),
            expected_trade_date=_date_from_yyyymmdd(end_date),
        )

    def query_snapshot(
        self,
        codes: Iterable[str],
        begin_date: int,
        end_date: int,
        *,
        timeout: float | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._call_sdk(
            self.market_data.query_snapshot,
            code_list=list(codes),
            begin_date=begin_date,
            end_date=end_date,
            **kwargs,
        )

    def get_future_code_list(self, security_type: str = "ZJ_FUTURE") -> list[str]:
        return list(self._call_sdk(self.base_data.get_future_code_list, security_type=security_type))

    def get_fund_share(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(
            self.info_data.get_fund_share,
            list(codes),
            local_path=str(self.config.cache_dir.resolve()),
            is_local=False,
        )

    def get_etf_pcf(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(self.base_data.get_etf_pcf, list(codes))

    def get_income(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(self.info_data.get_income, list(codes))

    def get_balance_sheet(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(self.info_data.get_balance_sheet, list(codes))

    def get_cash_flow(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(self.info_data.get_cash_flow, list(codes))

    def get_profit_notice(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(
            self.info_data.get_profit_notice,
            list(codes),
            local_path=str(self.config.cache_dir.resolve()),
            is_local=False,
        )

    def get_equity_structure(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(
            self.info_data.get_equity_structure,
            list(codes),
            local_path=str(self.config.cache_dir.resolve()),
            is_local=False,
        )

    def get_index_constituent(self, codes: Iterable[str]) -> Any:
        return self._call_sdk(
            self.info_data.get_index_constituent,
            list(codes),
            local_path=str(self.config.cache_dir.resolve()),
            is_local=False,
        )

    def doctor(self, code: str) -> dict[str, Any]:
        """Run a low-cost connectivity check against login, calendar, and one stock."""

        self.login()
        latest_calendar = self.calendar[-5:]
        code_info = self.get_code_info()
        code_count = len(code_info)
        basic = self.get_stock_basic([code])

        return {
            "ok": True,
            "host": self._active_host or self.config.host,
            "configured_hosts": self.config.hosts,
            "port": self.config.port,
            "permission_start": self.config.permission_start,
            "permission_end": self.config.permission_end,
            "permission_days_remaining": self.config.permission_days_remaining,
            "calendar_tail": latest_calendar,
            "code_info_rows": code_count,
            "sample_code": code,
            "stock_basic_rows": len(basic),
            "stock_basic_columns": list(getattr(basic, "columns", []))[:12],
        }


def normalise_daily_kline_result(
    raw: object,
    *,
    requested_codes: Iterable[str],
    fetched_at: datetime | None = None,
    expected_trade_date: date | None = None,
    source_time: datetime | None = None,
) -> ProviderResult[dict[str, pd.DataFrame]]:
    """Turn the AmazingData response into canonical OHLCV.

    ``source_time`` is reserved for an explicit provider response timestamp.
    Daily bar dates remain in ``trade_date`` and do not imply a source time.
    """

    fetched = _aware_shanghai(fetched_at or datetime.now(tz=SHANGHAI_TZ))
    explicit_source_time = (
        _aware_shanghai(source_time) if source_time is not None else None
    )
    codes = tuple(dict.fromkeys(str(code) for code in requested_codes))
    frames: dict[str, pd.DataFrame] = {}
    gaps: list[str] = []
    errors: list[str] = []
    trade_dates: list[date] = []

    ambiguous_frame = (
        isinstance(raw, pd.DataFrame)
        and len(codes) > 1
        and "code" not in raw.columns
    )
    if ambiguous_frame:
        errors.append("request:ambiguous_frame_without_code")
        frames.update({code: _empty_daily_frame() for code in codes})
    else:
        for code in codes:
            provider_frame = _provider_frame_for_code(raw, code)
            if provider_frame.empty:
                frames[code] = _empty_daily_frame()
                gaps.append(f"{code}:missing_series")
                continue
            frame, frame_gaps, frame_errors = _normalise_daily_frame(
                provider_frame,
                code=code,
                expected_trade_date=expected_trade_date,
            )
            frames[code] = frame
            gaps.extend(frame_gaps)
            errors.extend(frame_errors)
            if not frame.empty:
                trade_dates.append(frame["trade_date"].iloc[-1].date())

    if not codes:
        errors.append("request:missing_codes")
    if len(set(trade_dates)) > 1:
        gaps.append(
            "batch:trade_date_mismatch:"
            + ",".join(sorted(value.isoformat() for value in set(trade_dates)))
        )
    if explicit_source_time is not None and explicit_source_time > fetched:
        errors.append("request:source_time_after_fetched_at")
        explicit_source_time = None

    latest_trade_date = max(trade_dates) if trade_dates else None
    status = _provider_status(frames, gaps, errors)
    return ProviderResult(
        provider="amazingdata",
        schema_version=DAILY_KLINE_SCHEMA_VERSION,
        source_time=explicit_source_time,
        fetched_at=fetched,
        trade_date=latest_trade_date,
        status=status,
        gaps=tuple(gaps),
        errors=tuple(errors),
        price_basis=AMAZINGDATA_DAILY_PRICE_BASIS,
        data=frames,
    )


def daily_kline_result_for_code(
    result: ProviderResult[dict[str, pd.DataFrame]],
    code: str,
) -> ProviderResult[pd.DataFrame]:
    """Narrow a batch contract without dropping its fault context."""

    frame = result.data.get(code, _empty_daily_frame())
    prefixes = (f"{code}:", "batch:", "request:")
    gaps = tuple(item for item in result.gaps if item.startswith(prefixes))
    errors = tuple(item for item in result.errors if item.startswith(prefixes))
    fetched_at = _aware_shanghai(result.fetched_at)
    source_time = (
        _aware_shanghai(result.source_time)
        if result.source_time is not None
        else None
    )
    if source_time is not None and source_time > fetched_at:
        errors += ("request:source_time_after_fetched_at",)
        source_time = None
    trade_date = (
        frame["trade_date"].iloc[-1].date()
        if not frame.empty
        else None
    )
    if errors:
        status: ProviderStatus = "invalid"
    elif frame.empty:
        status = "empty"
    elif any(":price_discontinuity:" in item for item in gaps):
        status = "quarantined"
    elif gaps:
        status = "partial"
    else:
        status = "ok"
    return ProviderResult(
        provider=result.provider,
        schema_version=result.schema_version,
        source_time=source_time,
        fetched_at=fetched_at,
        trade_date=trade_date,
        status=status,
        gaps=gaps,
        errors=errors,
        price_basis=result.price_basis,
        data=frame,
    )


def _provider_frame_for_code(raw: object, code: str) -> pd.DataFrame:
    if isinstance(raw, dict):
        value = next(
            (raw[alias] for alias in _code_aliases(code) if alias in raw),
            None,
        )
        return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()
    if isinstance(raw, pd.DataFrame):
        if "code" not in raw.columns:
            return raw.copy()
        expected = _canonical_code(code)
        matches = raw["code"].map(_canonical_code) == expected
        return raw.loc[matches].copy()
    return pd.DataFrame()


def _normalise_daily_frame(
    frame: pd.DataFrame,
    *,
    code: str,
    expected_trade_date: date | None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    gaps: list[str] = []
    errors: list[str] = []
    expected_code = _canonical_code(code)
    if "code" in frame.columns:
        inner_codes = frame["code"].map(_canonical_code)
        if inner_codes.isna().any() or set(inner_codes) != {expected_code}:
            errors.append(f"{code}:code_mismatch")
            return _empty_daily_frame(), gaps, errors
    required = ("kline_time", "open", "high", "low", "close")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        errors.append(f"{code}:missing_fields:{','.join(missing)}")
        return _empty_daily_frame(), gaps, errors

    result = pd.DataFrame(
        {
            "code": (
                pd.Series(expected_code, index=frame.index, dtype="object")
            ),
            "trade_date": pd.to_datetime(frame["kline_time"], errors="coerce"),
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "volume": (
                pd.to_numeric(frame["volume"], errors="coerce")
                if "volume" in frame.columns
                else pd.Series(float("nan"), index=frame.index)
            ),
            "amount": (
                pd.to_numeric(frame["amount"], errors="coerce")
                if "amount" in frame.columns
                else pd.Series(float("nan"), index=frame.index)
            ),
        }
    )
    invalid_required = result[["trade_date", "open", "high", "low", "close"]].isna().any(axis=1)
    positive_prices = (result[["open", "high", "low", "close"]] > 0).all(axis=1)
    valid_envelope = (
        (result["high"] >= result[["open", "close"]].max(axis=1))
        & (result["low"] <= result[["open", "close"]].min(axis=1))
        & (result["high"] >= result["low"])
    )
    invalid = invalid_required | ~positive_prices | ~valid_envelope
    if invalid.any():
        errors.append(f"{code}:invalid_ohlc_rows:{int(invalid.sum())}")
        result = result.loc[~invalid].copy()

    if result.empty:
        return _empty_daily_frame(), gaps, errors
    if not result["trade_date"].is_monotonic_increasing:
        gaps.append(f"{code}:timestamps_reordered")
    result = result.sort_values("trade_date", kind="stable")
    duplicate_count = int(result["trade_date"].duplicated(keep="last").sum())
    if duplicate_count:
        gaps.append(f"{code}:duplicate_trade_dates:{duplicate_count}")
        result = result.drop_duplicates("trade_date", keep="last")

    latest_trade_date = result["trade_date"].iloc[-1].date()
    if expected_trade_date is not None and latest_trade_date < expected_trade_date:
        gaps.append(
            f"{code}:stale_trade_date:{latest_trade_date.isoformat()}"
            f"<{expected_trade_date.isoformat()}"
        )
    elif expected_trade_date is not None and latest_trade_date > expected_trade_date:
        errors.append(
            f"{code}:future_trade_date:{latest_trade_date.isoformat()}"
            f">{expected_trade_date.isoformat()}"
        )

    largest_gap = float(result["close"].pct_change().abs().dropna().max())
    if largest_gap > PRICE_DISCONTINUITY_LIMIT:
        gaps.append(f"{code}:price_discontinuity:{largest_gap:.6f}")
    return result.reset_index(drop=True), gaps, errors


def _provider_status(
    frames: dict[str, pd.DataFrame],
    gaps: list[str],
    errors: list[str],
) -> ProviderStatus:
    if errors:
        return "invalid"
    if not frames or all(frame.empty for frame in frames.values()):
        return "empty"
    if any(":price_discontinuity:" in item for item in gaps):
        return "quarantined"
    if gaps:
        return "partial"
    return "ok"


def _empty_daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["code", "trade_date", "open", "high", "low", "close", "volume", "amount"]
    )


def _aware_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def _canonical_code(value: object) -> str:
    return str(value).strip().upper().replace("_", ".")


def _code_aliases(code: str) -> tuple[str, ...]:
    canonical = _canonical_code(code)
    return tuple(dict.fromkeys((code, canonical, canonical.replace(".", "_"))))


def _date_from_yyyymmdd(value: int) -> date:
    text = str(value)
    return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AmazingData data source tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check AmazingData connectivity")
    doctor.add_argument("--code", default="000001.SZ", help="sample stock code")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    client = AmazingDataClient()

    try:
        if args.command == "doctor":
            result = client.doctor(args.code)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    finally:
        client.logout()

    raise AmazingDataError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
