from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Coroutine,
    Dict,
    Iterable,
    List,
    Literal,
    NamedTuple,
    Optional,
    Pattern,
    Tuple,
    Union,
)

import discord
import pytz
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from yarl import URL

from .constants import TEAMS
from .teamentry import TeamEntry

if TYPE_CHECKING:
    from .game import Game, GameState
    from .hockey import Hockey
    from .player import SearchPlayer


_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")

DATE_RE = re.compile(
    r"((19|20)\d\d)[- \/.](0[1-9]|1[012]|[1-9])[- \/.](0[1-9]|[12][0-9]|3[01]|[1-9])"
)
DAY_REF_RE = re.compile(r"(yesterday|tomorrow|today)", re.I)

YEAR_RE = re.compile(r"((19|20)\d\d)-?\/?((19|20)\d\d)?")
# https://www.regular-expressions.info/dates.html

TIMEZONE_RE = re.compile(r"|".join(re.escape(zone) for zone in pytz.common_timezones), flags=re.I)


ACTIVE_TEAM_RE_STR = r""
for team, data in TEAMS.items():
    if not data["active"]:
        continue
    nicks = "|".join(f"\b{n}\b" for n in data["nickname"])
    ACTIVE_TEAM_RE_STR += rf"\b{team}\b|\b{data['tri_code']}\b|{nicks}"

ACTIVE_TEAM_RE = re.compile(ACTIVE_TEAM_RE_STR, flags=re.I)

VERSUS_RE = re.compile(r"vs\.?|versus", flags=re.I)


@dataclass
class Team:
    id: int
    name: str
    emoji: Union[discord.PartialEmoji, str]
    logo: str
    home_colour: str
    away_colour: str
    division: str
    conference: str
    tri_code: str
    nickname: List[str]
    team_url: str
    timezone: str
    active: bool
    invite: Optional[str] = None

    def __str__(self):
        return self.name

    @property
    def colour(self) -> discord.Colour:
        return discord.Colour.from_str(self.home_colour)

    @property
    def link(self) -> Optional[URL]:
        return URL(self.team_url)

    @classmethod
    def from_json(cls, data: dict, team_name: str) -> Team:
        return cls(
            id=data.get("id", 0),
            name=team_name,
            emoji=discord.PartialEmoji.from_str(data.get("emoji", "")),
            logo=data.get(
                "logo", "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
            ),
            home_colour=data.get("home", "#000000"),
            away_colour=data.get("away", "#ffffff"),
            division=data.get("division", _("unknown")),
            conference=data.get("conference", _("unknown")),
            tri_code=data.get("tri_code", "".join([i[0].upper() for i in team_name.split(" ")])),
            nickname=data.get("nickname", []),
            team_url=data.get("team_url", ""),
            timezone=data.get("timezone", "US/Pacific"),
            active=data.get("active", False),
            invite=data.get("invite"),
        )

    @classmethod
    def from_id(cls, team_id: int) -> Team:
        for name, data in TEAMS.items():
            if team_id == data["id"]:
                return cls(
                    id=data.get("id", 0),
                    name=name,
                    emoji=discord.PartialEmoji.from_str(data.get("emoji", "")),
                    logo=data.get(
                        "logo", "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
                    ),
                    home_colour=data.get("home", "#000000"),
                    away_colour=data.get("away", "#ffffff"),
                    division=data.get("division", _("unknown")),
                    conference=data.get("conference", _("unknown")),
                    tri_code=data.get(
                        "tri_code", "".join([i[0].upper() for i in name.split(" ")])
                    ),
                    nickname=data.get("nickname", []),
                    team_url=data.get("team_url", ""),
                    timezone=data.get("timezone", "US/Pacific"),
                    active=data.get("active", False),
                    invite=data.get("invite"),
                )
        return cls(
            id=team_id,
            name=_("Unknown Team"),
            emoji=discord.PartialEmoji.from_str(""),
            logo="https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png",
            home_colour="#000000",
            away_colour="#ffffff",
            division=_("unknown"),
            conference=_("unknown"),
            tri_code="",
            nickname=[],
            team_url="",
            timezone="US/Pacific",
            active=False,
            invite=None,
        )

    @classmethod
    def from_name(cls, team_name: str) -> Team:
        for name, data in TEAMS.items():
            if team_name == name:
                return cls.from_id(data["id"])
        return cls(
            id=0,
            name=team_name,
            emoji=discord.PartialEmoji.from_str(""),
            logo="https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png",
            home_colour="#000000",
            away_colour="#ffffff",
            division=_("unknown"),
            conference=_("unknown"),
            tri_code="".join([i[0].upper() for i in team_name.split(" ")]),
            nickname=[],
            team_url="",
            timezone="US/Pacific",
            active=False,
            invite=None,
        )

    @classmethod
    def from_nhle(cls, data: dict, home: bool = False) -> Team:
        name = data.get("name", {}).get("default") or data.get("placeName", {}).get("default")
        team_id = data.get("id", -1)
        team_ids = set(i["id"] for i in TEAMS.values())
        if team_id in team_ids:
            return cls.from_id(team_id)
        return cls.from_name(name)


class Broadcast(NamedTuple):
    id: int
    name: str
    type: str
    site: str
    language: str


def utc_to_local(utc_dt: datetime, new_timezone: str = "US/Pacific") -> datetime:
    eastern = pytz.timezone(new_timezone)
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=eastern)


def get_chn_name(game: Game) -> str:
    """
    Creates game day channel name
    """
    timestamp = utc_to_local(game.game_start)
    chn_name = "{}-vs-{}-{}-{}-{}".format(
        game.home.tri_code, game.away.tri_code, timestamp.year, timestamp.month, timestamp.day
    )
    return chn_name.lower()


class YearFinder(Converter):
    """
    Validates Year format

    for use in the `[p]nhl games` command to pull up specific dates
    """

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> re.Match:
        find = YEAR_RE.search(argument)
        if find:
            return find
        else:
            raise BadArgument(_("`{arg}` is not a valid year.").format(arg=argument))


class DateFinder(discord.app_commands.Transformer):
    """
    Converter for `YYYY-MM-DD` date formats

    for use in the `[p]nhl games` command to pull up specific dates
    """

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> datetime:
        if argument.lower() == "yesterday":
            return datetime.now(timezone.utc) - timedelta(days=1)
        if argument.lower() == "today":
            return datetime.now(timezone.utc)
        if argument.lower() == "tomorrow":
            return datetime.now(timezone.utc) + timedelta(days=1)
        find = DATE_RE.search(argument)
        if find:
            date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
            return datetime.strptime(date_str, "%Y-%m-%d").astimezone(timezone.utc)
        else:
            raise BadArgument()

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> datetime:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, value)


class TeamFinder(discord.app_commands.Transformer):
    """
    Converter for Teams
    """

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> str:
        potential_teams = argument.split()
        result = set()
        include_all = ctx.command.qualified_name in [
            "hockey gdt setup",
            "hockey gdc setup",
            "hockey set add",
            "hockey otherdiscords",
            "hockey notifications start",
            "hockey notifications goal",
            "hockey notifications state",
            "hockey notifications defaultstart",
            "hockey notifications defaultstate",
            "hockey notifications defaultgoal",
        ]
        include_inactive = ctx.command.qualified_name in []
        if argument in TEAMS.keys():
            return argument
        for team, data in TEAMS.items():
            if "Team" in team:
                continue
            if not include_inactive and not data["active"]:
                continue
            nick = data["nickname"]
            short = data["tri_code"]
            pattern = rf"{short}\b|" + r"|".join(rf"\b{i}\b" for i in team.split())
            if nick:
                pattern += r"|" + r"|".join(rf"\b{i}\b" for i in nick)
            # log.debug(pattern)
            reg: Pattern = re.compile(rf"\b{pattern}", flags=re.I)
            for pot in potential_teams:
                find = reg.findall(pot)
                if find:
                    log.verbose("TeamFinder reg: %s", reg)
                    log.verbose("TeamFinder find: %s", find)
                    result.add(team)
        if include_all and "all" in argument:
            result.add("all")
        if not result:
            raise BadArgument(_("You must provide a valid current team."))
        return list(result)[0]

    async def transform(self, interaction: discord.Interaction, argument: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice[str]]:
        team_choices = []
        include_all = interaction.command.name in ["setup", "add", "otherdiscords"]
        include_inactive = interaction.command.name in ["roster", "games"]
        ret = []
        for t, d in TEAMS.items():
            if not include_inactive and not d["active"]:
                continue
            team_choices.append(discord.app_commands.Choice(name=t, value=t))
        if include_all:
            team_choices.insert(0, discord.app_commands.Choice(name="All", value="all"))
        for choice in team_choices:
            if current.lower() in choice.name.lower():
                ret.append(choice)
        return ret[:25]


class PlayerFinder(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> List[SearchPlayer]:
        cog = ctx.bot.get_cog("Hockey")
        players = await cog.api.search_player(argument)
        ret = []
        for player in players:
            if player.name.lower() == argument.lower():
                ret.insert(0, player)
            else:
                ret.append(player)
        return ret

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> List[SearchPlayer]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def check_and_download(self, cog: Hockey):
        now = datetime.utcnow()
        saved = datetime.fromtimestamp(await cog.config.player_db())
        path = cog_data_path(cog) / "players.json"
        if (now - saved) > timedelta(days=1) or not path.exists():
            url = (
                "https://records.nhl.com/site/api/player?include=id"
                "&include=fullName"
                "&include=onRoster"
                "&include=birthDate"
                "&include=homeTown"
                "&include=position"
                "&include=height"
                "&include=weight"
                "&include=birthCity"
                "&include=birthCountry"
                "&include=birthStateProvince"
                "&include=sweaterNumber"
                "&include=lastNHLTeamId"
                "&include=currentTeamId"
                "&include=isRookie"
                "&include=isRetired"
                "&include=isJunior"
                "&include=isSuspended"
                "&include=deceased"
                "&include=dateOfDeath"
                "&include=nationality"
                "&include=longTermInjury"
                "&include=shootsCatches"
                "&include=epPlayerId"
            )
            async with cog.session.get(url) as resp:
                with path.open(encoding="utf-8", mode="w") as f:
                    json.dump(await resp.json(), f)
            await cog.config.player_db.set(int(now.timestamp()))

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        cog = interaction.client.get_cog("Hockey")
        players = await cog.api.search_player(current)
        ret = []
        for player in players:
            ret.append(discord.app_commands.Choice(name=player.name, value=player.name))
        return ret[:25]


class TimezoneFinder(Converter):
    """
    Converts user input into valid timezones for pytz to use
    """

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> str:
        find = TIMEZONE_RE.search(argument)
        if find:
            return find.group(0)
        else:
            raise BadArgument(
                _(
                    "`{argument}` is not a valid timezone. Please see "
                    "`{prefix}hockeyset timezone list`."
                ).format(argument=argument, prefix=ctx.clean_prefix)
            )


class LeaderboardType(Enum):
    worst_playoffs = -2
    worst_preseason = -1
    worst = 0
    preseason = 1
    preseason_weekly = 2
    season = 3
    weekly = 4
    playoffs = 5
    playoffs_weekly = 6
    preseason_last_week = 7
    last_week = 8
    playoffs_last_week = 9

    @classmethod
    def from_str(cls, name: str) -> LeaderboardType:
        leaderboard_type = name.replace(" ", "_").lower()
        if leaderboard_type in ("seasonal", "season"):
            return LeaderboardType(3)
        elif leaderboard_type in ("weekly", "week"):
            return LeaderboardType(4)
        elif leaderboard_type in ("playoffs", "playoff"):
            return LeaderboardType(5)
        elif leaderboard_type in ("playoffs_weekly", "playoff_weekly"):
            return LeaderboardType(6)
        elif leaderboard_type in ("pre-season", "preseason"):
            return LeaderboardType(1)
        elif leaderboard_type in ("pre-season_weekly", "preseason_weekly"):
            return LeaderboardType(2)
        elif leaderboard_type in ("worst",):
            return LeaderboardType(0)
        elif leaderboard_type in ("worst_playoffs",):
            return LeaderboardType(-2)
        elif leaderboard_type in ("worst_preseason", "worst_pre-season"):
            return LeaderboardType(-1)
        elif leaderboard_type in ("last_week",):
            return LeaderboardType(8)
        elif leaderboard_type in ("playoffs_last_week",):
            return LeaderboardType(9)
        elif leaderboard_type in ("pre-season_last_week", "preseason_last_week"):
            return LeaderboardType(7)
        else:
            raise TypeError(_("`{name}` is not a valid leaderboard type.").format(name=name))

    def is_standard(self):
        return self in (
            LeaderboardType.preseason,
            LeaderboardType.season,
            LeaderboardType.playoffs,
        )

    def is_last_week(self):
        return self in (
            LeaderboardType.preseason_last_week,
            LeaderboardType.last_week,
            LeaderboardType.playoffs_last_week,
        )

    def is_weekly(self):
        return self in (
            LeaderboardType.preseason_weekly,
            LeaderboardType.weekly,
            LeaderboardType.playoffs_weekly,
            LeaderboardType.preseason_last_week,
            LeaderboardType.last_week,
            LeaderboardType.playoffs_last_week,
        )

    def is_worst(self):
        return self.value <= 0

    def as_str(self) -> str:
        return self.name.replace("_", " ").replace("preseason", "pre-season")

    def key(self):
        if self.value <= 0:
            return {
                LeaderboardType.worst: "season",
                LeaderboardType.worst_preseason: "preseason",
                LeaderboardType.worst_playoffs: "playoffs",
            }.get(self, "season")
        if self.value < 7:
            return self.name.replace("preseason", "pre-season")
        elif self.value == 7:
            return "pre-season_weekly"
        elif self.value == 8:
            return "weekly"
        else:
            return "playoffs_weekly"

    def total_key(self) -> str:
        return {
            LeaderboardType.season: "total",
            LeaderboardType.playoffs: "playoffs_total",
            LeaderboardType.preseason: "pre-season_total",
            LeaderboardType.worst: "total",
            LeaderboardType.worst_playoffs: "playoffs_total",
            LeaderboardType.worst_preseason: "pre-season_total",
        }.get(self, "total")


class LeaderboardFinder(discord.app_commands.Transformer):
    @classmethod
    async def convert(self, ctx: Context, argument: str) -> LeaderboardType:
        if argument.isdigit():
            return LeaderboardType(int(argument))
        try:
            return LeaderboardType.from_str(argument)
        except TypeError:
            pass
        return LeaderboardType(4)

    async def transform(self, interaction: discord.Interaction, argument: str) -> LeaderboardType:
        ctx = interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, argument: str
    ) -> List[discord.app_commands.Choice[str]]:
        return [
            discord.app_commands.Choice(name=i.as_str().title(), value=str(i.value))
            for i in LeaderboardType
            if argument.lower() in i.as_str().lower()
        ]


class HockeyStates(Enum):
    preview = "Preview"
    live = "Live"
    goal = "Goal"
    periodrecap = "Periodrecap"
    final = "Final"


class StateFinder(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> HockeyStates:
        state_list = [i.value for i in HockeyStates]
        if argument.title() not in state_list:
            raise BadArgument('"{}" is not a valid game state.'.format(argument))
        return HockeyStates(argument.title())

    @classmethod
    async def transform(self, interaction: discord.Interaction, argument: str) -> HockeyStates:
        return await self.convert(interaction, argument)  # type: ignore

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[discord.app_commands.Choice[str]]:
        return [
            discord.app_commands.Choice(name=v.name.title(), value=v.value) for v in HockeyStates
        ]


class Divisions(Enum):
    Metropolitan = "Metropolitan"
    Atlantic = "Atlantic"
    Central = "Central"
    Pacific = "Pacific"


class Conferences(Enum):
    Eastern = "Eastern"
    Western = "Western"


class StandingsFinder(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> str:
        ret = ""
        try:
            ret = Divisions(argument.title()).name
        except ValueError:
            pass
        try:
            ret = Conferences(argument.title()).name
        except ValueError:
            pass
        if argument.lower() == "all":
            ret = "all"
        if argument.lower() == "league":
            ret = "league"
        if not ret:
            for division in Divisions:
                if argument.lower() in division.name.lower():
                    ret = division.name
            for conference in Conferences:
                if argument.lower() in conference.name.lower():
                    ret = conference.name
        return ret.lower()

    @classmethod
    async def transform(cls, ctx: Context, argument: str) -> str:
        ret = ""
        try:
            ret = Divisions(argument.title()).name
        except ValueError:
            pass
        try:
            ret = Conferences(argument.title()).name
        except ValueError:
            pass
        if argument.lower() == "all":
            ret = "all"
        if argument.lower() == "league":
            ret = "league"
        return ret.lower()

    async def autocomplete(
        self, interaction: discord.Interaction, argument: str
    ) -> List[discord.app_commands.Choice[str]]:
        choices = [
            discord.app_commands.Choice(name="All", value="all"),
            discord.app_commands.Choice(name="League", value="league"),
        ]
        choices += [discord.app_commands.Choice(name=d.name, value=d.name) for d in Divisions]
        choices += [discord.app_commands.Choice(name=d.name, value=d.name) for d in Conferences]
        return choices


def game_states_to_int(states: List[str]) -> List[int]:
    ret = []
    options = {
        "Preview": [1, 2, 3, 4],
        "Live": [5],
        "Final": [9, 10, 11],
        "Goal": [],
        "Periodrecap": [6, 7, 8],
    }
    for state in states:
        ret += options.get(state, [])
    return ret


async def check_to_post(
    bot: Red,
    channel: Union[discord.TextChannel, discord.Thread],
    channel_data: dict,
    post_state: List[str],
    game_state: GameState,
    is_goal: bool = False,
) -> bool:
    if channel is None:
        return False
    channel_teams = channel_data.get("team", [])
    if channel_teams is None:
        await bot.get_cog("Hockey").config.channel(channel).team.clear()
        return False
    is_countdown = game_state.value in [2, 3, 4]
    channel_countdown = channel_data["countdown"]
    if is_countdown and channel_countdown is False:
        return False
    should_post = False
    state_ints = game_states_to_int(channel_data["game_states"])
    if game_state.value in state_ints:
        for team in channel_teams:
            if team in post_state:
                should_post = True
    if is_goal and "Goal" in channel_data["game_states"]:
        for team in channel_teams:
            if team in post_state:
                should_post = True
    return should_post


def get_team_role(guild: discord.Guild, team_name: str) -> Optional[discord.Role]:
    """
    This returns the role mentions if they exist
    Otherwise it returns the name of the team as a str
    """
    role = discord.utils.get(guild.roles, name=team_name)
    if role is None and "Canadiens" in team:
        role = discord.utils.get(guild.roles, neam="Montreal Canadiens")
    return role


async def get_team(bot: Red, team: str, game_start: str, game_id: int = 0) -> dict:
    config = bot.get_cog("Hockey").config
    team_list = await config.teams()
    if team_list is None:
        team_list = []
        team_entry = TeamEntry(
            game_state=0,
            team_name=team,
            period=0,
            channel=[],
            goal_id={},
            created_channel=[],
            game_start=game_start,
            game_id=game_id,
        )
        team_list.append(team_entry.to_json())
        await config.teams.set(team_list)
    for teams in team_list:
        if (
            team == teams["team_name"]
            and game_start == teams["game_start"]
            and game_id == teams["game_id"]
        ):
            return teams
    # Add unknown teams to the config to track stats
    return_team = TeamEntry(
        game_state=0,
        team_name=team,
        period=0,
        channel=[],
        goal_id={},
        created_channel=[],
        game_start=game_start,
        game_id=game_id,
    )
    team_list.append(return_team.to_json())
    await config.teams.set(team_list)
    return return_team.to_json()


async def get_channel_obj(
    bot: Red, channel_id: int, data: dict
) -> Optional[Union[discord.TextChannel, discord.Thread]]:
    """
    Requires a bot object to access config, channel_id, and channel config data
    Returns the channel object and sets the guild ID if it's missing from config

    This is used in Game objects and Goal objects so it's here to be shared
    between the two rather than duplicating the code
    """
    if not data["guild_id"]:
        channel = bot.get_channel(channel_id)
        if not channel:
            # await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
            # log.info(f"{channel_id} channel was removed because it no longer exists")
            log.info("channel ID %s Could not be found", channel_id)
            return None
        guild = channel.guild
        await bot.get_cog("Hockey").config.channel(channel).guild_id.set(guild.id)
        return channel
    guild = bot.get_guild(data["guild_id"])
    if not guild:
        # await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
        # log.info(f"{channel_id} channel was removed because it no longer exists")
        log.info("guild ID %s Could not be found", channel_id)
        return None
    channel = guild.get_channel(channel_id)
    thread = guild.get_thread(channel_id)
    if channel is None and thread is None:
        # await bot.get_cog("Hockey").config.channel_from_id(channel_id).clear()
        # log.info(f"{channel_id} channel was removed because it no longer exists")
        log.info("thread or channel ID %s Could not be found", channel_id)
        return None
    return channel or thread


async def slow_send_task(tasks: Iterable[Coroutine]):
    async for task in AsyncIter(tasks, steps=5, delay=5):
        await task
