from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box
from redbot.vendored.discord.ext import menus
from tabulate import tabulate
from yarl import URL

from .components import (
    BackButton,
    FirstItemButton,
    ForwardButton,
    LastItemButton,
    StopButton,
    TeamButton,
)
from .constants import BASE_URL, TEAMS
from .helper import ACTIVE_TEAM_RE, Conferences, Divisions, Team, utc_to_local

if TYPE_CHECKING:
    from redbot.core import Config, commands

    from .api import NewAPI

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")


class StreakType(Enum):
    ot = "ot"
    wins = "wins"
    losses = "losses"

    @classmethod
    def from_code(cls, code: str) -> StreakType:
        return {"W": StreakType.wins, "L": StreakType.losses, "OT": StreakType.ot}.get(
            code, StreakType.wins
        )


@dataclass
class LeagueRecord:
    wins: int
    losses: int
    ot: int
    type: Literal["league"]


@dataclass
class Streak:
    streakType: StreakType
    streakNumber: int
    streakCode: str

    def __init__(self, *args, **kwargs):
        try:
            self.streakType = StreakType(kwargs["streakType"])
        except ValueError:
            self.streakType = StreakType.from_code(kwargs["streakCode"])
        self.streakNumber = int(kwargs["streakNumber"])
        self.streakCode = kwargs["streakCode"]

    def __str__(self):
        return self.streakCode


@dataclass
class Division:
    id: int
    name: str
    nameShort: str
    link: str
    abbreviation: str


@dataclass
class Conference:
    id: Optional[int]
    name: Optional[str]
    link: Optional[str]

    @classmethod
    def from_json(cls, data: dict) -> Conference:
        return cls(
            id=data.get("id", None),
            name=data.get("name", None),
            link=data.get("link", None),
        )


@dataclass
class Playoffs:
    year: int
    bracketLogo: Optional[str] = None
    bracketLogoFr: Optional[str] = None
    series: List[PlayoffSeries] = field(default_factory=list)

    @property
    def logo(self) -> Optional[URL]:
        if self.bracketLogo:
            return URL(self.bracketLogo)

    @classmethod
    def from_json(cls, data: dict, year: int) -> Playoffs:
        series = [PlayoffSeries.from_json(i, year) for i in data.pop("series", [])]
        return cls(**data, series=series, year=year)

    def get_series(self, team_1: Team, team_2: Team) -> Optional[PlayoffSeries]:
        for series in self.series:
            top_team = series.topSeedTeam
            bot_team = series.bottomSeedTeam
            if top_team is None or bot_team is None:
                continue
            if top_team.id == team_1.id and bot_team.id == team_2.id:
                return series
            if top_team.id == team_2.id and bot_team.id == team_1.id:
                return series

    def embed(self) -> discord.Embed:
        msg = ""
        if not self.series:
            msg = "TBD"
        embed = discord.Embed(title=_("Stanley Cup Playoffs {season}").format(season=self.year))
        embed.set_image(url=self.bracketLogo)
        for series in self.series:
            top_wins = series.topSeedWins
            bot_wins = series.bottomSeedWins
            if series.url:
                msg = f"[{series.description}]({series.url})\n"
            else:
                msg = f"{series.description}\n"
            msg += f"{top_wins}-{bot_wins}\n"
            if series.winner is not None:
                msg += _("Winner: {winner}").format(winner=series.winner)
            embed.add_field(name=f"{series.seriesTitle}", value=msg)
        return embed


@dataclass
class PlayoffSeries:
    seriesTitle: str
    seriesAbbrev: str
    seriesLetter: str
    playoffRound: int
    topSeedRank: int
    topSeedWins: int
    bottomSeedRank: int
    bottomSeedWins: int

    year: int

    winningTeamId: int = -1
    losingTeamId: int = -1
    conferenceAbbrev: Optional[str] = None
    conferenceName: Optional[str] = None
    seriesLogo: Optional[str] = None
    seriesLogoFr: Optional[str] = None
    bottomSeedRankAbbrev: Optional[str] = None
    topSeedRankAbbrev: Optional[str] = None
    seriesUrl: Optional[str] = None
    topSeedTeam: Optional[Team] = None
    bottomSeedTeam: Optional[Team] = None

    @property
    def round(self):
        return self.playoffRound

    @property
    def title(self) -> str:
        return _("{year} Stanley Cup Playoffs: {series}").format(
            year=self.year, series=self.seriesTitle
        )

    @property
    def description(self) -> str:
        return _("{top_team} vs. {bottom_team}").format(
            top_team=self.topSeedTeam or _("TBD"), bottom_team=self.bottomSeedTeam or _("TBD")
        )

    @property
    def url(self) -> Optional[URL]:
        if self.seriesUrl is not None:
            return URL("https://nhl.com").join(URL(self.seriesUrl))
        return None

    @property
    def logo(self) -> Optional[URL]:
        if self.seriesLogo is not None:
            return URL(self.seriesLogo)
        return None

    @property
    def logo_fr(self) -> Optional[URL]:
        if self.seriesLogoFr is not None:
            return URL(self.seriesLogoFr)
        return None

    @property
    def games_played(self) -> int:
        return self.topSeedWins + self.bottomSeedWins

    @property
    def winner(self) -> Optional[Team]:
        if self.winningTeamId <= 0:
            return None
        if self.topSeedTeam is None or self.bottomSeedTeam is None:
            return None
        elif self.winningTeamId == self.topSeedTeam.id:
            return self.topSeedTeam
        else:
            return self.bottomSeedTeam

    @classmethod
    def from_json(cls, data: dict, year: int) -> PlayoffSeries:
        top_team = data.pop("topSeedTeam", None)
        if top_team:
            top_team = Team.from_nhle(top_team)
        bot_team = data.pop("bottomSeedTeam", None)
        if bot_team:
            bot_team = Team.from_nhle(bot_team)

        return cls(**data, topSeedTeam=top_team, bottomSeedTeam=bot_team, year=year)


class PlayoffsView(discord.ui.View):
    def __init__(self, start_date: Optional[int], api: NewAPI):
        super().__init__()
        self.playoffs = None
        self.current_page = start_date
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.stop_button)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.api = api

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self):
        value = self.playoffs.embed()
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        season = page_number
        self.playoffs = await self.api.get_playoffs(season)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page()
        if interaction.response.is_done():
            await interaction.followup.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(self, ctx: commands.Context) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.author = ctx.author
        if self.playoffs is None:
            season = None
            if self.current_page is not None:
                season = self.current_page
            self.playoffs = await self.api.get_playoffs(season)
            self.current_page = self.playoffs.year
        kwargs = await self._get_kwargs_from_page()
        return await ctx.send(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = None
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


@dataclass
class TeamRecord:
    team: Team
    division: Division
    conference: Conference
    league_record: LeagueRecord
    regulation_wins: int
    goals_against: int
    goals_scored: int
    points: int
    division_rank: int
    division_l10_rank: int
    division_road_rank: int
    division_home_rank: int
    conference_rank: int
    conference_l10_rank: int
    conference_road_rank: int
    conference_home_rank: int
    league_rank: int
    league_l10_rank: int
    league_road_rank: int
    league_home_rank: int
    wildcard_rank: int
    row: int
    games_played: int
    streak: Streak
    points_percentage: float
    pp_division_rank: int
    pp_conference_rank: int
    pp_league_rank: int
    last_updated: datetime

    def __str__(self) -> str:
        wildcard = f"(WC{self.wildcard_rank})" if self.wildcard_rank else ""
        just = 4
        return (
            f"GP: {str(self.games_played).ljust(just)} "
            f"W: {str(self.league_record.wins).ljust(just)} "
            f"L: {str(self.league_record.losses).ljust(just)} "
            f"OT: {str(self.league_record.ot).ljust(just)} "
            f"PTS: {str(self.points).ljust(just)} "
            f"{wildcard}\n"
        )

    @property
    def gaa(self):
        try:
            return self.goals_against / self.games_played
        except ZeroDivisionError:
            return 0.0

    @property
    def gpg(self):
        try:
            return self.goals_scored / self.games_played
        except ZeroDivisionError:
            return 0.0

    @classmethod
    def from_json(cls, data: dict, division: Division, conference: Conference) -> TeamRecord:
        return cls(
            team=Team(**data["team"]),
            division=division,
            conference=conference,
            league_record=LeagueRecord(**data["leagueRecord"]),
            regulation_wins=int(data["regulationWins"]),
            goals_against=int(data["goalsAgainst"]),
            goals_scored=int(data["goalsScored"]),
            points=int(data["points"]),
            division_rank=int(data["divisionRank"]),
            division_l10_rank=int(data["divisionL10Rank"]),
            division_road_rank=int(data["divisionRoadRank"]),
            division_home_rank=int(data["divisionHomeRank"]),
            conference_rank=int(data["conferenceRank"]),
            conference_l10_rank=int(data["conferenceL10Rank"]),
            conference_road_rank=int(data["conferenceRoadRank"]),
            conference_home_rank=int(data["conferenceHomeRank"]),
            league_rank=int(data["leagueRank"]),
            league_l10_rank=int(data["leagueL10Rank"]),
            league_road_rank=int(data["leagueRoadRank"]),
            league_home_rank=int(data["leagueHomeRank"]),
            wildcard_rank=int(data["wildCardRank"]),
            row=int(data["row"]),
            games_played=int(data["gamesPlayed"]),
            streak=Streak(
                **data.get("streak", {"streakType": "wins", "streakNumber": 0, "streakCode": ""})
            ),
            points_percentage=float(data["pointsPercentage"]),
            pp_division_rank=int(data["ppDivisionRank"]),
            pp_conference_rank=int(data["ppConferenceRank"]),
            pp_league_rank=int(data["ppLeagueRank"]),
            last_updated=datetime.strptime(data["lastUpdated"], "%Y-%m-%dT%H:%M:%SZ"),
        )

    @classmethod
    def from_nhle(cls, data: dict) -> TeamRecord:
        team_name = data["teamName"].get("default")
        team = Team.from_name(team_name)
        division = Division(
            id=0,
            name=data["divisionName"],
            nameShort="",
            abbreviation=data["divisionAbbrev"],
            link=None,
        )
        conference = Conference(id=0, name=data["conferenceName"], link=None)
        league_record = LeagueRecord(
            wins=data["wins"], losses=data["losses"], ot=data["otLosses"], type="league"
        )
        streak = Streak(
            **{
                "streakType": "wins",
                "streakNumber": data.get("streakCount", 0),
                "streakCode": data.get("streakCode", "N/A"),
            }
        )
        return cls(
            team=team,
            division=division,
            conference=conference,
            league_record=league_record,
            regulation_wins=int(data["regulationWins"]),
            goals_against=int(data["goalAgainst"]),
            goals_scored=int(data["goalFor"]),
            points=int(data["points"]),
            division_rank=int(data["divisionSequence"]),
            division_l10_rank=int(data["divisionL10Sequence"]),
            division_road_rank=int(data["divisionRoadSequence"]),
            division_home_rank=int(data["divisionHomeSequence"]),
            conference_rank=int(data["conferenceSequence"]),
            conference_l10_rank=int(data["conferenceL10Sequence"]),
            conference_road_rank=int(data["conferenceRoadSequence"]),
            conference_home_rank=int(data["conferenceHomeSequence"]),
            league_rank=int(data["leagueSequence"]),
            league_l10_rank=int(data["leagueL10Sequence"]),
            league_road_rank=int(data["leagueRoadSequence"]),
            league_home_rank=int(data["leagueHomeSequence"]),
            wildcard_rank=int(data["wildcardSequence"]),
            row=0,
            games_played=int(data["gamesPlayed"]),
            streak=streak,
            points_percentage=float(data.get("pointPctg", 0.0)),
            pp_division_rank=0,
            pp_conference_rank=0,
            pp_league_rank=0,
            last_updated=datetime.now(timezone.utc),
        )


class Standings:
    def __init__(self, records: dict = {}):
        super().__init__()
        self.all_records = records

    def last_timestamp(
        self,
        *,
        division: Optional[Divisions] = None,
        conference: Optional[Conferences] = None,
    ) -> datetime:
        """Get the last updated time for the total number of teams provided"""
        latest = None
        for team, record in self.all_records.items():
            if division and division in [record.division.name.lower(), "division"]:
                continue
            if conference and conference in [record.conference.name.lower(), "conference"]:
                continue
            if latest is None:
                latest = record.last_updated
            if record.last_updated > latest:
                latest = record.last_updated
        return latest or datetime.now(timezone.utc)

    @classmethod
    def from_nhle(cls, data: dict) -> Standings:
        all_records = {}
        for team in data["standings"]:
            record = TeamRecord.from_nhle(team)
            all_records[record.team.name] = record
        return cls(records=all_records)

    @classmethod
    async def get_team_standings(
        cls,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Standings:
        """
        Creates a list of standings when given a particular style
        accepts Division names, Conference names, and Team names
        returns a list of standings objects and the location of the given
        style in the list
        """
        if session is None:
            async with aiohttp.ClientSession() as new_session:
                async with new_session.get(BASE_URL + "/api/v1/standings") as resp:
                    data = await resp.json()
        else:
            async with session.get(BASE_URL + "/api/v1/standings") as resp:
                data = await resp.json()
        all_records = {}
        for division in data["records"]:
            div_class = Division(**division["division"])
            conf_class = Conference(**division["conference"])
            for team in division["teamRecords"]:
                record = TeamRecord.from_json(team, division=div_class, conference=conf_class)
                all_records[record.team.name] = record
        return cls(records=all_records)

    @staticmethod
    async def post_automatic_standings(bot) -> None:
        """
        Automatically update a standings embed with the latest stats
        run when new games for the day is updated
        """
        log.debug("Updating Standings.")
        cog = bot.get_cog("Hockey")
        config = cog.config
        standings = await cog.api.get_standings()

        all_guilds = await config.all_guilds()
        async for guild_id, data in AsyncIter(all_guilds.items(), steps=100):
            guild = bot.get_guild(guild_id)
            if guild is None:
                continue
            log.verbose("post_automatic_standings, guild name: ", guild.name)
            if data["post_standings"]:
                search = data["standings_type"]
                if search is None:
                    continue
                standings_channel = data["standings_channel"]
                if standings_channel is None:
                    continue
                channel = guild.get_channel(standings_channel)
                if channel is None:
                    continue
                standings_msg = data["standings_msg"]
                if standings_msg is None:
                    continue
                try:
                    message = channel.get_partial_message(standings_msg)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    await config.guild(guild).post_standings.clear()
                    await config.guild(guild).standings_type.clear()
                    await config.guild(guild).standings_channel.clear()
                    await config.guild(guild).standings_msg.clear()
                    continue

                if search in [i.name.lower() for i in Divisions]:
                    div = Divisions(search.title())
                    em = await standings.make_division_standings_embed(div)

                elif search in [i.name.lower() for i in Conferences]:
                    conf = Conferences(search.title())
                    em = await standings.make_conference_standings_embed(conf)
                else:
                    em = await standings.all_standing_embed()
                if message is not None:
                    asyncio.create_task(
                        standings.edit_standings_message(em, guild, message, config)
                    )

    @staticmethod
    async def edit_standings_message(
        embed: discord.Embed, guild: discord.Guild, message: discord.Message, config: Config
    ) -> None:
        try:
            await message.edit(embed=embed)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            await config.guild(guild).post_standings.clear()
            await config.guild(guild).standings_type.clear()
            await config.guild(guild).standings_channel.clear()
            await config.guild(guild).standings_msg.clear()
        except Exception:
            log.exception(f"Error editing standings message in {repr(guild)}")

    async def all_standing_embed(self, table: bool = True) -> discord.Embed:
        """
        Builds the standing embed when all TEAMS are selected
        """
        em = discord.Embed()
        new_dict = {}
        nhl_icon = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        latest_timestamp = self.last_timestamp()
        for division in Divisions:
            if table:
                new_dict[division.name] = box(self.get_division_table(division), lang="ansi")
            else:
                new_dict[division.name] = self.get_division_str(division)
        for div in new_dict:
            em.add_field(name=f"{div} Division", value=new_dict[div], inline=False)
        em.set_author(
            name="NHL Standings",
            url="https://www.nhl.com/standings",
            icon_url=nhl_icon,
        )
        em.set_thumbnail(url=nhl_icon)
        em.timestamp = utc_to_local(latest_timestamp, "UTC")
        em.set_footer(text="Stats Last Updated", icon_url=nhl_icon)
        return em

    async def league_standing_embed(self, table: bool = True) -> discord.Embed:
        em = discord.Embed()
        msg = ""
        nhl_icon = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        if table:
            msg = box(self.get_all_table())
        else:
            msg = self.get_all_str()
        em.description = msg
        em.set_author(
            name="NHL League Standings",
            url="https://www.nhl.com/standings",
            icon_url=nhl_icon,
        )
        em.set_thumbnail(url=nhl_icon)
        em.timestamp = utc_to_local(self.last_timestamp(), "UTC")
        em.set_footer(text="Stats Last Updated", icon_url=nhl_icon)
        return em

    async def make_division_standings_embeds(self) -> List[discord.Embed]:
        ret = []
        for division in Divisions:
            ret.append(await self.make_division_standings_embed(division))
        return ret

    def make_table(
        self,
        records: Dict[str, TeamRecord],
        rank_type: Literal["division", "conference", "league"],
    ) -> str:
        headers = ("Rank", "Team", "GP", "W", "L", "OT", "P")
        # "P%", "RW", "G/G", "GA/G", "PP%", "S/G", "SA/G", "FO%")
        post_data = []
        for name, record in records.items():
            tri_code = TEAMS[name]["tri_code"]
            wc = "*" if record.wildcard_rank in range(1, 3) else ""
            rank = getattr(record, f"{rank_type}_rank")
            post_data.append(
                [
                    f"{rank}{wc}",
                    tri_code,
                    record.games_played,
                    record.league_record.wins,
                    record.league_record.losses,
                    record.league_record.ot,
                    record.points,
                ]
            )
        return tabulate(
            sorted(post_data, key=lambda x: int(x[0].replace("*", ""))),
            headers=headers,
            numalign="center",
            tablefmt="plain",
        )

    def get_division_table(self, division: Divisions) -> str:
        records = {}
        for name, record in self.all_records.items():
            if record.division.name != division.name:
                continue
            records[name] = record
        return self.make_table(records, "division")

    def get_conference_table(self, conference: Conferences) -> str:
        records = {}
        for name, record in self.all_records.items():
            if record.conference.name != conference.name:
                continue
            records[name] = record
        return self.make_table(records, "division")

    def get_all_table(self):
        records = {}
        for name, record in self.all_records.items():
            records[name] = record
        return self.make_table(records, "division")

    def get_division_str(self, division: Divisions) -> str:
        msg = ""
        for name, record in self.all_records.items():
            if record.division.name.lower() != division.name.lower():
                continue
            emoji = discord.PartialEmoji.from_str(TEAMS.get(name, {"emoji": ""})["emoji"])
            msg += f"{record.division_rank}. {emoji} {record}"
        return msg

    def get_conference_str(self, conference: Conferences) -> str:
        team_str = []
        for name, record in self.all_records.items():
            if record.conference.name.lower() != conference.name.lower():
                continue
            team_str.append(
                (
                    record.conference_rank,
                    (f"{record.conference_rank}. {record}"),
                )
            )
        return "".join(i[1] for i in sorted(team_str, key=lambda x: x[0]))

    def get_all_str(self):
        msg = ""
        records = [(r.league_rank, r) for name, r in self.all_records.items()]
        for rank, record in sorted(records, key=lambda x: x[0]):
            emoji = discord.PartialEmoji.from_str(
                TEAMS.get(record.team.name, {"emoji": ""})["emoji"]
            )
            msg += f"{record.league_rank}. {emoji} {record}"
        return msg

    async def make_division_standings_embed(
        self, division: Divisions, table: bool = True
    ) -> discord.Embed:
        em = discord.Embed()
        # timestamp = datetime.strptime(record[0].last_updated, "%Y-%m-%dT%H:%M:%SZ")
        em.timestamp = self.last_timestamp(division=division)
        if table:
            msg = box(self.get_division_table(division), lang="ansi")
        else:
            msg = self.get_division_str(division)
        em.description = msg
        division_logo = TEAMS["Team {}".format(division.name)]["logo"]
        em.colour = int(TEAMS["Team {}".format(division.name)]["home"].replace("#", ""), 16)
        em.set_author(
            name=division.name + " Division",
            url="https://www.nhl.com/standings",
            icon_url=division_logo,
        )
        em.set_footer(text="Stats last Updated", icon_url=division_logo)
        em.set_thumbnail(url=division_logo)
        return em

    async def make_conference_standings_embeds(self) -> List[discord.Embed]:
        ret = []
        for conference in Conferences:
            ret.append(await self.make_conference_standings_embed(conference))
        return ret

    async def make_conference_standings_embed(
        self, conference: Conferences, table: bool = True
    ) -> discord.Embed:
        em = discord.Embed()
        em.timestamp = utc_to_local(self.last_timestamp(conference=conference), "UTC")
        if table:
            msg = box(self.get_conference_table(conference), lang="ansi")
        else:
            msg = self.get_conference_str(conference)
        em.description = msg
        em.colour = int("c41230", 16) if conference == "Eastern" else int("003e7e", 16)
        logo = {
            "Eastern": (
                "https://upload.wikimedia.org/wikipedia/en/thumb/1/"
                "16/NHL_Eastern_Conference.svg/1280px-NHL_Eastern_Conference.svg.png"
            ),
            "Western": (
                "https://upload.wikimedia.org/wikipedia/en/thumb/6/"
                "65/NHL_Western_Conference.svg/1280px-NHL_Western_Conference.svg.png"
            ),
        }
        em.set_author(
            name=conference.name + " Conference",
            url="https://www.nhl.com/standings",
            icon_url=logo[conference.name],
        )
        em.set_thumbnail(url=logo[conference.name])
        em.set_footer(text="Stats last Updated", icon_url=logo[conference.name])
        return em

    async def make_team_standings_embeds(self) -> List[discord.Embed]:
        ret = []
        for team, data in TEAMS.items():
            if not data["active"]:
                continue
            ret.append(await self.make_team_standings_embed(team))
        return ret

    async def make_team_standings_embed(self, team: str) -> discord.Embed:
        record = self.all_records.get(team)
        if record is None:
            raise KeyError(f"{team} is not an available team.")

        em = discord.Embed()
        em.set_author(
            name="# {} {}".format(record.league_rank, record.team.name),
            url="https://www.nhl.com/standings",
            icon_url=TEAMS[record.team.name]["logo"],
        )
        headers = ("Stat", "Rank")
        conference_data = [
            [_("Rank"), record.conference_rank],
            [_("Home"), record.conference_home_rank],
            [_("Road"), record.conference_road_rank],
            [_("PP"), record.pp_conference_rank],
            [_("L10"), record.conference_l10_rank],
        ]
        division_data = [
            [_("Rank"), record.division_rank],
            [_("Home"), record.division_home_rank],
            [_("Road"), record.division_road_rank],
            [_("PP"), record.pp_division_rank],
            [_("L10"), record.division_l10_rank],
        ]
        league_data = [
            [_("Rank"), record.league_rank],
            [_("Home"), record.league_home_rank],
            [_("Road"), record.league_road_rank],
            [_("PP"), record.pp_league_rank],
            [_("L10"), record.league_l10_rank],
        ]
        conference_table = tabulate(conference_data, headers=headers)
        division_table = tabulate(division_data, headers=headers)
        league_table = tabulate(league_data, headers=headers)
        em.colour = int(TEAMS[record.team.name]["home"].replace("#", ""), 16)
        # em.set_thumbnail(url=TEAMS[record.team.name]["logo"])
        em.add_field(
            name=f"{record.division.name} Division", value=box(division_table, lang="ansi")
        )
        em.add_field(
            name=f"{record.conference.name} Conference", value=box(conference_table, lang="ansi")
        )
        em.add_field(name="League", value=box(league_table, lang="ansi"))
        em.add_field(
            name="Wins (Regulation)",
            value=f"{record.league_record.wins} ({record.regulation_wins})",
        )
        em.add_field(name="Losses", value=str(record.league_record.losses))
        em.add_field(name="OT", value=str(record.league_record.ot))
        em.add_field(name="Games Played", value=str(record.games_played))
        em.add_field(name="Points", value=str(record.points))
        em.add_field(name="Points %", value=f"{record.points_percentage:.3}")
        em.add_field(name="Goals Scored", value=str(record.goals_scored))
        em.add_field(name="Goals Against", value=str(record.goals_against))
        em.add_field(name="Goals Diff.", value=str(record.goals_scored - record.goals_against))
        em.add_field(name="G/G", value=f"{record.gpg:.3}")
        em.add_field(name="GA/G", value=f"{record.gaa:.3}")
        em.add_field(
            name="Current Streak",
            value=str(record.streak),
        )
        # timestamp = datetime.strptime(record.last_updated, "%Y-%m-%dT%H:%M:%SZ")
        em.timestamp = utc_to_local(record.last_updated, "UTC")
        em.set_footer(text="Stats last Updated", icon_url=TEAMS[record.team.name]["logo"])
        return em


class StandingsPages(menus.ListPageSource):
    def __init__(self, pages: List[discord.Embed]):
        super().__init__(pages, per_page=1)

    async def format_page(self, view: discord.ui.View, page: discord.Embed) -> discord.Embed:
        return page


class StandingsMenu(discord.ui.View):
    def __init__(self, standings: Standings, start: str):
        super().__init__()
        self.standings = standings
        self.pages: List[discord.Embed] = []
        self.context = "all"
        self.current_page = 0
        self.search = start
        self._source = None
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.team_button = TeamButton(discord.ButtonStyle.grey, 1)
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.team_button)

    async def set_context(self, search: str):
        context_re = {
            "conference": re.compile(r"conference|eastern|western", flags=re.I),
            "division": re.compile(
                r"division|metro(?=politan)?|pacific|atlantic|central", flags=re.I
            ),
            "all": re.compile(r"all", flags=re.I),
            "league": re.compile(r"league", flags=re.I),
            "team": ACTIVE_TEAM_RE,
        }
        if search is None:
            return
        for key, value in context_re.items():
            if value.search(search) and key != self.context:
                self.context = key

    async def prepare(self):
        embeds_mapping = {
            "team": self.standings.make_team_standings_embeds,
            "division": self.standings.make_division_standings_embeds,
            "conference": self.standings.make_conference_standings_embeds,
            "all": self.standings.all_standing_embed,
            "league": self.standings.league_standing_embed,
        }
        if self.context not in ["all", "league"]:
            self.pages = await embeds_mapping[self.context]()
        else:
            self.pages = [await embeds_mapping[self.context]()]
        self._source = StandingsPages(self.pages)
        if len(self.pages) == 1:
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
        else:
            self.forward_button.disabled = False
            self.back_button.disabled = False
            self.first_item.disabled = False
            self.last_item.disabled = False

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        await self.set_context(self.search)
        await self.prepare()
        await self.source._prepare_once()
        self.ctx = ctx
        self.author = ctx.message.author
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        if interaction.response.is_done():
            await interaction.followup.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(self, ctx: commands.Context) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        if self.search is not None:
            for page in self.pages:
                if self.search.lower() in page.author.name.lower():
                    self.current_page = self.pages.index(page)
        page = await self.source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        return await ctx.send(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self.source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.grey, label="All", row=1)
    async def all_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.context = "all"
        await self.prepare()
        await self.show_page(0, interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, label="League", row=1)
    async def leagues(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.context = "league"
        await self.prepare()
        await self.show_page(0, interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, label="Conferences", row=1)
    async def conferences(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.context = "conference"
        await self.prepare()
        await self.show_page(0, interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, label="Divisions", row=1)
    async def divisions(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.context = "division"
        await self.prepare()
        await self.show_page(0, interaction)
