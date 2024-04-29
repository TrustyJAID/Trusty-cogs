from datetime import datetime, timedelta, timezone
from typing import List, Optional

import discord
from red_commons.logging import getLogger
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.vendored.discord.ext import menus

from .api import GameEventTypeCode, ScheduledGame
from .constants import TEAMS
from .errors import NoSchedule
from .helper import utc_to_local

_ = Translator("Hockey", __file__)
log = getLogger("red.trusty-cogs.Hockey")


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
        self.select_options = []
        self.search_range = 7
        self.include_heatmap = kwargs.get("include_heatmap", False)
        self.include_gameflow = kwargs.get("include_gameflow", False)
        self.include_plays = kwargs.get("include_plays", False)
        self.include_goals = kwargs.get("include_goals", True)
        self.show_broadcasts = kwargs.get("show_broadcasts", False)
        self.style = kwargs.get("style", "all")
        self.corsi = kwargs.get("corsi", True)
        self.strength = kwargs.get("strength", "all")
        self.vs = False
        if kwargs.get("vs", False) and len(self.team) == 2:
            self.vs = True
        self.api = kwargs["api"]

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
        log.debug(
            "Cache size is %s page_number=%s game_id=%s", len(self._cache), page_number, game_id
        )
        if game_id is not None:
            for game in self._cache:
                if game.id == game_id:
                    log.verbose("getting game %s", game_id)
                    page_number = self._cache.index(game)
                    log.verbose(
                        "game_id=%s page_number=%s last_page=%s",
                        game_id,
                        page_number,
                        self.last_page,
                    )
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

    async def format_page(self, menu: menus.MenuPages, game: ScheduledGame) -> discord.Embed:
        log.debug(game.play_by_play)

        game_obj = await self.api.get_game_from_id(game.id)
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
        if self.show_broadcasts:
            broadcasts = []
            for cast in game.broadcasts:
                country = cast.get("countryCode")
                network = cast.get("network")
                broadcasts.append(f"- {country}: {network}")
            broadcast_str = "\n".join(c for c in broadcasts)
            em.add_field(name=_("Broadcasts"), value=broadcast_str)
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
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_timestamp = int(
                utc_to_local((date + timedelta(days=self.search_range)), "UTC").timestamp()
            )
        else:
            date_timestamp = int(utc_to_local(date, "UTC").timestamp())
            end_date_timestamp = int(
                utc_to_local((self.date + timedelta(days=self.search_range)), "UTC").timestamp()
            )
        # log.debug(url)
        self._last_searched = f"<t:{date_timestamp}> to <t:{end_date_timestamp}>"
        team = None
        if self.team:
            team = self.team[0]
        data = await self.api.get_schedule(team, date, end_date)
        games = data.games
        self.select_options = []
        # log.debug(games)
        for count, game in enumerate(games):
            home_team = game.home_team
            home_abr = home_team
            if home_team in TEAMS:
                home_abr = TEAMS[home_team]["tri_code"]
            away_team = game.away_team
            away_abr = away_team
            if away_team in TEAMS:
                away_abr = TEAMS[away_team]["tri_code"]
            if self.vs and (home_team not in self.team or away_team not in self.team):
                continue
            date = game.game_start
            label = f"{away_abr}@{home_abr}-{date.year}-{date.month}-{date.day}"
            description = f"{away_team} @ {home_team}"
            emoji = None
            if home_team in TEAMS:
                if home_team in TEAMS and TEAMS[home_team]["emoji"]:
                    emoji = discord.PartialEmoji.from_str(TEAMS[home_team]["emoji"])
                else:
                    emoji = discord.PartialEmoji.from_str("\N{HOUSE BUILDING}")
            self.select_options.append(
                discord.SelectOption(
                    label=label, value=str(game.id), description=description, emoji=emoji
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


class PlayByPlayFilter(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            min_values=1, max_values=1, options=options, placeholder=_("Filter Events")
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.source.type_code = GameEventTypeCode(int(self.values[0]))
        await self.view.show_page(self.view.current_page, interaction=interaction)


class PlayByPlay(Schedule):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.type_code = kwargs.get("type_code")
        self.select_options = [
            discord.SelectOption(label=e.name.title().replace("_", " "), value=str(e.value))
            for e in GameEventTypeCode
        ]

    async def format_page(self, menu: menus.MenuPages, game: ScheduledGame) -> discord.Embed:
        log.debug(game.play_by_play)
        game_obj = await self.api.get_game_from_id(game.id)
        msg = ""
        events = game_obj.plays
        log.debug(game_obj.url)
        if self.type_code is not None and self.type_code is not GameEventTypeCode.ALL:
            events = [e for e in game_obj.plays if e.type_code is self.type_code]
        for e in reversed(events):
            msg += f"{e.description()}\n"
            if highlight := e.get_highlight(game_obj.landing):
                msg += _("- [Highlight]({highlight_url})").format(highlight_url=highlight)
                msg += "\n"
        em = await game_obj.game_state_embed()
        for page in pagify(msg, delims=["\n"], page_length=4096):
            em.description = page
            break
        return em


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
        self.timezone: Optional[str] = kwargs.get("timezone")
        self.get_recap: bool = kwargs.get("get_recap", False)
        self.show_broadcasts = kwargs.get("show_broadcasts", False)
        self.api = kwargs["api"]

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
        self, menu: menus.MenuPages, games: List[ScheduledGame]
    ) -> discord.Embed:
        # log.debug(games)
        msg = humanize_list(self.team) + "\n"
        day = None
        start_time = None
        for game in games:
            game_start = game.game_start
            home_team = game.home_team
            away_team = game.away_team
            home_emoji = discord.PartialEmoji.from_str("\N{HOUSE BUILDING}")
            away_emoji = discord.PartialEmoji.from_str("\N{AIRPLANE}")
            home_abr = home_team
            away_abr = away_team
            broadcast_str = ""
            log.verbose("ScheduleList game: %s", game)
            if game.broadcasts and self.show_broadcasts:
                if game.broadcasts:
                    broadcast_str = (
                        " - "
                        + _("__Broadcasts__")
                        + "\n   - "
                        + humanize_list([b.get("network", "Unknown") for b in game.broadcasts])
                    )
            if home_team in TEAMS:
                home_emoji = discord.PartialEmoji.from_str(TEAMS[home_team]["emoji"])
                home_abr = TEAMS[home_team]["tri_code"]
            if away_team in TEAMS:
                away_emoji = discord.PartialEmoji.from_str(TEAMS[away_team]["emoji"])
                away_abr = TEAMS[away_team]["tri_code"]

            postponed = game.schedule_state != "OK"
            game_state = game.game_state.emoji()
            if start_time is None:
                start_time = game_start
            if day is None:
                day = utc_to_local(game_start).day
                time = f"<t:{int(game_start.timestamp())}:D>"
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} <t:{int(game_start.timestamp())}:D>**\n"
            elif day and day != utc_to_local(game_start).day:
                day = utc_to_local(game_start).day
                time = f"<t:{int(game_start.timestamp())}:D>"
                game_str = _("Games") if self.team == [] else _("Game")
                msg += f"**{game_str} {time}**\n"
            time_str = f"<t:{int(game_start.timestamp())}:t>"
            if postponed:
                game_state = "\N{CROSS MARK}"
            msg += (
                f"- {away_emoji} {away_abr} @ "
                f"{home_emoji} {home_abr} - {time_str} - {game_state}"
            )

            if game_start < datetime.now(timezone.utc):
                home_score = game.home_score
                away_score = game.away_score
                score_msg = f"{away_abr} **{away_score}** - **{home_score}** {home_abr}"
                if self.get_recap:
                    game_recap = await self.api.get_game_recap(game.id)
                    if game_recap is not None:
                        score_msg = f"[{score_msg}]({game_recap})"
                msg += f"\n  - {score_msg}"
            msg += "\n"
            if self.show_broadcasts:
                msg += f"{broadcast_str}\n"

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
        log.verbose("_next_batch date: %s", date)
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
            end_date_str = (self.date + timedelta(days=days_to_check)).strftime("%Y-%m-%d")
            end_date_timestamp = int(
                utc_to_local((self.date + timedelta(days=days_to_check)), "UTC").timestamp()
            )
        self._last_searched = f"<t:{date_timestamp}> to <t:{end_date_timestamp}>"
        team = None
        if self.team:
            team = self.team[0]
        data = await self.api.get_schedule(team, date, end_date)
        if team is None:
            days = data.days
            if not days:
                #      log.debug("No schedule, looking for more days")
                if self._checks < self.limit:
                    self._checks += 1
                    games = await self._next_batch(date=self.date, _next=_next, _prev=_prev)
                else:
                    raise NoSchedule
            games = days[0]
        else:
            games = data.games
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
