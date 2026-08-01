"""AmazingData adapter for the Xingyao Shuzhi data source."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import socket
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from stock_assist.env import load_project_env


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
