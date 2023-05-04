import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiohttp
import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.vendored.discord.ext import menus

from .constants import BASE_URL, TEAMS
from .errors import NoSchedule
from .game import Game
from .helper import utc_to_local

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.hockey")


class Schedule(menus.PageSource):
    def __init__(self, **kwargs):
        self._yielded: int = 0
        self._index: int = 0
        self._cache: List[dict] = []
        self._checks: int = 0
        self._last_page: int = 0
        self.date: datetime = kwargs.get("date", utc_to_local(datetime.now(timezone.utc)))
        if self.date is None:
            self.date = utc_to_local(datetime.now(timezone.utc))
        self.limit: int = kwargs.get("limit", 10)
        self.team: List[str] = kwargs.get("team", [])
        self._last_searched: str = ""
        self._session: aiohttp.ClientSession = kwargs.get("session")
        self.select_options = []
        self.search_range = 30
        self.include_heatmap = kwargs.get("include_heatmap", False)
        self.include_gameflow = kwargs.get("include_gameflow", False)
        self.include_plays = kwargs.get("include_plays", False)
        self.include_goals = kwargs.get("include_goals", True)
        self.style = kwargs.get("style", "all")
        self.corsi = kwargs.get("corsi", True)
        self.strength = kwargs.get("strength", "all")
        self.vs = False
        if kwargs.get("vs", False) and len(self.team) == 2:
            self.vs = True

    @property
    def index(self) -> int:
        return self._index

    @property
    def last_page(self) -> int:
        return self._last_page

    async def get_page(
        self,
        page_number,
        *,
        skip_next: bool = False,
        skip_prev: bool = False,
        game_id: Optional[int] = None,
    ) -> dict:
        log.debug(f"Cache size is {len(self._cache)} {page_number=} {game_id=}")
        if game_id is not None:
            for game in self._cache:
                if game["gamePk"] == game_id:
                    log.debug("getting game")
                    page_number = self._cache.index(game)
                    log.debug(f"{page_number=} {self.last_page=}")
                    self._last_page = page_number
                    self._index = page_number
                    return self._cache[page_number]
        if page_number < self.last_page:
            page = await self.prev()
        if page_number > self.last_page:
            page = await self.next()
        if page_number == self.last_page and self._cache:
            page = self._cache[page_number]
        if skip_next:
            page = await self.next(skip=True)
        if skip_prev:
            page = await self.prev(skip=True)
        if not self._cache:
            raise NoSchedule
        # log.info(page)
        self._last_page = page_number
        return page

    async def format_page(self, menu: menus.MenuPages, game: dict) -> discord.Embed:
        async with aiohttp.ClientSession() as session:
            log.debug(BASE_URL + game["link"])
            async with session.get(BASE_URL + game["link"]) as resp:
                data = await resp.json()
        game_obj = await Game.from_json(data)
        # return {"content": f"{self.index+1}/{len(self._cache)}", "embed": await game_obj.make_game_embed()}
        em = await game_obj.make_game_embed(
            include_plays=self.include_plays,
            include_goals=self.include_goals,
        )
        if self.include_heatmap:
            em.set_image(url=game_obj.heatmap_url(style=self.style))
            em.description = f"[Natural Stat Trick]({game_obj.nst_url()})"
        if self.include_gameflow:
            em.set_image(url=game_obj.gameflow_url(corsi=self.corsi, strength=self.strength))
            em.description = f"[Natural Stat Trick]({game_obj.nst_url()})"
        return em

    async def next(self, choice: Optional[int] = None, skip: bool = False) -> dict:
        """
        Returns the next element from the list

        If all elements have been traversed attempt to pull new data

        If no new data can be found within a reasonable number of calls stop
        """

        self._index += 1
        if choice is not None:
            self._index = choice
        if self._index > (len(self._cache) - 1) or skip:
            # Grab new list from next day
            # log.debug("Getting new games")
            new_date = self.date + timedelta(days=self.search_range)
            self.date = new_date
            try:
                await self._next_batch(date=new_date, _next=True)
            except NoSchedule as e:
                # log.debug("Error getting schedule")
                raise NoSchedule(e)
            self._index = 0
        # log.info(f"getting next data {len(self._cache)}")
        return self._cache[self.index]

    async def prev(self, choice: Optional[int] = None, skip: bool = False) -> dict:
        """
        Returns the previous element from the list

        If all elements have been traversed pull new data

        If no new data can be found within a reasonable number of calls stop
        (this one is expected to have more time between calls)
        I wonder if I should traverse weekly instead of daily :blobthink:
        """
        self._index -= 1
        if choice is not None:
            self._index = choice
        if self._index < 0 or skip:
            # Grab new list from previous day
            new_date = self.date + timedelta(days=-self.search_range)
            self.date = new_date
            try:
                new_data = await self._next_batch(date=new_date, _prev=True)
                self._index = len(new_data) - 1
            except NoSchedule as e:
                # log.debug("Error getting schedule")
                self._index = 0
                raise NoSchedule(e)
        return self._cache[self.index]

    async def prepare(self) -> None:
        try:
            await self._next_batch(date=self.date)
        except NoSchedule:
            pass

    def is_paginating(self) -> bool:
        return True

    async def _next_batch(
        self,
        *,
        date: Optional[datetime] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        _next: bool = False,
        _prev: bool = False,
    ) -> List[dict]:
        """
        Actually grab the list of games.
        """
        # log.debug("Filling the cache")
        # compare_date = datetime.utcnow().strftime("%Y-%m-%d")
        if date:
            date_str = date.strftime("%Y-%m-%d")
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_str = (date + timedelta(days=self.search_range)).strftime("%Y-%m-%d")
            end_date_timestamp = int(
                utc_to_local(
                    (date + timedelta(days=self.search_range)), "UTC"
                ).timestamp()
            )
        else:
            date_str = self.date.strftime("%Y-%m-%d")
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_str = (self.date + timedelta(days=self.search_range)).strftime("%Y-%m-%d")
            end_date_timestamp = int(
                utc_to_local((self.date + timedelta(days=self.search_range)), "UTC").timestamp()
            )

        url = f"{BASE_URL}/api/v1/schedule?startDate={date_str}&endDate={end_date_str}"
        if self.team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            url += "&teamId=" + ",".join(str(TEAMS[t]["id"]) for t in self.team)
        # log.debug(url)
        self._last_searched = f"<t:{date_timestamp}> to <t:{end_date_timestamp}>"
        async with self._session.get(url) as resp:
            data = await resp.json()
        games = [game for date in data["dates"] for game in date["games"]]
        self.select_options = []
        # log.debug(games)
        for count, game in enumerate(games):

            home_team = game["teams"]["home"]["team"]["name"]
            home_abr = home_team
            if home_team in TEAMS:
                home_abr = TEAMS[home_team]["tri_code"]
            away_team = game["teams"]["away"]["team"]["name"]
            away_abr = away_team
            if away_team in TEAMS:
                away_abr = TEAMS[away_team]["tri_code"]
            if self.vs and (home_team not in self.team or away_team not in self.team):
                continue
            date = utc_to_local(datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ"))
            label = f"{away_abr}@{home_abr}-{date.year}-{date.month}-{date.day}"
            description = f"{away_team} @ {home_team}"
            emoji = None
            if home_team in TEAMS:
                if home_team in TEAMS:
                    emoji = discord.PartialEmoji.from_str(TEAMS[home_team]["emoji"])
                else:
                    emoji = discord.PartialEmoji.from_str("\N{HOUSE BUILDING}")
            self.select_options.append(
                discord.SelectOption(
                    label=label, value=str(game["gamePk"]), description=description, emoji=emoji
                )
            )
        if not games:
            # log.debug("No schedule, looking for more days")
            if self._checks < self.limit:
                self._checks += 1
                games = await self._next_batch(date=self.date, _next=_next, _prev=_prev)
            else:
                raise NoSchedule
        self._cache = games
        # return the games as a form of metadata about how the cache is changing
        return games


class ScheduleList(menus.PageSource):
    def __init__(self, **kwargs):
        self._yielded: int = 0
        self._index: int = 0
        self._cache: List[dict] = []
        self._checks: int = 0
        self._last_page: int = 0
        self.date: datetime = kwargs.get("date", utc_to_local(datetime.utcnow()))
        if self.date is None:
            self.date = datetime.now(timezone.utc)
        self.limit: int = kwargs.get("limit", 10)
        self.team: List[str] = kwargs.get("team", [])
        if self.team is None:
            self.team = []
        self._last_searched: str = ""
        self._session: aiohttp.ClientSession = kwargs.get("session")
        self.timezone: str = kwargs.get("timezone")
        self.get_recap: bool = kwargs.get("get_recap", False)

    @property
    def index(self) -> int:
        return self._index

    @property
    def last_page(self) -> int:
        return self._last_page

    async def get_page(
        self,
        page_number,
        *,
        skip_next: bool = False,
        skip_prev: bool = False,
        game_id: Optional[int] = None,
    ) -> List[dict]:
        # log.info(f"Cache size is {len(self._cache)}")

        if page_number < self.last_page:
            page = await self.prev()
        if page_number > self.last_page:
            page = await self.next()
        if page_number == self.last_page and self._cache:
            page = self._cache
        if skip_next:
            page = await self.next(True)
        if skip_prev:
            page = await self.prev(True)
        if not self._cache:
            raise NoSchedule
        # log.info(page)
        self._last_page = page_number
        return page

    async def format_page(
        self, menu: menus.MenuPages, games: List[dict]
    ) -> discord.Embed:
        states = {
            "Preview": "\N{LARGE RED CIRCLE}",
            "Live": "\N{LARGE GREEN CIRCLE}",
            "Intermission": "\N{LARGE YELLOW CIRCLE}",
            "Final": "\N{CHEQUERED FLAG}",
        }
        # log.debug(games)
        msg = humanize_list(self.team) + "\n"
        day = None
        start_time = None
        for game in games:
            game_start = datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ")
            game_start = game_start.replace(tzinfo=timezone.utc)
            home_team = game["teams"]["home"]["team"]["name"]
            away_team = game["teams"]["away"]["team"]["name"]
            home_emoji = discord.PartialEmoji.from_str("\N{HOUSE BUILDING}")
            away_emoji = discord.PartialEmoji.from_str("\N{AIRPLANE}")
            home_abr = home_team
            away_abr = away_team
            if home_team in TEAMS:
                home_emoji = discord.PartialEmoji.from_str(TEAMS[home_team]["emoji"])
                home_abr = TEAMS[home_team]["tri_code"]
            if away_team in TEAMS:
                away_emoji = discord.PartialEmoji.from_str(TEAMS[away_team]["emoji"])
                away_abr = TEAMS[away_team]["tri_code"]

            postponed = game["status"]["detailedState"] == "Postponed"
            try:
                game_state = states[game["status"]["abstractGameState"]]
            except KeyError:
                game_state = "\N{LARGE RED CIRCLE}"
            if start_time is None:
                start_time = game_start
            if day is None:
                day = utc_to_local(game_start).day
                time = f"<t:{int(game_start.timestamp())}:D>"
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} <t:{int(game_start.timestamp())}:D>\n**"
            elif day and day != utc_to_local(game_start).day:
                day = utc_to_local(game_start).day
                time = f"<t:{int(game_start.timestamp())}:D>"
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} {time}\n**"

            if postponed:
                time_str = _("Postponed")
                msg += (
                    f"{game_state} - {away_emoji} {away_abr} @ "
                    f"{home_emoji} {home_abr} - {time_str}\n"
                )
            elif game_start < datetime.now(timezone.utc):
                home_score = game["teams"]["home"]["score"]
                away_score = game["teams"]["away"]["score"]
                if self.get_recap:
                    game_recap = await Game.get_game_recap(game["gamePk"], session=self._session)
                    msg += (
                        f"[{game_state} -  {away_emoji} {away_abr} **{away_score}** - "
                        f"**{home_score}** {home_emoji} {home_abr}]({game_recap}) \n"
                    )
                else:
                    msg += (
                        f"{game_state} -  {away_emoji} {away_abr} **{away_score}** - "
                        f"**{home_score}** {home_emoji} {home_abr} \n"
                    )
            else:
                time_str = f"<t:{int(game_start.timestamp())}:t>"
                msg += (
                    f"{game_state} - {away_emoji} {away_abr} @ "
                    f"{home_emoji} {home_abr} - {time_str}\n"
                )

            count = 0
            em = discord.Embed()
            if len(self.team) == 1:
                # log.debug(self.team)
                colour = (
                    int(TEAMS[self.team[0]]["home"].replace("#", ""), 16)
                    if self.team[0] in TEAMS
                    else None
                )
                if colour is not None:
                    em.colour = colour
                if self.team[0] in TEAMS:
                    em.set_thumbnail(url=TEAMS[self.team[0]]["logo"])
            if len(msg) > 4096:
                for page in pagify(msg, ["Games", "\n"], page_length=1024, priority=True):
                    if count == 0:
                        em.description = page
                        count += 1
                        continue
                    else:
                        em.add_field(name=_("Games Continued"), value=page)
            else:
                em.description = msg
        # return {"content": f"{self.index+1}/{len(self._cache)}", "embed": await game_obj.make_game_embed()}
        return em

    async def next(self, skip: bool = False) -> List[dict]:
        """
        Returns the next element from the list

        If all elements have been traversed attempt to pull new data

        If no new data can be found within a reasonable number of calls stop
        """
        days_to_check = 1
        if self.team != []:
            days_to_check = 7
        self._index += 1
        # Grab new list from next day
        # log.debug("Getting new games")
        new_date = self.date + timedelta(days=days_to_check)
        self.date = new_date
        try:
            await self._next_batch(date=new_date, _next=True)
        except NoSchedule as e:
            # log.debug("Error getting schedule")
            raise NoSchedule(e)
        self._index = 0
        # log.info(f"getting next data {len(self._cache)}")
        return self._cache

    async def prev(self, skip: bool = False) -> List[dict]:
        """
        Returns the previous element from the list

        If all elements have been traversed pull new data

        If no new data can be found within a reasonable number of calls stop
        (this one is expected to have more time between calls)
        I wonder if I should traverse weekly instead of daily :blobthink:
        """
        days_to_check = 1
        if self.team != []:
            days_to_check = 7
        self._index -= 1
        # Grab new list from previous day
        new_date = self.date + timedelta(days=-days_to_check)
        self.date = new_date
        try:
            new_data = await self._next_batch(date=new_date, _prev=True)
            self._index = len(new_data) - 1
        except NoSchedule as e:
            # log.debug("Error getting schedule")
            self._index = 0
            raise NoSchedule(e)
        return self._cache

    async def prepare(self):
        try:
            await self._next_batch(date=self.date)
        except NoSchedule:
            pass

    def is_paginating(self):
        return True

    async def _next_batch(
        self,
        *,
        date: Optional[datetime] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        _next: bool = False,
        _prev: bool = False,
    ) -> List[dict]:
        """
        Actually grab the list of games.
        """
        # compare_date = datetime.utcnow().strftime("%Y-%m-%d")
        log.debug(date)
        days_to_check = 0
        if self.team != []:
            days_to_check = 7

        if date:
            date_str = date.strftime("%Y-%m-%d")
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_str = (date + timedelta(days=days_to_check)).strftime("%Y-%m-%d")
            end_date_timestamp = int(
                utc_to_local((date + timedelta(days=days_to_check)), "UTC").timestamp()
            )
        else:
            date_str = self.date.strftime("%Y-%m-%d")
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_str = (self.date + timedelta(days=days_to_check)).strftime(
                "%Y-%m-%d"
            )
            end_date_timestamp = int(
                utc_to_local(
                    (self.date + timedelta(days=days_to_check)), "UTC"
                ).timestamp()
            )

        url = f"{BASE_URL}/api/v1/schedule?startDate={date_str}&endDate={end_date_str}"
        if self.team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            url += "&teamId=" + ",".join(str(TEAMS[t]["id"]) for t in self.team)
        log.debug(url)
        self._last_searched = f"<t:{date_timestamp}> to <t:{end_date_timestamp}>"
        async with self._session.get(url) as resp:
            data = await resp.json()
        games = [game for date in data["dates"] for game in date["games"]]
        if not games:
            #      log.debug("No schedule, looking for more days")
            if self._checks < self.limit:
                self._checks += 1
                games = await self._next_batch(date=self.date, _next=_next, _prev=_prev)
            else:
                raise NoSchedule
        self._cache = games
        # return the games as a form of metadata about how the cache is changing
        return games
