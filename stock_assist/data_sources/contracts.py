"""Typed, provider-neutral results emitted by data-source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, Literal, TypeVar

T = TypeVar("T")

ProviderStatus = Literal["ok", "partial", "quarantined", "invalid", "empty"]
PriceBasis = Literal[
    "unadjusted",
    "forward_adjusted",
    "backward_adjusted",
    "not_applicable",
    "unknown",
]


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    """Normalized data plus the minimum context needed to trust or block it."""

    provider: str
    schema_version: str
    source_time: datetime | None
    fetched_at: datetime
    trade_date: date | None
    status: ProviderStatus
    gaps: tuple[str, ...]
    errors: tuple[str, ...]
    price_basis: PriceBasis
    data: T
