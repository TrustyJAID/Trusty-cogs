from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Quote:
    price: float
    volume_24h: float
    percent_change_1h: float
    percent_change_24h: float
    percent_change_7d: float
    percent_change_30d: float
    percent_change_60d: float
    percent_change_90d: float
    market_cap: float
    last_updated: datetime

    @classmethod
    def from_json(cls, data: Dict[Any, Any]) -> Quote:
        last_updated = datetime.now(timezone.utc)
        if "last_updated" in data:
            last_updated = datetime.strptime(data["last_updated"], "%Y-%m-%dT%H:%M:%S.000Z")
        return cls(
            price=data.get("price", 0.0),
            volume_24h=data.get("volume_24h", 0.0),
            percent_change_1h=data.get("percent_change_1h", 0.0),
            percent_change_24h=data.get("percent_change_24h", 0.0),
            percent_change_7d=data.get("percent_change_7d", 0.0),
            percent_change_30d=data.get("percent_change_30d", 0.0),
            percent_change_60d=data.get("percent_change_60d", 0.0),
            percent_change_90d=data.get("percent_change_90d", 0.0),
            market_cap=data.get("market_cap", 0.0),
            last_updated=last_updated,
        )


@dataclass
class CoinBase:
    id: int
    name: str
    symbol: str
    slug: str
    rank: int
    is_active: int
    first_historical_data: datetime
    last_historical_data: datetime
    platform: Optional[Dict[Any, Any]]

    @classmethod
    def from_json(cls, data: Dict[Any, Any]) -> CoinBase:
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            symbol=data.get("symbol", ""),
            slug=data.get("slug", ""),
            rank=data.get("rank", 0),
            is_active=data.get("is_active", 0),
            first_historical_data=data.get("first_historical_data", 0),
            last_historical_data=data.get("last_historical_data", 0),
            platform=data.get("platform", {}),
        )


@dataclass
class Coin:
    id: int
    name: str
    symbol: str
    slug: str
    num_market_pairs: int
    date_added: datetime
    tags: List[str]
    max_supply: Optional[int]
    circulating_supply: float
    total_supply: float
    platform: Optional[Dict[Any, Any]]
    cmc_rank: int
    last_updated: datetime
    quote: Dict[str, Quote]

    @classmethod
    def from_json(cls, data: Dict[Any, Any]) -> Coin:
        date_added = datetime.now(timezone.utc)
        last_updated = datetime.now(timezone.utc)
        if "date_added" in data:
            date_added = datetime.strptime(data["date_added"], "%Y-%m-%dT%H:%M:%S.000Z")
        if "last_updated" in data:
            last_updated = datetime.strptime(data["last_updated"], "%Y-%m-%dT%H:%M:%S.000Z")

        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            symbol=data.get("symbol", ""),
            slug=data.get("slug", ""),
            num_market_pairs=data.get("num_market_pairs", 0),
            date_added=date_added,
            tags=data.get("tags", []),
            max_supply=data.get("max_supply"),
            circulating_supply=data.get("circulating_supply", 0.0),
            total_supply=data.get("total_supply", 0.0),
            platform=data.get("platform"),
            cmc_rank=data.get("cmc_rank", 0),
            last_updated=last_updated,
            quote={k: Quote.from_json(v) for k, v in data.get("quote", {}).items()},
        )
