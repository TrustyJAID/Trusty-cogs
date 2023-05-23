from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import aiohttp
import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify

from .components import StopButton
from .constants import BASE_URL
from .errors import NoStats
from .game import Team

_ = Translator("Hockey", __file__)


# https://github.com/Rapptz/discord.py/blob/1bfe6b2bb160ce802a1f08afed73941a19a0a651/discord/app_commands/commands.py#L132
CAMEL_CASE_REGEX = re.compile(r"(?<!^)(?=[A-Z])")


# https://github.com/Rapptz/discord.py/blob/1bfe6b2bb160ce802a1f08afed73941a19a0a651/discord/app_commands/commands.py#L190-L191
def _fix_camel_case(text: str) -> str:
    return CAMEL_CASE_REGEX.sub(" ", text).title()


class LeaderCategories(Enum):
    goals = "goals"
    assists = "assists"
    savePct = "savePct"
    shutouts = "shutouts"
    wins = "wins"
    gaa = "gaa"
    plusMinus = "plusMinus"
    points = "points"
    powerPlayGoals = "powerPlayGoals"
    shortHandedGoals = "shortHandedGoals"
    timeOnIcePerGame = "timeOnIcePerGame"
    faceOffPct = "faceOffPct"
    otLosses = "otLosses"
    losses = "losses"
    shortHandedAssists = "shortHandedAssists"
    pointsPerGame = "pointsPerGame"
    powerPlayPoints = "powerPlayPoints"
    shootingPctg = "shootingPctg"
    hits = "hits"
    shortHandedPoints = "shortHandedPoints"
    penaltyMinutes = "penaltyMinutes"
    shots = "shots"
    powerPlayAssists = "powerPlayAssists"
    gameWinningGoals = "gameWinningGoals"

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> LeaderCategories:
        try:
            ret = cls(argument)
        except ValueError:
            raise commands.BadArgument("`{argument}` is not a valid category.")
        return ret


@dataclass
class GameType:
    id: str
    description: str
    postseason: bool


@dataclass
class Person:
    id: int
    full_name: str
    link: str

    @classmethod
    def from_json(cls, data: dict) -> Person:
        return cls(full_name=data.pop("fullName"), **data)


@dataclass
class Leader:
    rank: int
    value: str
    team: Team
    person: Person
    season: Optional[str]

    @classmethod
    def from_json(cls, data: dict) -> Leader:
        return cls(
            rank=data["rank"],
            value=data["value"],
            team=Team(**data["team"]),
            person=Person.from_json(data["person"]),
            season=data.get("season", None),
        )


@dataclass
class LeagueLeaders:
    leader_category: LeaderCategories
    depth: str
    player_status: str
    season: str
    game_type: GameType
    limit_metadata: dict
    leaders: List[Leader]

    @classmethod
    def from_json(cls, data: dict) -> LeagueLeaders:
        return cls(
            leader_category=LeaderCategories(data["leaderCategory"]),
            depth=data["depth"],
            player_status=data["playerStatus"],
            season=data["season"],
            game_type=GameType(**data["gameType"]),
            limit_metadata=data["limitMetadata"],
            leaders=[Leader.from_json(leader) for leader in data["leaders"]],
        )

    @classmethod
    async def from_url(
        cls, url: str, /, *, session: Optional[aiohttp.ClientSession] = None
    ) -> LeagueLeaders:
        if session is None:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
        else:
            async with session.get(url) as resp:
                data = await resp.json()
        return cls.from_json(data["leagueLeaders"][0])

    @classmethod
    async def get(
        cls,
        category: LeaderCategories,
        season: Optional[str] = None,
        limit: int = 10,
        /,
        *,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> LeagueLeaders:
        url = f"{BASE_URL}/api/v1/stats/leaders?leaderCategories={category.value}&limit={limit}"
        if season is not None:
            url += f"&season={season}"
        try:
            return await cls.from_url(url, session=session)
        except (KeyError, IndexError):
            raise NoStats(f"`{category.name}` has no stats available for season `{season}`.")

    def embed(self) -> discord.Embed:
        title = f"Top {_fix_camel_case(self.leader_category.value)} for {self.season}"
        em = discord.Embed(title=title)
        msg = ""
        for player in self.leaders:
            msg += f"{player.rank}. {player.person.full_name} - {player.value}\n"

        em.description = list(pagify(msg, delims=["\n"], page_length=4096))[0]
        return em


class LeaderCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=_fix_camel_case(i.name), value=i.name)
            for i in LeaderCategories
        ]
        super().__init__(
            min_values=1, max_values=1, options=options, placeholder=_("Pick a category")
        )

    async def callback(self, interaction: discord.Interaction):
        category = LeaderCategories(self.values[0])
        self.view.category = category
        await self.view.show_page(interaction)


class SeasonModal(discord.ui.Modal):
    def __init__(self, view: discord.ui.View):
        super().__init__(title=_("Season"))
        self.view = view
        cur_season = self.view.season
        self.date = discord.ui.TextInput(
            style=discord.TextStyle.short,
            label="Season",
            placeholder="YYYY-YYYY",
            default=cur_season,
            min_length=8,
            max_length=9,
            required=True,
        )
        self.add_item(self.date)

    async def on_submit(self, interaction: discord.Interaction):
        if self.date.value:
            new_season = self.date.value.replace("-", "")
            if not new_season.isdigit() and len(new_season) != 8:
                await interaction.response.send_message(
                    "That is not a valid season.", ephemeral=True
                )
                return
            self.view.season = new_season

        await self.view.show_page(interaction=interaction)


class SeasonButton(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, row: Optional[int] = None):
        super().__init__(style=style, row=row, label=_("Season"))
        self.style = style

    async def callback(self, interaction: discord.Interaction):
        """stops the pagination session."""
        modal = SeasonModal(self.view)
        await interaction.response.send_modal(modal)


class LeaderView(discord.ui.View):
    def __init__(
        self,
        category: LeaderCategories,
        season: Optional[str],
        limit: int = 10,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        super().__init__()
        self.season = season.replace("-", "") if season is not None else season
        self.category = category
        self.limit = limit
        self.leaders: Optional[LeagueLeaders] = None
        self.session = session
        self.ctx = None
        self.stop_button = StopButton()
        self.add_item(self.stop_button)
        self.season_button = SeasonButton(discord.ButtonStyle.blurple)
        self.add_item(self.season_button)
        self.select_menu = LeaderCategorySelect()
        self.add_item(self.select_menu)

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.author = ctx.author
        try:
            em = await self.get_page()
        except NoStats as e:
            await ctx.send(e, ephemeral=True)
            return
        self.message = await ctx.send(embed=em, view=self)

    async def get_page(self) -> discord.Embed:
        self.leaders = await LeagueLeaders.get(
            self.category, self.season, self.limit, session=self.session
        )
        return self.leaders.embed()

    async def show_page(self, interaction: discord.Interaction):
        try:
            em = await self.get_page()
        except IndexError:
            await interaction.response.send_message(
                _("Some of the provided inputs were invalid. Try again."), ephemeral=True
            )
            return
        await interaction.response.edit_message(embed=em)

    async def interaction_check(self, interaction: discord.Interaction):
        if self.author.id != interaction.user.id:
            await interaction.response.send_message(
                _("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
