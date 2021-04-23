from __future__ import annotations

from datetime import datetime
from typing import Any, List, Dict, Optional
from dataclasses import dataclass


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
        return cls(
            price=data["price"],
            volume_24h=data["volume_24h"],
            percent_change_1h=data["percent_change_1h"],
            percent_change_24h=data["percent_change_24h"],
            percent_change_7d=data["percent_change_7d"],
            percent_change_30d=data["percent_change_30d"],
            percent_change_60d=data["percent_change_60d"],
            percent_change_90d=data["percent_change_90d"],
            market_cap=data["market_cap"],
            last_updated=datetime.strptime(data["last_updated"], "%Y-%m-%dT%H:%M:%S.000Z"),
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
        return cls(
            id=data["id"],
            name=data["name"],
            symbol=data["symbol"],
            slug=data["slug"],
            num_market_pairs=data["num_market_pairs"],
            date_added=datetime.strptime(data["date_added"], "%Y-%m-%dT%H:%M:%S.000Z"),
            tags=data["tags"],
            max_supply=data["max_supply"],
            circulating_supply=data["circulating_supply"],
            total_supply=data["total_supply"],
            platform=data["platform"],
            cmc_rank=data["cmc_rank"],
            last_updated=datetime.strptime(data["last_updated"], "%Y-%m-%dT%H:%M:%S.000Z"),
            quote={k: Quote.from_json(v) for k, v in data["quote"].items()}
        )
