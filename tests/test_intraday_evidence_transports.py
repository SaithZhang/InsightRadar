from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp import Client, StdioServerParameters, stdio_client
from pydantic import ValidationError

from stock_assist.intraday.evidence_cli import parse_trade_rows
from stock_assist.intraday.evidence_contracts import EvidenceEnvelope
from stock_assist.intraday.mcp_server import TradeRequest, create_server

SHANGHAI = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StubEvidenceService:
    def _result(self, data: dict[str, object]) -> EvidenceEnvelope[dict[str, object]]:
        now = datetime(2026, 8, 7, 10, 45, tzinfo=SHANGHAI)
        return EvidenceEnvelope(
            schema_version="intraday-evidence/v1",
            status="ok",
            reason=None,
            source_time=now,
            fetched_at=now,
            stale_seconds=0,
            data=data,
            provenance=(),
        )

    def get_intraday(self, symbol: str, trade_date: date, *, as_of: object = None):
        return self._result(
            {
                "symbol": symbol,
                "qualified_symbol": f"{symbol}.SH",
                "name": "Synthetic ETF",
                "market": "SH",
                "trade_date": trade_date.isoformat(),
                "source": "fixture",
                "pre_close": 4.0,
                "open": 4.0,
                "last": 4.1,
                "high": 4.2,
                "low": 3.9,
                "day_pct": 2.5,
                "vwap": 4.05,
                "return_5m": 0.2,
                "return_15m": 0.5,
                "return_30m": 0.8,
                "distance_to_vwap_pct": 1.2,
                "distance_to_high_pct": -2.4,
                "volume_acceleration": 1.1,
                "minutes": [],
                "amount_unit": "CNY",
                "volume_unit": "share",
            }
        )

    def get_intraday_compare(self, symbols: object, *, benchmark: str, trade_date: date, as_of: object = None):
        return self._result(
            {
                "trade_date": trade_date.isoformat(),
                "requested_time": None,
                "benchmark": benchmark,
                "rows": [],
            }
        )

    def get_market_amount_compare(self, trade_date: date, *, as_of: object = None):
        return self._result(
            {
                "market": "CN_A",
                "trade_date": trade_date.isoformat(),
                "previous_trade_date": "2026-08-06",
                "time": "10:10",
                "today_amount": 100.0,
                "previous_day_same_time_amount": 90.0,
                "delta": 10.0,
                "delta_pct": 11.111,
            }
        )

    def review_trades(self, trades: object, *, benchmark: str):
        return self._result({"trades": [], "summary": {"trade_count": len(trades)}})


class McpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_exposes_only_four_read_only_tools(self) -> None:
        server = create_server(StubEvidenceService())  # type: ignore[arg-type]
        async with Client(server) as client:
            listed = await client.list_tools()
        self.assertEqual(
            [tool.name for tool in listed.tools],
            [
                "get_intraday",
                "get_intraday_compare",
                "get_market_amount_compare",
                "review_trades",
            ],
        )
        self.assertTrue(all(tool.annotations and tool.annotations.read_only_hint for tool in listed.tools))
        self.assertFalse(any(tool.name in {"buy", "sell", "place_order", "cancel_order"} for tool in listed.tools))
        for tool in listed.tools:
            assert tool.output_schema is not None
            self.assertIn("status", tool.output_schema["properties"])
            self.assertIn("provenance", tool.output_schema["properties"])
            self.assertIn("stale_seconds", tool.output_schema["properties"])
            self.assertIn("data", tool.output_schema["properties"])
        compare_schema = next(item.input_schema for item in listed.tools if item.name == "get_intraday_compare")
        review_schema = next(item.input_schema for item in listed.tools if item.name == "review_trades")
        self.assertEqual(compare_schema["properties"]["symbols"]["maxItems"], 20)
        self.assertEqual(review_schema["properties"]["trades"]["maxItems"], 100)

    async def test_tool_returns_structured_json(self) -> None:
        server = create_server(StubEvidenceService())  # type: ignore[arg-type]
        async with Client(server) as client:
            result = await client.call_tool(
                "get_intraday",
                {"symbol": "588200", "date": "2026-08-07", "time": "10:41"},
            )
        self.assertEqual(result.structured_content["status"], "ok")
        self.assertEqual(result.structured_content["trade_authority"], "none")
        self.assertEqual(result.structured_content["data"]["symbol"], "588200")

    async def test_review_trade_input_schema_and_parsing(self) -> None:
        server = create_server(StubEvidenceService())  # type: ignore[arg-type]
        async with Client(server) as client:
            result = await client.call_tool(
                "review_trades",
                {
                    "benchmark": "000688",
                    "trades": [
                        {
                            "trade_date": "2026-08-07",
                            "time": "10:11:10",
                            "symbol": "510300",
                            "side": "sell",
                            "quantity": 123,
                            "price": 4.123,
                        }
                    ],
                },
            )
        self.assertEqual(result.structured_content["data"]["summary"]["trade_count"], 1)

    def test_trade_schema_rejects_non_finite_numbers(self) -> None:
        with self.assertRaises(ValidationError):
            TradeRequest(
                trade_date="2026-08-07",
                time="10:11:10",
                symbol="510300",
                side="sell",
                quantity=float("inf"),
                price=4.123,
            )


class TradeInputParsingTests(unittest.TestCase):
    def test_default_date_is_allowed_but_missing_is_not_synthetic(self) -> None:
        rows = [
            {
                "time": "10:12:20",
                "symbol": "510300",
                "side": "sell",
                "quantity": 123,
                "price": 4.123,
            }
        ]
        parsed = parse_trade_rows(rows, default_date=date(2026, 8, 7))
        self.assertEqual(parsed[0].trade_date, date(2026, 8, 7))
        with self.assertRaisesRegex(ValueError, "missing trade_date"):
            parse_trade_rows(rows)

    def test_non_finite_trade_numbers_are_rejected(self) -> None:
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be finite"):
                parse_trade_rows(
                    [
                        {
                            "trade_date": "2026-08-07",
                            "time": "10:11:10",
                            "symbol": "510300",
                            "side": "buy",
                            "quantity": value,
                            "price": 4.123,
                        }
                    ]
                )


class ProcessTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_subprocess_lists_only_read_only_tools(self) -> None:
        transport = stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "stock_assist.intraday.mcp_server", "--transport", "stdio"],
                cwd=PROJECT_ROOT,
            )
        )
        async with Client(transport, read_timeout_seconds=5) as client:
            listed = await client.list_tools()
        self.assertEqual(len(listed.tools), 4)
        self.assertTrue(all(item.annotations and item.annotations.read_only_hint for item in listed.tools))

    async def test_streamable_http_process_lists_tools(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        command = [
            sys.executable,
            "-m",
            "stock_assist.intraday.mcp_server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--endpoint",
            "/mcp",
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            for _ in range(50):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                self.fail(f"HTTP MCP server did not bind; exit_code={process.returncode}")
            async with Client(
                f"http://127.0.0.1:{port}/mcp",
                read_timeout_seconds=5,
            ) as client:
                listed = await client.list_tools()
            self.assertEqual(len(listed.tools), 4)
        finally:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5)


class CliProcessTests(unittest.TestCase):
    def test_integrated_help_and_weekend_json(self) -> None:
        help_result = subprocess.run(
            [sys.executable, "-m", "stock_assist.cli", "intraday-evidence", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("{get,compare,amount,review}", help_result.stdout)

        json_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "stock_assist.cli",
                "intraday-evidence",
                "get",
                "588200",
                "--date",
                "2026-08-08",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual((payload["status"], payload["reason"]), ("no_data", "non_trading_day"))


if __name__ == "__main__":
    unittest.main()
