import discord
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from redbot.core.i18n import Translator
from redbot.vendored.discord.ext import menus
from redbot.core.utils.chat_formatting import pagify

from .constants import BASE_URL, TEAMS
from .errors import NoSchedule
from .game import Game
from .helper import utc_to_local

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.hockey")


class Schedule(menus.PageSource):
    def __init__(self, **kwargs):
        self._yielded = 0
        self._listing = None
        self._index = 0
        self._cache = []
        self._checks = 0
        self._last_page = 0
        self.date = kwargs.get("date", utc_to_local(datetime.utcnow()))
        self.limit = kwargs.get("limit", 10)
        self.team = kwargs.get("team", None)
        self._last_searched = ""

    @property
    def index(self):
        return self._index

    @property
    def last_page(self):
        return self._last_page

    async def get_page(self, page_number, *, skip_next: bool = False, skip_prev: bool = False):
        # log.info(f"Cache size is {len(self._cache)}")

        if page_number < self.last_page:
            page = await self.prev()
        if page_number > self.last_page:
            page = await self.next()
        if page_number == self.last_page and self._cache:
            page = self._cache[page_number]
        if skip_next:
            page = await self.next(True)
        if skip_prev:
            page = await self.prev(True)
        if not self._cache:
            raise NoSchedule
        # log.info(page)
        self._last_page = page_number
        return page

    async def format_page(self, menu: menus.MenuPages, game: dict):
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL + game["link"]) as resp:
                data = await resp.json()
        game_obj = await Game.from_json(data)
        # return {"content": f"{self.index+1}/{len(self._cache)}", "embed": await game_obj.make_game_embed()}
        return await game_obj.make_game_embed(True)

    async def next(self, skip: bool = False):
        """
        Returns the next element from the list

        If all elements have been traversed attempt to pull new data

        If no new data can be found within a reasonable number of calls stop
        """
        self._index += 1
        if self._index > (len(self._cache) - 1) or skip:
            # Grab new list from next day
            # log.debug("Getting new games")
            new_date = self.date + timedelta(days=30)
            self.date = new_date
            try:
                await self._next_batch(date=new_date, _next=True)
            except NoSchedule as e:
                # log.debug("Error getting schedule")
                raise NoSchedule(e)
            self._index = 0
        # log.info(f"getting next data {len(self._cache)}")
        return self._cache[self.index]

    async def prev(self, skip: bool = False):
        """
        Returns the previous element from the list

        If all elements have been traversed pull new data

        If no new data can be found within a reasonable number of calls stop
        (this one is expected to have more time between calls)
        I wonder if I should traverse weekly instead of daily :blobthink:
        """
        self._index -= 1
        if self._index < 0 or skip:
            # Grab new list from previous day
            new_date = self.date + timedelta(days=-30)
            self.date = new_date
            try:
                new_data = await self._next_batch(date=new_date, _prev=True)
                self._index = len(new_data) - 1
            except NoSchedule as e:
                # log.debug("Error getting schedule")
                self._index = 0
                raise NoSchedule(e)
        return self._cache[self.index]

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
    ):
        """
        Actually grab the list of games.
        """
        # compare_date = datetime.utcnow().strftime("%Y-%m-%d")
        if date:
            date_str = date.strftime("%Y-%m-%d")
            end_date_str = (date + timedelta(days=30)).strftime("%Y-%m-%d")
        else:
            date_str = self.date.strftime("%Y-%m-%d")
            end_date_str = (self.date + timedelta(days=30)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/api/v1/schedule?startDate={date_str}&endDate={end_date_str}"
        if self.team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            url += "&teamId=" + ",".join(str(TEAMS[t]["id"]) for t in self.team)
        # log.debug(url)
        self._last_searched = f"{date_str} to {end_date_str}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        games = [game for date in data["dates"] for game in date["games"]]
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
        self._yielded = 0
        self._listing = None
        self._index = 0
        self._cache = []
        self._checks = 0
        self._last_page = 0
        self.date = kwargs.get("date", utc_to_local(datetime.utcnow()))
        self.limit = kwargs.get("limit", 10)
        self.team = kwargs.get("team", [])
        self._last_searched = ""

    @property
    def index(self):
        return self._index

    @property
    def last_page(self):
        return self._last_page

    async def get_page(self, page_number, *, skip_next: bool = False, skip_prev: bool = False):
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

    async def format_page(self, menu: menus.MenuPages, games: dict):
        states = {
            "Preview": "\N{LARGE RED CIRCLE}",
            "Live": "\N{LARGE GREEN CIRCLE}",
            "Intermission": "\N{LARGE YELLOW CIRCLE}",
            "Final": "\N{CHEQUERED FLAG}"
        }
        # log.debug(games)
        msg = ""
        day = None
        start_time = None
        for game in games:
            game_start = datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ")
            home_team = game["teams"]["home"]["team"]["name"]
            away_team = game["teams"]["away"]["team"]["name"]
            home_emoji = "<:" + TEAMS[home_team]["emoji"] + ">"
            away_emoji = "<:" + TEAMS[away_team]["emoji"] + ">"
            home_abr = TEAMS[home_team]["tri_code"]
            away_abr = TEAMS[away_team]["tri_code"]
            try:
                game_state = states[game["status"]["abstractGameState"]]
            except KeyError:
                game_state = "\N{LARGE RED CIRCLE}"
            if start_time is None:
                start_time = game_start
            if day is None:
                day = utc_to_local(game_start).day
                time = utc_to_local(game_start).strftime("%A %b %d")
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} {time}\n**"
            elif day and day != utc_to_local(game_start).day:
                day = utc_to_local(game_start).day
                time = utc_to_local(game_start).strftime("%A %b %d")
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} {time}\n**"

            if game_start < datetime.utcnow():
                home_score = game["teams"]["home"]["score"]
                away_score = game["teams"]["away"]["score"]
                msg += (
                    f"{game_state} - {home_emoji} {home_abr} **{home_score}** - "
                    f"**{away_score}** {away_emoji} {away_abr} \n"
                )
            else:
                if self.team == []:
                    game_time = utc_to_local(game_start, TEAMS[home_team]["timezone"])
                    time_str = game_time.strftime("%I:%M %p %Z")
                else:

                    game_time = utc_to_local(game_start, TEAMS[self.team[0]]["timezone"])
                    time_str = game_time.strftime("%I:%M %p %Z")
                msg += f"{game_state} - {away_emoji} {away_abr} @ " f"{home_emoji} {home_abr} - {time_str}\n"

            count = 0
            em = discord.Embed(timestamp=start_time)
            em.set_footer(text=_("Games Start"))
            if self.team != []:
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
            if len(msg) > 2048:
                for page in pagify(msg, ["Games", "\n"], page_length=1024):
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

    async def next(self, skip: bool = False):
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

    async def prev(self, skip: bool = False):
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
    ):
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
            end_date_str = (date + timedelta(days=days_to_check)).strftime("%Y-%m-%d")
        else:
            date_str = self.date.strftime("%Y-%m-%d")
            end_date_str = (self.date + timedelta(days=days_to_check)).strftime("%Y-%m-%d")

        url = f"{BASE_URL}/api/v1/schedule?startDate={date_str}&endDate={end_date_str}"
        if self.team not in ["all", None]:
            # if a team is provided get just that TEAMS data
            url += "&teamId=" + ",".join(str(TEAMS[t]["id"]) for t in self.team)
        # log.debug(url)
        self._last_searched = f"{date_str} to {end_date_str}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        games = [game for date in data["dates"] for game in date["games"]]
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
