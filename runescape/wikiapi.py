from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import List, Optional

import aiohttp
import discord
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from babel.numbers import format_compact_decimal


class FiltersEndpoint(Enum):
    _all = "all"
    last90d = "last90d"
    sample = "sample"
    latest = "latest"

    def get_name(self):
        if self is FiltersEndpoint.last90d:
            return "Last 90 Days"
        return self.value.title()


class GameEnum(Enum):
    runescape = "rs"
    oldschool = "osrs"
    rs_fsw_2022 = "rs-fsw-2022"
    osrs_fsw_2022 = "osrs-fsw-2022"

    @property
    def wiki_url(self):
        return {
            GameEnum.runescape: "https://runescape.wiki/",
            GameEnum.oldschool: "https://oldschool.runescape.wiki/",
            GameEnum.rs_fsw_2022: "https://runescape.wiki/",
            GameEnum.osrs_fsw_2022: "https://oldschool.runescape.wiki/",
        }[self]


class WikiAPIError(Exception):
    pass


class WikiAPI:
    def __init__(self, *, session: Optional[aiohttp.ClientSession] = None):
        self.session = session

    async def _request(
        self,
        url: str,
        params: Optional[dict] = None,
    ):
        if self.session is None:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        raise WikiAPIError(f"Error getting info from the Wiki: {resp.status}")
                    data = await resp.json()
        else:
            async with self.session.get(url, params=params) as resp:
                if resp.status != 200:
                    raise WikiAPIError(f"Error getting info from the Wiki: {resp.status}")
                data = await resp.json()
        if "error" in data:
            raise WikiAPIError(data["error"])
        return data

    def exchange_method(self, endpoint: FiltersEndpoint):
        return {
            FiltersEndpoint._all: self.all,
            FiltersEndpoint.last90d: self.last90d,
            FiltersEndpoint.latest: self.latest,
            FiltersEndpoint.sample: self.sample,
        }[endpoint]

    async def _request_exchange(
        self, game: GameEnum, endpoint: FiltersEndpoint, params: dict
    ) -> dict:
        url = "https://api.weirdgloop.org/exchange/history/{game}/{endpoint}".format(
            endpoint=endpoint.value, game=game.value
        )
        return await self._request(url, params)

    async def latest(
        self,
        game: GameEnum,
        *,
        name: Optional[str] = None,
        item_id: Optional[int] = None,
    ) -> List[Exchange]:
        params = {}
        if name:
            params["name"] = name
        if item_id:
            params["id"] = item_id
        endpoint = FiltersEndpoint.latest
        data = await self._request_exchange(game, endpoint, params)
        return Exchange.from_json(data, game, endpoint)

    async def last90d(
        self,
        game: GameEnum,
        *,
        name: Optional[str] = None,
        item_id: Optional[int] = None,
    ) -> List[Exchange]:
        params = {}
        if name:
            params["name"] = name
        if item_id:
            params["id"] = item_id

        endpoint = FiltersEndpoint.last90d
        data = await self._request_exchange(game, endpoint, params)
        return Exchange.from_json(data, game, endpoint)

    async def all(
        self,
        game: GameEnum,
        *,
        name: Optional[str] = None,
        item_id: Optional[int] = None,
    ) -> List[Exchange]:
        params = {}
        if name:
            params["name"] = name
        if item_id:
            params["id"] = item_id

        endpoint = FiltersEndpoint._all
        data = await self._request_exchange(game, endpoint, params)
        return Exchange.from_json(data, game, endpoint)

    async def sample(
        self,
        game: GameEnum,
        *,
        name: Optional[str] = None,
        item_id: Optional[int] = None,
    ) -> List[Exchange]:
        params = {}
        if name:
            params["name"] = name
        if item_id:
            params["id"] = item_id

        endpoint = FiltersEndpoint.sample
        data = await self._request_exchange(game, endpoint, params)
        return Exchange.from_json(data, game, endpoint)

    # Note Voice of Seren info from the Wiki is not updated
    # due to twitter API changes so these will not work
    async def vos(self) -> dict:
        url = "https://api.weirdgloop.org/runescape/vos"
        return await self._request(url)

    async def vos_history(self) -> dict:
        url = "https://api.weirdgloop.org/runescape/vos/history"
        return await self._request(url)

    async def search(self, game: GameEnum, search: str) -> dict:
        url = game.wiki_url + "api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": search,
            "format": "json",
        }
        return await self._request(url, params)


@dataclass
class Exchange:
    name: str
    id: int
    price: int
    volume: Optional[int]
    datetime: datetime
    _game: GameEnum
    _endpoint: FiltersEndpoint

    @property
    def image(self):
        return (
            self._game.wiki_url
            + "/w/Special:FilePath/"
            + self.name.replace(" ", "_")
            + "_detail.png"
        )

    @property
    def url(self):
        return self._game.wiki_url + "/w/" + self.name.replace(" ", "_")

    @classmethod
    def from_json(cls, data: dict, game: GameEnum, endpoint: FiltersEndpoint) -> List[Exchange]:
        ret = []
        for key, value in data.items():
            if isinstance(value, list):
                for day in value:
                    day.update({"name": key})
                    day["datetime"] = datetime.fromtimestamp(day.pop("timestamp") / 1000).replace(
                        tzinfo=timezone.utc
                    )
                    day["id"] = int(day["id"])
                    ret.append(cls(**day, _game=game, _endpoint=endpoint))
            else:
                value.update({"name": key})
                value["datetime"] = datetime.strptime(
                    value.pop("timestamp"), "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(tzinfo=timezone.utc)
                value["id"] = int(value["id"])
                ret.append(cls(**value, _game=game, _endpoint=endpoint))
        return ret


def format_price_ticks(x, pos):
    return format_compact_decimal(x, format_type="short", locale="en_US", fraction_digits=3)


def plot_exchange(items: List[Exchange]):
    prices = [i.price for i in items]
    times = [i.datetime for i in items]
    game = items[0]._game
    data_set = items[0]._endpoint
    plotcolour = "#081021" if game is GameEnum.runescape else "#E2DBC9"
    facecolour = "#182135" if game is GameEnum.runescape else "#BFA888"
    font_colour = "w" if game is GameEnum.runescape else "black"
    fig, ax = plt.subplots(facecolor=plotcolour, tight_layout=True)
    ax.set_facecolor(facecolour)
    # outline_effect = patheffects.withStroke(linewidth=3, foreground="w")
    ax.plot(times, prices)
    plt.ylabel("Prices", color=font_colour)
    plt.xlabel("Days", color=font_colour)
    plt.grid(True)
    item_name = items[0].name
    url_name = re.sub(r"\W", "", item_name)  # item_name.replace(" ", "_").replace("'", "")
    plt.yticks(fontsize=13, color=font_colour)
    plt.xticks(fontsize=13, color=font_colour)
    ax.set_title(f"{item_name} {data_set.get_name()}", color=font_colour)
    ax.yaxis.set_major_formatter(format_price_ticks)
    if data_set is FiltersEndpoint.last90d:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_minor_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_minor_locator(mdates.MonthLocator())
    # ax.set_xticklabels([i for i in ax.get_xticklabels()], path_effects=[outline_effect])
    temp = BytesIO()
    filename = f"{url_name}.png"
    plt.savefig(temp)
    temp.seek(0)
    return discord.File(temp, filename=filename)
