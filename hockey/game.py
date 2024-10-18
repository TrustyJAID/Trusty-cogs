from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Literal, Optional, Set, Tuple, Union

import discord
from red_commons.logging import getLogger
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list, pagify
from yarl import URL

from .constants import TEAMS
from .goal import Goal
from .helper import Team, check_to_post, get_channel_obj, get_team, get_team_role

if TYPE_CHECKING:
    from .api import Event, Player

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")


class GameState(Enum):
    unknown = 0
    preview = 1
    preview_60 = 2
    preview_30 = 3
    preview_10 = 4
    live = 5
    live_end_first = 6
    live_end_second = 7
    live_end_third = 8
    over = 9
    final = 10
    official_final = 11

    def __str__(self):
        return self.name.replace("_", " ").title()

    def emoji(self) -> str:
        if 1 <= self.value < 5:
            return "\N{LARGE RED CIRCLE}"
        if self.value == 5:
            return "\N{LARGE GREEN CIRCLE}"
        if 5 < self.value < 9:
            return "\N{LARGE YELLOW CIRCLE}"
        if self.value >= 9:
            return "\N{CHEQUERED FLAG}"
        return str(self)

    def is_preview(self):
        return self in (
            GameState.preview,
            GameState.preview_60,
            GameState.preview_30,
            GameState.preview_10,
        )

    def is_live(self):
        return self in (
            GameState.live,
            GameState.live_end_first,
            GameState.live_end_second,
            GameState.live_end_third,
        )

    @classmethod
    def from_statsapi(cls, game_state: str) -> GameState:
        return {
            "Preview": GameState.preview,
            "Preview60": GameState.preview_60,
            "Preview30": GameState.preview_30,
            "Preview10": GameState.preview_10,
            "Live": GameState.live,
            "Final": GameState.final,
        }.get(game_state, GameState.unknown)

    @classmethod
    def from_nhle(cls, game_state: str, period: int, remaining: Optional[str] = None) -> GameState:
        if remaining and game_state not in ["CRIT", "OVER", "FINAL", "OFF"]:
            if period == 1 and remaining == "00:00":
                return GameState.live_end_first
            elif period == 2 and remaining == "00:00":
                return GameState.live_end_second
            elif period == 3 and remaining == "00:00":
                return GameState.live_end_third
        return {
            "FUT": GameState.preview,
            "PRE": GameState.preview,
            "Preview": GameState.preview,
            "Preview60": GameState.preview_60,
            "Preview30": GameState.preview_30,
            "Preview10": GameState.preview_10,
            # These previews are only my internal code, not sure if they'll be used
            "LIVE": GameState.live,
            "CRIT": GameState.live,
            "OVER": GameState.over,
            "FINAL": GameState.final,
            "OFF": GameState.official_final,
        }.get(game_state, GameState.unknown)


class GameType(Enum):
    unknown = "Unknown"
    pre_season = "PR"
    regular_season = "R"
    playoffs = "P"
    allstars = "A"
    allstars_women = "WA"
    olympics = "O"
    world_cup_exhibition = "WCOH_EXH"
    world_cup_prelim = "WCOH_PRELIM"
    world_cup_final = "WCOH_FINAL"

    def __str__(self):
        return str(self.value)

    def __int__(self):
        return {GameType.pre_season: 1, GameType.regular_season: 2, GameType.playoffs: 3}[self]

    @classmethod
    def from_int(cls, value: int) -> GameType:
        return {
            1: GameType.pre_season,
            2: GameType.regular_season,
            3: GameType.playoffs,
        }.get(value, GameType.unknown)


@dataclass
class GameStatus:
    abstractGameState: str
    codedGameState: int
    detailedState: str
    statusCode: int
    startTimeTBD: bool

    @classmethod
    def sim(cls):
        return cls(
            abstractGameState="Preview",
            codedGameState="1",
            detailedState="Scheduled",
            statusCode="1",
            startTimeTBD=False,
        )


class Game:
    """
    This is the object that handles game information
    game state updates and goal posts
    """

    def __init__(self, **kwargs):
        super().__init__()
        self.game_id: int = kwargs.get("game_id", 0)
        self.game_state = kwargs.get("game_state", GameState.unknown)
        self.home_shots: int = kwargs.get("home_shots", 0)
        self.away_shots: int = kwargs.get("away_shots", 0)
        self.home_score: int = kwargs.get("home_score", 0)
        self.away_score: int = kwargs.get("away_score", 0)
        self.home: Team = kwargs.get("home")
        self.away: Team = kwargs.get("away")
        self.goals: List[Goal] = kwargs.get("goals", [])
        self.period: int = kwargs.get("period", 0)
        self.period_ord: str = kwargs.get("period_ord", "")
        self.period_time_left: str = kwargs.get("period_time_left", "")
        self.period_starts = kwargs.get("period_starts", {})
        self.plays: List[Event] = kwargs.get("plays", [])
        self.game_start_str = kwargs.get("game_start", "")
        game_start = datetime.strptime(self.game_start_str, "%Y-%m-%dT%H:%M:%SZ")
        self.game_start = game_start.replace(tzinfo=timezone.utc)
        self.first_star = kwargs.get("first_star")
        self.second_star = kwargs.get("second_star")
        self.third_star = kwargs.get("third_star")
        self.away_roster: Dict[int, Player] = kwargs.get("away_roster", {})
        self.home_roster: Dict[int, Player] = kwargs.get("home_roster", {})
        self.game_type: GameType = kwargs.get("game_type", GameType.unknown)
        self.link = kwargs.get("link")
        self.season = kwargs.get("season")
        self._recap_url: Optional[str] = kwargs.get("recap_url", None)
        self.data = kwargs.get("data", {})
        self.api = kwargs.get("api", None)
        self.url = kwargs.get("url", None)
        self.landing: Optional[dict] = kwargs.get("landing", None)

    def __repr__(self):
        return "<Hockey Game home={0.home_team} away={0.away_team} state={0.game_state}>".format(
            self
        )

    @property
    def home_team(self) -> str:
        return self.home.name

    @property
    def away_team(self) -> str:
        return self.away.name

    @property
    def home_logo(self) -> URL:
        return URL(self.home.logo)

    @property
    def away_logo(self) -> URL:
        return URL(self.away.logo)

    @property
    def home_emoji(self) -> Union[discord.PartialEmoji, str]:
        if str(self.home.emoji) == "_":
            # d.py coerces empty strings to _ for client renderability.
            # I don't entirely understand why but it breaks equality when expecting
            # nothing as the emoji name making this a bit more convoluted than necessary.
            return discord.PartialEmoji.from_str("\N{HOUSE BUILDING}\N{VARIATION SELECTOR-16}")
        return self.home.emoji

    @property
    def away_emoji(self) -> Union[discord.PartialEmoji, str]:
        if str(self.home.emoji) == "_":
            return discord.PartialEmoji.from_str("\N{AIRPLANE}\N{VARIATION SELECTOR-16}")
        return self.away.emoji

    @property
    def home_goals(self) -> List[Goal]:
        return [g for g in self.goals if g.team.id == self.home.id]

    @property
    def away_goals(self) -> List[Goal]:
        return [g for g in self.goals if g.team.id == self.away.id]

    @property
    def recap_url(self) -> Optional[URL]:
        if self._recap_url is not None:
            return URL(self._recap_url)

    @property
    def short(self) -> str:
        return f"{self.away.tri_code} @ {self.home.tri_code} {self.period_time_left} {self.period_ord}"

    @property
    def timestamp(self) -> int:
        """
        This is just a helper property to access the game_start as
        a timestamp for formation of discord timestamps
        """
        return int(self.game_start.timestamp())

    def game_type_str(self):
        game_types = {
            GameType.pre_season: _("Pre Season"),
            GameType.regular_season: _("Regular Season"),
            GameType.playoffs: _("Post Season"),
        }
        return game_types.get(self.game_type, _("Unknown"))

    def nst_url(self) -> URL:
        url = URL("https://www.naturalstattrick.com/game.php")
        params = {"season": self.season, "game": str(self.game_id)[5:], "view": "limited"}
        url = url.update_query(params)
        return url.with_fragment("gameflow")

    def heatmap_url(
        self, style: Literal["all", "ev", "5v5", "sva", "home5v4", "away5v4"] = "all"
    ) -> URL:
        url = URL(f"https://www.naturalstattrick.com/heatmaps/games/{self.season}/")
        if style == "home5v4":
            return url.join(
                URL(f"{self.season}-{str(self.game_id)[5:]}-{self.home.tri_code}-5v4.png")
            )
        elif style == "away5v4":
            return url.join(
                URL(f"{self.season}-{str(self.game_id)[5:]}-{self.away.tri_code}-5v4.png")
            )
        return url.join(URL(f"{self.season}-{str(self.game_id)[5:]}-{style}.png"))

    def gameflow_url(
        self, corsi: bool = True, strength: Literal["all", "ev", "5v5", "sva"] = "all"
    ) -> URL:
        url = URL("https://www.naturalstattrick.com/graphs/")
        diff = "cfdiff" if corsi else "xgdiff"
        return url.join(URL(f"{self.season}-{str(self.game_id)[5:]}-{diff}-{strength}.png"))

    def get_goal_from_id(self, goal_id: int) -> Optional[Goal]:
        for goal in self.goals:
            if goal.goal_id == goal_id:
                return goal
        return None

    async def goal_fields(
        self, period_goals: Optional[Literal["1st", "2nd", "3rd"]] = None
    ) -> List[Dict[str, str]]:
        goal_msg = ""
        first_goals = [goal for goal in self.goals if goal.period_ord == "1st"]
        second_goals = [goal for goal in self.goals if goal.period_ord == "2nd"]
        third_goals = [goal for goal in self.goals if goal.period_ord == "3rd"]
        ot_goals = [goal for goal in self.goals if "OT" in goal.period_ord]
        so_goals = [goal for goal in self.goals if goal.period_ord == "SO"]
        list_goals = {
            "1st": first_goals,
            "2nd": second_goals,
            "3rd": third_goals,
            "OT": ot_goals,
        }
        fields = []
        if period_goals:
            list_goals = {period_goals: list_goals[period_goals]}
        for goals in list_goals:
            ordinal = goals
            goal_msg = ""

            period_start_str = ""
            period_start = self.period_starts.get(ordinal)
            if period_start:
                period_start_ts = int(period_start.timestamp())
                period_start_str = f"(<t:{period_start_ts}:t>)"

            for goal in list_goals[ordinal]:
                emoji = goal.emoji
                left = ""
                if goal.time_remaining:
                    left = _("\n{time} left in the {ord} period").format(
                        time=goal.time_remaining, ord=goal.period_ord
                    )
                if goal.link:
                    goal_msg += _(
                        "{emoji} [{team} {strength} Goal By {description} {left}]({link})\n\n"
                    ).format(
                        emoji=emoji,
                        team=goal.team_name,
                        strength=goal.strength,
                        description=goal.description,
                        link=goal.link,
                        left=left,
                    )
                else:
                    goal_msg += _(
                        "{emoji} {team} {strength} Goal By {description} {left}\n\n"
                    ).format(
                        emoji=emoji,
                        team=goal.team_name,
                        strength=goal.strength,
                        description=goal.description,
                        left=left,
                    )

            count = 0
            continued = _("(Continued)")
            for page in pagify(goal_msg, delims=["\n\n", "\n"], page_length=1024, priority=True):
                fields.append(
                    dict(
                        name=_("{ordinal} Period {time} Goals {continued}").format(
                            ordinal=ordinal,
                            time=period_start_str,
                            continued="" if count == 0 else continued,
                        ),
                        value=page,
                        inline=False,
                    )
                )
                count += 1
        if len(so_goals) != 0:
            home_msg, away_msg = await self.goals[-1].get_shootout_display(self)
            # get the last goal so that we always post the full current
            # shootout display here
            fields.append(
                dict(name=_("{team} Shootout").format(team=self.home_team), value=home_msg)
            )
            fields.append(
                dict(name=_("{team} Shootout").format(team=self.away_team), value=away_msg)
            )
        return fields

    async def make_game_embed(
        self,
        include_plays: bool = False,
        period_goals: Optional[Literal["1st", "2nd", "3rd"]] = None,
        include_heatmap: bool = False,
        include_gameflow: bool = False,
        include_goals: bool = True,
    ) -> discord.Embed:
        """
        Builds the game embed when the command is called
        provides as much data as possible
        """
        team_url = self.home.team_url
        # timestamp = datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        title = "{away} @ {home} {state}".format(
            away=self.away_team, home=self.home_team, state=str(self.game_state)
        )
        colour = self.home.colour

        em = discord.Embed(timestamp=self.game_start)
        home_field = f"{self.home_emoji} {self.home_team}"
        away_field = f"{self.away_emoji} {self.away_team}"
        if colour is not None:
            em.colour = colour
        em.set_author(name=title, url=team_url, icon_url=self.home_logo)
        em.set_thumbnail(url=self.home_logo)
        em.set_footer(
            text=_("{game_type} Game start ").format(game_type=self.game_type_str()),
            icon_url=self.away_logo,
        )
        description = ""
        if self.game_state is GameState.preview:
            home_str, away_str, desc, url = await self.get_stats_msg()
            if desc is not None:
                description += desc
            if url is not None:
                em.set_image(url=url)
            em.add_field(name=home_field, value=home_str)
            em.add_field(name=away_field, value=away_str)
        if self.game_type is GameType.playoffs and not self.game_state.is_preview():
            try:
                playoffs = await self.api.get_playoffs(self.game_start.year)
                series = playoffs.get_series(self.home, self.away)
                log.debug("Playoffs series %s", series)
                em.set_image(url=series.logo or playoffs.logo)
                description += f"[{series.title}]({series.url})"
            except Exception:
                log.exception("Error getting playoffs data.")

        if include_heatmap:
            em.set_image(url=self.heatmap_url())
            description += f"\n[Natural Stat Trick]({self.nst_url()})"
        if include_gameflow:
            em.set_image(url=self.gameflow_url())
            description += f"\n[Natural Stat Trick]({self.nst_url()})"

        if not self.game_state.is_preview():
            home_msg = _("Goals: **{home_score}**\nShots: **{home_shots}**").format(
                home_score=self.home_score, home_shots=self.home_shots
            )
            away_msg = _("Goals: **{away_score}**\nShots: **{away_shots}**").format(
                away_score=self.away_score, away_shots=self.away_shots
            )
            em.add_field(name=home_field, value=home_msg)
            em.add_field(name=away_field, value=away_msg)

            if self.goals != [] and include_goals:
                fields = await self.goal_fields(period_goals)
                for field in fields:
                    em.add_field(name=field["name"], value=field["value"], inline=False)
            if self.recap_url is not None:
                description += f"\n[Recap]({self.recap_url})"
            if self.first_star is not None:
                stars = f"⭐ {self.first_star.as_link()}\n⭐⭐ {self.second_star.as_link()}\n⭐⭐⭐ {self.third_star.as_link()}"
                em.add_field(name=_("Stars of the game"), value=stars, inline=False)
            if self.game_state.is_live():
                period = self.period_ord
                if self.period_time_left[0].isdigit():
                    msg = _("{time} Left in the {ordinal} period").format(
                        time=self.period_time_left, ordinal=period
                    )
                else:
                    msg = _("{time} Left of the {ordinal} period").format(
                        time=self.period_time_left, ordinal=period
                    )
                if include_plays:
                    description += _("Last Play: {play}").format(play=self.plays[-1].description)
                em.add_field(name="Period", value=msg)
        if description:
            em.description = description
        return em

    async def game_state_embed(self) -> discord.Embed:
        """
        Makes the game state embed based on the game self provided
        """
        # post_state = ["all", self.home_team, self.away_team]
        # timestamp = datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        title = f"{self.away_team} @ {self.home_team} {str(self.game_state)}"
        em = discord.Embed(timestamp=self.game_start)
        home_field = f"{self.home_emoji} {self.home_team}"
        away_field = f"{self.away_emoji} {self.away_team}"
        description = ""
        if not self.game_state.is_preview():
            home_str = _("Goals: **{home_score}**\nShots: **{home_shots}**").format(
                home_score=self.home_score, home_shots=self.home_shots
            )
            away_str = _("Goals: **{away_score}**\nShots: **{away_shots}**").format(
                away_score=self.away_score, away_shots=self.away_shots
            )
            if self.game_type is GameType.playoffs:
                try:
                    playoffs = await self.api.get_playoffs(self.game_start.year)
                    series = playoffs.get_series(self.home, self.away)
                    log.debug("Playoffs series %s", series)
                    em.set_image(url=series.logo or playoffs.logo)
                    description += f"[{series.title}]({series.url})\n"
                except Exception:
                    log.exception("Error getting playoffs data.")

        else:
            home_str, away_str, desc, url = await self.get_stats_msg()
            if desc is not None:
                description += f"{desc}\n"
            if url is not None:
                em.set_image(url=url)
        em.add_field(name=home_field, value=home_str)
        em.add_field(name=away_field, value=away_str)
        colour = self.home.colour
        if colour is not None:
            em.colour = colour
        home_url = self.home.team_url
        if self.first_star is not None:
            stars = f"⭐ {self.first_star.as_link()}\n⭐⭐ {self.second_star.as_link()}\n⭐⭐⭐ {self.third_star.as_link()}"
            em.add_field(name=_("Stars of the game"), value=stars, inline=False)
        em.set_author(name=title, url=home_url, icon_url=self.home_logo)
        em.set_thumbnail(url=self.home_logo)
        em.set_footer(text=_("Game start "), icon_url=self.away_logo)
        if self.recap_url is not None:
            description += f"[Recap]({self.recap_url})\n"
        if description:
            em.description = description
        return em

    async def game_state_text(self) -> str:
        # post_state = ["all", self.home_team, self.away_team]
        # timestamp =  datetime.strptime(self.game_start, "%Y-%m-%dT%H:%M:%SZ")
        time_string = f"<t:{self.timestamp}>"
        em = (
            f"{self.away_emoji}{self.away_team} @ {self.home_emoji}{self.home_team} "
            f"{str(self.game_state)}\n({time_string})"
        )
        if not self.game_state.is_preview():
            em = (
                _("**__Current Score__**\n")
                + f"{self.home_emoji} {self.home_team}: {self.home_score}\n"
                + f"{self.away_emoji} {self.away_team}: {self.away_score}"
            )
        return em

    async def get_stats_msg(self) -> Tuple[str, str, Optional[str], Optional[URL]]:
        """
        returns team stats on the season from standings object
        """
        home_str = _("GP:**0** W:**0** L:**0\n**OT:**0** PTS:**0** S:**0**\n")
        away_str = _("GP:**0** W:**0** L:**0\n**OT:**0** PTS:**0** S:**0**\n")
        desc = None
        url = None
        if self.game_type is not GameType.playoffs:
            msg = _(
                "GP:**{gp}** W:**{wins}** L:**{losses}\n**OT:**{ot}** PTS:**{pts}** S:**{streak}**\n"
            )
            try:
                standings = await self.api.get_standings()
                for name, record in standings.all_records.items():
                    if record.team.name == self.away_team:
                        away_str = msg.format(
                            wins=record.league_record.wins,
                            losses=record.league_record.losses,
                            ot=record.league_record.ot,
                            pts=record.points,
                            gp=record.games_played,
                            streak=record.streak,
                        )
                    if record.team.name == self.home_team:
                        home_str = msg.format(
                            wins=record.league_record.wins,
                            losses=record.league_record.losses,
                            ot=record.league_record.ot,
                            pts=record.points,
                            gp=record.games_played,
                            streak=record.streak,
                        )
            except Exception:
                log.exception("Error pulling stats")
                pass
        else:
            try:
                msg = _("GP:**{gp}** W:**{wins}** L:**{losses}**")
                playoffs = await self.api.get_playoffs()
                series = playoffs.get_series(self.home, self.away)
                if series is not None:
                    gp = series.games_played
                    if self.away.id == series.topSeedTeam.id:
                        away_wins = series.topSeedWins
                        home_wins = series.bottomSeedWins
                    else:
                        away_wins = series.bottomSeedWins
                        home_wins = series.topSeedWins
                    url = series.logo or playoffs.logo

                    away_str = msg.format(gp=gp, wins=away_wins, losses=gp - away_wins)
                    home_str = msg.format(gp=gp, wins=home_wins, losses=gp - home_wins)
                    desc = f"[{series.title}]({series.url})"
            except Exception:
                log.exception("Error pulling playoffs stats")
                pass
        return home_str, away_str, desc, url

    async def check_game_state(self, bot: Red, count: int = 0) -> bool:
        # post_state = ["all", self.home_team, self.away_team]
        home = await get_team(bot, self.home_team, self.game_start_str, self.game_id)
        await get_team(bot, self.away_team, self.game_start_str, self.game_id)
        # ensures that the TeamEntry gets created for both teams to save their data
        try:
            old_game_state = GameState(home["game_state"])
            log.trace(
                "Old Game State for %s @ %s is %r", self.away_team, self.home_team, old_game_state
            )
        except ValueError:
            old_game_state = GameState.unknown
        # away = await get_team(self.away_team)
        # team_list = await self.config.teams()
        # Home team checking
        end_first = self.period_time_left in ["END", "00:00"] and self.period == 1
        end_second = self.period_time_left in ["END", "00:00"] and self.period == 2
        end_third = self.period_time_left in ["END", "00:00"] and self.period == 3
        if self.game_state.is_preview():
            """Checks if the the game state has changes from Final to Preview
            Could be unnecessary since after Game Final it will check for next game
            """
            time_now = datetime.now(tz=timezone.utc)
            # game_time = datetime.strptime(data.game_start, "%Y-%m-%dT%H:%M:%SZ")
            game_start = (self.game_start - time_now).total_seconds() / 60
            if old_game_state.value < GameState.preview.value:
                asyncio.create_task(self.post_game_state(bot))
                await self.save_game_state(bot)
                bot.dispatch("hockey_preview", self)
            if game_start < 60 and game_start > 30 and old_game_state is not GameState.preview_60:
                # Post 60 minutes until game start
                asyncio.create_task(self.post_time_to_game_start(bot, "60"))
                self.game_state = GameState.preview_60
                await self.save_game_state(bot, "60")
                bot.dispatch("hockey_preview", self)
            if game_start < 30 and game_start > 10 and old_game_state is not GameState.preview_30:
                # Post 30 minutes until game start
                self.game_state = GameState.preview_30
                asyncio.create_task(self.post_time_to_game_start(bot, "30"))
                await self.save_game_state(bot, "30")
                bot.dispatch("hockey_preview", self)
            if game_start < 10 and game_start > 0 and old_game_state is not GameState.preview_10:
                # Post 10 minutes until game start
                self.game_state = GameState.preview_10
                asyncio.create_task(self.post_time_to_game_start(bot, "10"))
                await self.save_game_state(bot, "10")
                bot.dispatch("hockey_preview", self)

                # Create channel and look for game day thread

        if self.game_state.is_live():
            # Checks what the period is and posts the game is starting in the appropriate channel

            if home["period"] != self.period or old_game_state.is_preview():
                log.debug(
                    "**%s Period starting %s at %s**",
                    self.period_ord,
                    self.away_team,
                    self.home_team,
                )
                asyncio.create_task(self.post_game_state(bot))
                await self.save_game_state(bot)
                bot.dispatch("hockey_period_start", self)

            if (self.home_score + self.away_score) != 0:
                # Check if there's goals only if there are goals
                await self.check_team_goals(bot)
            if end_first and old_game_state is not GameState.live_end_first:
                log.debug("End of the first period %s @ %s", self.away_team, self.home_team)
                asyncio.create_task(self.period_recap(bot, "1st"))
                await self.save_game_state(bot, "END1st")
            if end_second and old_game_state is not GameState.live_end_second:
                log.debug("End of the second period %s @ %s", self.away_team, self.home_team)
                asyncio.create_task(self.period_recap(bot, "2nd"))
                await self.save_game_state(bot, "END2nd")
            if end_third and old_game_state is not GameState.live_end_third:
                log.debug("End of the third period %s @ %s", self.away_team, self.home_team)
                asyncio.create_task(self.period_recap(bot, "3rd"))
                await self.save_game_state(bot, "END3rd")

        if self.game_state.value > GameState.over.value:
            if (self.home_score + self.away_score) != 0:
                # Check if there's goals only if there are goals
                await self.check_team_goals(bot)
            if end_third and old_game_state not in [GameState.final, GameState.official_final]:
                log.debug("End of the third period %s @ %s", self.away_team, self.home_team)
                if old_game_state is not GameState.live_end_third:
                    await self.period_recap(bot, "3rd")
                await self.save_game_state(bot, "END3rd")

            if (
                (
                    self.first_star is not None
                    and self.second_star is not None
                    and self.third_star is not None
                    and self.recap_url is not None
                )
                or count >= 20
                or self.game_state is GameState.official_final
            ):
                """Final game state checks"""
                if old_game_state is not self.game_state:
                    # Post game final data and check for next game
                    log.debug("Game Final %s @ %s", self.away_team, self.home_team)
                    asyncio.create_task(self.post_game_state(bot))
                    await self.save_game_state(bot)
                    bot.dispatch("hockey_final", self)
                    log.debug("Saving final")
                    return True
        return False

    async def period_recap(self, bot: Red, period: Literal["1st", "2nd", "3rd"]) -> None:
        """
        Builds the period recap
        """
        em = await self.make_game_embed(False, None)
        tasks = []
        post_state = ["all", self.home_team, self.away_team]
        config = bot.get_cog("Hockey").config
        all_channels = await bot.get_cog("Hockey").config.all_channels()
        async for channel_id, data in AsyncIter(all_channels.items(), steps=100):
            await self.maybe_edit_gamedaythread_message(bot, channel_id, data)
            channel = await get_channel_obj(bot, channel_id, data)
            if not channel:
                continue

            should_post = await check_to_post(bot, channel, data, post_state, self.game_state)
            should_post &= "Periodrecap" in await config.channel(channel).game_states()
            publish = "Periodrecap" in await config.channel(channel).publish_states()
            if should_post:
                tasks.append((channel, publish))
        async for c, to_pub in AsyncIter(tasks, steps=5, delay=5):
            await self.post_period_recap(c, em, to_pub)

    async def post_period_recap(
        self, channel: discord.TextChannel, embed: discord.Embed, publish: bool
    ) -> None:
        """
        Posts the period recap in designated channels
        """
        if not channel.permissions_for(channel.guild.me).send_messages:
            log.debug("No permission to send messages in %s", repr(channel))
            return
        if channel.guild.me.is_timed_out():
            return
        try:
            msg = await channel.send(embed=embed)
            if publish and channel.is_news():
                pass
                # await msg.publish()
        except Exception:
            log.exception("Could not post goal in %s", repr(channel))

    async def maybe_edit_gamedaythread_message(
        self, bot: Red, channel_id: int, data: dict
    ) -> None:
        post_state = ["all", self.home_team, self.away_team]
        if data["parent"] and any([i in data["team"] for i in post_state]) and data["update"]:
            try:
                em = await self.make_game_embed(False, None)
                parent = await get_channel_obj(bot, data["parent"], data)
                if parent is None:
                    return
                if isinstance(parent, discord.ForumChannel):
                    channel = parent.get_thread(channel_id)
                    if channel is None:
                        return
                    msg = channel.get_partial_message(channel_id)
                else:
                    msg = parent.get_partial_message(channel_id)
                asyncio.create_task(msg.edit(embed=em))
            except Exception:
                log.exception("Error editing thread start message.")

    async def post_game_state(self, bot: Red) -> None:
        """
        When a game state has changed this is called to create the embed
        and post in all channels
        """
        post_state = ["all", self.home_team, self.away_team]
        state_embed = await self.game_state_embed()
        state_text = await self.game_state_text()
        tasks = []
        all_channels = await bot.get_cog("Hockey").config.all_channels()
        async for channel_id, data in AsyncIter(all_channels.items(), steps=100):
            await self.maybe_edit_gamedaythread_message(bot, channel_id, data)
            channel = await get_channel_obj(bot, channel_id, data)
            if not channel:
                continue
            if channel.guild.me.is_timed_out():
                continue
            should_post = await check_to_post(bot, channel, data, post_state, self.game_state)
            if should_post:
                tasks.append(channel)
        async for channel in AsyncIter(tasks, steps=5, delay=5):
            await self.actually_post_state(bot, channel, state_embed, state_text)
        # previews = await bounded_gather(*tasks)

    async def actually_post_state(
        self,
        bot: Red,
        channel: Union[discord.TextChannel, discord.Thread],
        state_embed: discord.Embed,
        state_text: str,
    ) -> Optional[Tuple[Union[discord.TextChannel, discord.Thread], discord.Message]]:
        guild = channel.guild
        if not channel.permissions_for(guild.me).send_messages:
            log.debug("No permission to send messages in %s", repr(channel))
            return None
        config = bot.get_cog("Hockey").config
        guild_settings = await config.guild(guild).all()
        channel_settings = await config.channel(channel).all()
        game_day_channels = guild_settings["gdc"]
        can_embed = channel.permissions_for(guild.me).embed_links
        publish_states = []  # await config.channel(channel).publish_states()
        # can_manage_webhooks = False  # channel.permissions_for(guild.me).manage_webhooks

        if self.game_state.is_live():
            start_roles: Set[discord.Role] = set()
            state_roles: Set[discord.Role] = set()
            for team, role_ids in channel_settings.get("game_start_roles", {}).items():
                if team not in ["all", self.home_team, self.away_team]:
                    continue
                for role_id in role_ids:
                    if role := guild.get_role(role_id):
                        start_roles.add(role)
            for team, role_ids in channel_settings.get("game_state_roles", {}).items():
                if team not in ["all", self.home_team, self.away_team]:
                    continue
                for role_id in role_ids:
                    if role := guild.get_role(role_id):
                        state_roles.add(role)

            away_role = get_team_role(guild, self.away_team)
            home_role = get_team_role(guild, self.home_team)
            home_role_mention = self.home_team
            away_role_mention = self.away_team
            if home_role:
                home_role_mention = home_role.mention
            if away_role:
                away_role_mention = away_role.mention
            mention_roles = set()
            allowed_mentions = discord.AllowedMentions(roles=False)
            mention_roles = state_roles
            if start_roles and self.period == 1:
                mention_roles |= start_roles

            allowed_mentions = discord.AllowedMentions(roles=list(mention_roles))

            if "OT" in self.period_ord:
                if not guild_settings["ot_notifications"]:
                    allowed_mentions = discord.AllowedMentions(roles=False)
            if "SO" in self.period_ord:
                if not guild_settings["so_notifications"]:
                    allowed_mentions = discord.AllowedMentions(roles=False)

            text = _("**{period} Period starting {away_role} at {home_role}**").format(
                period=self.period_ord, away_role=away_role_mention, home_role=home_role_mention
            )
            ignore = [home_role_mention, away_role_mention]
            add_mentions: Set[discord.Role] = set()
            for role in mention_roles:
                if role.mention in ignore:
                    continue
                add_mentions.add(role)
            text += "\n" + humanize_list([r.mention for r in add_mentions])

            try:
                if not can_embed:
                    await channel.send(f"{text}\n{state_text}", allowed_mentions=allowed_mentions)
                else:
                    await channel.send(text, embed=state_embed, allowed_mentions=allowed_mentions)
                if self.game_state in publish_states:
                    try:
                        if channel.is_news():
                            # allows backwards compatibility still
                            # await msg.publish()
                            pass
                    except Exception:
                        pass
            except Exception:
                log.exception("Could not post goal in %s", repr(channel))

        else:
            if self.game_state.is_preview():
                if game_day_channels is not None:
                    # Don't post the preview message twice in the channel
                    if channel.id in game_day_channels:
                        return None
            try:
                if not can_embed:
                    preview_msg = await channel.send(state_text)
                else:
                    preview_msg = await channel.send(embed=state_embed)

                # Create new pickems object for the game
                if self.game_state.is_preview():
                    bot.dispatch("hockey_preview_message", channel, preview_msg, self)
                    return channel, preview_msg
            except Exception:
                log.exception("Could not post goal in %s", repr(channel))
        return None

    async def check_team_goals(self, bot: Red) -> None:
        """
        Checks to see if a goal needs to be posted
        """
        team_data = {
            self.home_team: await get_team(bot, self.home_team, self.game_start_str, self.game_id),
            self.away_team: await get_team(bot, self.away_team, self.game_start_str, self.game_id),
        }
        # home_team_data = await get_team(bot, self.home_team)
        # away_team_data = await get_team(bot, self.away_team)
        # all_data = await get_team("all")
        # post_state = ["all", self.home_team, self.away_team]
        cog = bot.get_cog("Hockey")
        # home_goal_ids = [goal.goal_id for goal in self.home_goals]
        # away_goal_ids = [goal.goal_id for goal in self.away_goals]

        home_goal_list = set(team_data[self.home_team]["goal_id"])
        current_home_goals = set(str(goal.goal_id) for goal in self.home_goals)
        away_goal_list = set(team_data[self.away_team]["goal_id"])
        current_away_goals = set(str(goal.goal_id) for goal in self.away_goals)

        for goal in self.goals:
            # goal_id = str(goal["result"]["eventCode"])
            # team = goal["team"]["name"]
            # team_data = await get_team(bot, goal.team_name)
            if str(goal.goal_id) not in team_data[goal.team_name]["goal_id"]:
                # attempts to post the goal if there is a new goal
                bot.dispatch("hockey_goal", self, goal)
                # goal.home_shots = self.home_shots
                # goal.away_shots = self.away_shots
                async with cog.config.teams() as teams:
                    for team in teams:
                        if team["team_name"] == goal.team_name and team["game_id"] == goal.game_id:
                            team["goal_id"][str(goal.goal_id)] = {
                                "goal": goal.to_json(),
                                "messages": [],
                            }
                asyncio.create_task(goal.post_team_goal(bot, self))
                continue
            if str(goal.goal_id) in team_data[goal.team_name]["goal_id"]:
                # attempts to edit the goal if the scorers have changed
                old_goal = Goal(**team_data[goal.team_name]["goal_id"][str(goal.goal_id)]["goal"])
                if goal != old_goal:
                    # goal.home_shots = old_goal.home_shots
                    # goal.away_shots = old_goal.away_shots
                    # This is to keep shots consistent between edits
                    # Shots should not update as the game continues
                    bot.dispatch("hockey_goal_edit", self, goal)
                    log.debug(
                        "Before desc=%s after desc=%s equal=%s before link=%s after link=%s equal=%s",
                        old_goal.description,
                        goal.description,
                        old_goal.description == goal.description,
                        old_goal.link,
                        goal.link,
                        old_goal.link == goal.link,
                    )

                    # This is here in order to prevent the bot attempting to edit the same
                    # goal b2b causing increase of requests to discord for editing and
                    # hopefully reducing instances of rate limiting.
                    # The premise is that when we create this task, store a reference to it
                    # on the cog and when we want to edit see if there is already a task running.
                    # If a task is running we will instead wait for that task to finish and then
                    # run the same code. This way they work one after another instead of parallell.
                    # The done callback removes the task reference when the task is done so
                    # this should be efficient.

                    key = f"{self.game_id}-{goal.goal_id}"

                    def done_edit_callback(task):
                        task_name = task.get_name()
                        try:
                            del cog._edit_tasks[task_name]
                        except Exception:
                            log.exception(
                                "Error removing edit task from list, unknown task name %s",
                                task_name,
                            )

                    if key not in cog._edit_tasks:
                        log.debug("Creating edit task for %s", key)
                        cog._edit_tasks[key] = asyncio.create_task(
                            goal.edit_team_goal(bot, self), name=key
                        )
                        cog._edit_tasks[key].add_done_callback(done_edit_callback)
                    else:
                        log.debug("Found existing edit task, waiting for %s", key)
                        task = cog._edit_tasks[key]
                        await asyncio.wait_for(task, timeout=30)
                        log.debug("Done waiting for %s", key)
                        cog._edit_tasks[key] = asyncio.create_task(
                            goal.edit_team_goal(bot, self), name=key
                        )
                        cog._edit_tasks[key].add_done_callback(done_edit_callback)

                    async with cog.config.teams() as teams:
                        for team in teams:
                            if (
                                team["team_name"] == goal.team_name
                                and team["game_id"] == goal.game_id
                            ):
                                team["goal_id"][str(goal.goal_id)]["goal"] = goal.to_json()
        # attempts to delete the goal if it was called back
        home_diff = home_goal_list.difference(current_home_goals)
        # the difference here from the saved data to the new data returns only goals
        # that are missing from the old data and ignores new goals in the current data
        away_diff = away_goal_list.difference(current_away_goals)
        # log.debug("Home Diff %s Current %s Old %s", home_diff, current_home_goals, home_goal_list)
        # log.debug("Away Diff %s Current %s Old %s", away_diff, current_away_goals, away_goal_list)

        for goal_str in home_diff:
            asyncio.create_task(Goal.remove_goal_post(bot, str(goal_str), self.home_team, self))
        for goal_str in away_diff:
            asyncio.create_task(Goal.remove_goal_post(bot, str(goal_str), self.away_team, self))

    async def save_game_state(self, bot: Red, time_to_game_start: str = "0") -> None:
        """
        Saves the data do the config to compare against new data
        """
        game_state = self.game_state.value
        if time_to_game_start == "END3rd":
            game_state = GameState.live_end_third.value
        async with bot.get_cog("Hockey").config.teams() as teams:
            for team in teams:
                if team["team_name"] not in [self.home_team, self.away_team]:
                    continue
                if team["game_id"] != self.game_id:
                    continue

                if self.game_state not in [GameState.final, GameState.official_final]:
                    if self.game_state.is_preview() and time_to_game_start != "0":
                        team["game_state"] = game_state
                    elif self.game_state.is_live() and time_to_game_start != "0":
                        team["game_state"] = game_state
                    else:
                        team["game_state"] = game_state
                    team["period"] = self.period
                    team["game_start"] = self.game_start_str

                else:
                    if time_to_game_start == "0":
                        team["game_state"] = 0
                        team["period"] = 0
                        team["goal_id"] = {}
                        team["game_start"] = ""
                    elif (
                        self.game_state in [GameState.final, GameState.official_final]
                        and time_to_game_start != "0"
                    ):
                        team["game_state"] = game_state

    async def post_time_to_game_start(self, bot: Red, time_left: str) -> None:
        """
        Post when there is 60, 30, and 10 minutes until the game starts in all channels
        """
        post_state = ["all", self.home_team, self.away_team]
        time_str = f"<t:{self.timestamp}:R>"
        msg = _("{away_emoji} {away} @ {home_emoji} {home} game starts {time}!").format(
            time=time_str,
            away_emoji=self.away_emoji,
            away=self.away_team,
            home_emoji=self.home_emoji,
            home=self.home_team,
        )
        tasks = []
        all_channels = await bot.get_cog("Hockey").config.all_channels()
        async for channel_id, data in AsyncIter(all_channels.items(), steps=100):
            channel = await get_channel_obj(bot, channel_id, data)
            if not channel:
                continue

            should_post = await check_to_post(bot, channel, data, post_state, self.game_state)
            team_to_post = await bot.get_cog("Hockey").config.channel(channel).team()
            if should_post and "all" not in team_to_post:
                tasks.append(channel)
        async for channel in AsyncIter(tasks, delay=5, steps=5):
            await self.post_game_start(channel, msg)
        # await bounded_gather(*tasks)

    async def post_game_start(self, channel: discord.TextChannel, msg: str) -> None:
        if not channel.permissions_for(channel.guild.me).send_messages:
            log.debug("No permission to send messages in %s", repr(channel))
            return
        try:
            await channel.send(msg)
        except Exception:
            log.exception("Could not post goal in %s", repr(channel))

    @classmethod
    def from_data(cls, data: dict):
        goals = [Goal.from_data(**i) for i in data.pop("goals", [])]
        home_team = data.pop("home_team", "unknown team")
        away_team = data.pop("away_team", "unknown team")
        home = Team.from_json(TEAMS.get(home_team, {}), home_team)
        away = Team.from_json(TEAMS.get(away_team, {}), away_team)
        return cls(**data, home=home, away=away, goals=goals)
