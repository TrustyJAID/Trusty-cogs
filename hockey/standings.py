from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Literal, Optional

import aiohttp
import discord
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.vendored.discord.ext import menus

from .components import (
    BackButton,
    FirstItemButton,
    ForwardButton,
    LastItemButton,
    StopButton,
    TeamButton,
)
from .constants import BASE_URL, TEAMS
from .helper import ACTIVE_TEAM_RE, utc_to_local

if TYPE_CHECKING:
    from redbot.core import Config, commands

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")

DIVISIONS: List[str] = ["division", "metropolitan", "atlantic", "central", "pacific"]

DIVISIONS_TYPE = Literal["division", "metropolitan", "atlantic", "central", "pacific"]

CONFERENCES: List[str] = ["eastern", "western", "conference"]

CONFERENCES_TYPE = Literal["eastern", "western", "conference"]
# The NHL removed conferences from the standings in the 2021 season


@dataclass
class Team:
    id: int
    name: str
    link: str


@dataclass
class LeagueRecord:
    wins: int
    losses: int
    ot: int
    type: Literal["league"]


@dataclass
class Streak:
    streakType: Literal["ot", "wins", "losses"]
    streakNumber: int
    streakCode: str


@dataclass
class Division:
    id: int
    name: str
    nameShort: str
    link: str
    abbreviation: str


@dataclass
class Conference:
    id: int
    name: str
    link: str


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
    wildcard_rank: int
    row: int
    games_played: int
    streak: Streak
    points_percentage: float
    pp_division_rank: int
    pp_conference_rank: int
    last_updated: datetime

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
            wildcard_rank=int(data["wildCardRank"]),
            row=int(data["row"]),
            games_played=int(data["gamesPlayed"]),
            streak=Streak(**data["streak"]),
            points_percentage=float(data["pointsPercentage"]),
            pp_division_rank=int(data["ppDivisionRank"]),
            pp_conference_rank=int(data["ppConferenceRank"]),
            last_updated=datetime.strptime(data["lastUpdated"], "%Y-%m-%dT%H:%M:%SZ"),
        )


class Standings:
    def __init__(self, records: dict = {}):
        super().__init__()
        self.all_records = records
        self.conferences = ["Eastern", "Western"]
        self.divisions = ["Metropolitan", "Atlantic", "Central", "Pacific"]

    def last_timestamp(
        self,
        *,
        division: Optional[DIVISIONS_TYPE] = None,
        conference: Optional[CONFERENCES_TYPE] = None,
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
        config = bot.get_cog("Hockey").config
        standings = await Standings.get_team_standings()

        all_guilds = await config.all_guilds()
        async for guild_id, data in AsyncIter(all_guilds.items(), steps=100):
            guild = bot.get_guild(guild_id)
            if guild is None:
                continue
            log.debug(guild.name)
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

                if search in DIVISIONS:
                    em = await standings.make_division_standings_embed(search)

                elif search in CONFERENCES:
                    em = await standings.make_conference_standings_embed(search)
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

    async def all_standing_embed(self) -> discord.Embed:
        """
        Builds the standing embed when all TEAMS are selected
        """
        em = discord.Embed()
        new_dict = {}
        nhl_icon = "https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png"
        latest_timestamp = self.last_timestamp()
        for team_name, team in self.all_records.items():
            if team.division.name not in new_dict:
                new_dict[team.division.name] = ""
            emoji = TEAMS[team.team.name]["emoji"]
            wildcard = f"(WC{team.wildcard_rank})" if team.wildcard_rank in ["1", "2"] else ""
            new_dict[team.division.name] += (
                f"{team.division_rank}. <:{emoji}> GP: **{team.games_played}** "
                f"W: **{team.league_record.wins}** L: **{team.league_record.losses}** OT: "
                f"**{team.league_record.ot}** PTS: **{team.points}** {wildcard}\n"
            )
        for div in new_dict:
            em.add_field(name=f"{div} Division", value=new_dict[div], inline=False)
        em.set_author(
            name="NHL Standings",
            url="https://www.nhl.com/standings",
            icon_url="https://cdn.bleacherreport.net/images/team_logos/328x328/nhl.png",
        )
        em.set_thumbnail(url=nhl_icon)
        em.timestamp = utc_to_local(latest_timestamp, "UTC")
        em.set_footer(text="Stats Last Updated", icon_url=nhl_icon)
        return em

    async def make_division_standings_embeds(self) -> List[discord.Embed]:
        ret = []
        for division in self.divisions:
            ret.append(await self.make_division_standings_embed(division))
        return ret

    async def make_division_standings_embed(self, division: DIVISIONS_TYPE) -> discord.Embed:
        em = discord.Embed()
        msg = ""
        # timestamp = datetime.strptime(record[0].last_updated, "%Y-%m-%dT%H:%M:%SZ")
        em.timestamp = self.last_timestamp(division=division)

        for name, team in self.all_records.items():
            if team.division.name.lower() != division.lower():
                continue
            emoji = TEAMS[team.team.name]["emoji"]
            wildcard = f"(WC{team.wildcard_rank})" if team.wildcard_rank in ["1", "2"] else ""
            msg += (
                f"{team.division_rank}. <:{emoji}> GP: **{team.games_played}** "
                f"W: **{team.league_record.wins}** L: **{team.league_record.losses}** OT: "
                f"**{team.league_record.ot}** PTS: **{team.points}** {wildcard}\n"
            )
        em.description = msg
        division_logo = TEAMS["Team {}".format(division.title())]["logo"]
        em.colour = int(TEAMS["Team {}".format(division.title())]["home"].replace("#", ""), 16)
        em.set_author(
            name=division.title() + " Division",
            url="https://www.nhl.com/standings",
            icon_url=division_logo,
        )
        em.set_footer(text="Stats last Updated", icon_url=division_logo)
        em.set_thumbnail(url=division_logo)
        return em

    async def make_conference_standings_embeds(self) -> List[discord.Embed]:
        ret = []
        for conference in self.conferences:
            ret.append(await self.make_conference_standings_embed(conference))
        return ret

    async def make_conference_standings_embed(self, conference: CONFERENCES_TYPE) -> discord.Embed:
        conference = conference.title()
        em = discord.Embed()
        team_str = []
        for name, team in self.all_records.items():
            if team.conference.name.lower() != conference.lower():
                continue
            emoji = TEAMS[team.team.name]["emoji"]
            team_str.append(
                (
                    team.conference_rank,
                    (
                        f"{team.conference_rank}. <:{emoji}> GP: **{team.games_played}** "
                        f"W: **{team.league_record.wins}** L: **{team.league_record.losses}** OT: "
                        f"**{team.league_record.ot}** PTS: **{team.points}**\n"
                    ),
                )
            )
        msg = "".join(i[1] for i in sorted(team_str, key=lambda x: x[0]))
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
            name=conference + " Conference",
            url="https://www.nhl.com/standings",
            icon_url=logo[conference],
        )
        em.set_thumbnail(url=logo[conference])
        em.set_footer(text="Stats last Updated", icon_url=logo[conference])
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
        em.colour = int(TEAMS[record.team.name]["home"].replace("#", ""), 16)
        em.set_thumbnail(url=TEAMS[record.team.name]["logo"])
        em.add_field(name="Division", value=f"# {record.division_rank}")
        em.add_field(name="Conference", value=f"# {record.conference_rank}")
        em.add_field(name="Wins", value=str(record.league_record.wins))
        em.add_field(name="Losses", value=str(record.league_record.losses))
        em.add_field(name="OT", value=str(record.league_record.ot))
        em.add_field(name="Points", value=str(record.points))
        em.add_field(name="Games Played", value=str(record.games_played))
        em.add_field(name="Goals Scored", value=str(record.goals_scored))
        em.add_field(name="Goals Against", value=str(record.goals_against))
        em.add_field(
            name="Current Streak",
            value="{} {}".format(record.streak.streakNumber, record.streak.streakType),
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
        }
        if self.context != "all":
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
        self.message = await self.send_initial_message(ctx, ctx.channel)

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

    async def send_initial_message(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        is_slash = False

        if isinstance(ctx, discord.Interaction):
            is_slash = True
        if self.search is not None:
            for page in self.pages:
                if self.search.lower() in page.author.name.lower():
                    self.current_page = self.pages.index(page)
        page = await self.source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        if is_slash:
            self.author = ctx.user
            return await ctx.followup.send(**kwargs, view=self, wait=True)
        else:
            self.author = ctx.author
            return await channel.send(**kwargs, view=self)

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
