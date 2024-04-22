import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .api import HockeyAPI
from .game import Game
from .helper import (
    DateFinder,
    LeaderboardFinder,
    PlayerFinder,
    StandingsFinder,
    StateFinder,
    TeamFinder,
    YearFinder,
)
from .pickems import Pickems
from .stats import LeaderCategories


class HockeyMixin(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.
    """

    def __init__(self, *_args):
        super().__init__()
        self.config: Config
        self.bot: Red
        self.loop: Optional[asyncio.Task]
        self.TEST_LOOP: bool
        self.all_pickems: Dict[str, Dict[str, Pickems]]
        self.session: aiohttp.ClientSession
        self.pickems_config: Config
        self._ready: asyncio.Event
        self.api: HockeyAPI

    #######################################################################
    # hockey_commands.py                                                  #
    #######################################################################

    @commands.hybrid_group(name="hockey", aliases=["nhl"])
    async def hockey_commands(self, ctx: commands.Context) -> None:
        """
        Get information from NHL.com
        """
        pass

    @abstractmethod
    async def version(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def hockeyhub(self, ctx: commands.Context, *, search: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def team_role(self, ctx: commands.Context, *, team: TeamFinder) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def team_goals(self, ctx: commands.Context, *, team: TeamFinder = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def standings(self, ctx: commands.Context, *, search: StandingsFinder = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def games(
        self,
        ctx: commands.Context,
        *,
        team: Optional[TeamFinder],
        date: Optional[DateFinder],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def heatmap(
        self,
        ctx: commands.Context,
        style: Literal["all", "ev", "5v5", "sva", "home5v4", "away5v4"] = "all",
        *,
        team: Optional[TeamFinder],
        date: Optional[DateFinder],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gameflow(
        self,
        ctx: commands.Context,
        strength: Literal["all", "ev", "5v5", "sva"] = "all",
        corsi: bool = True,
        *,
        team: Optional[TeamFinder],
        date: Optional[DateFinder],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def schedule(
        self,
        ctx: commands.Context,
        *,
        team: Optional[TeamFinder],
        date: Optional[DateFinder],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def recap(
        self,
        ctx: commands.Context,
        *,
        team: Optional[TeamFinder],
        date: Optional[DateFinder],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def player(
        self,
        ctx: commands.Context,
        season: Optional[YearFinder],
        *,
        player: PlayerFinder,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roster(
        self,
        ctx: commands.Context,
        season: Optional[YearFinder],
        *,
        team: TeamFinder,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def hockey_stats(
        self,
        ctx: commands.Context,
        category: Optional[LeaderCategories],
        season: Optional[str],
        limit: Optional[int] = 10,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def rules(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def post_leaderboard(
        self,
        ctx: commands.Context,
        leaderboard_type: Literal[
            "season",
            "weekly",
            "worst",
            "playoffs",
            "playoffs_weekly",
            "pre-season",
            "pre-season_weekly",
        ],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def leaderboard(
        self, ctx: commands.Context, leaderboard_type: Optional[LeaderboardFinder]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def setrules(self, ctx: commands.Context, team: TeamFinder, *, rules) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def otherdiscords(self, ctx: commands.Context, team: TeamFinder) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_image(self, file_name: str, url: str) -> discord.File:
        raise NotImplementedError()

    #######################################################################
    # gamedaychannels.py                                                  #
    #######################################################################

    @abstractmethod
    async def gdc(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_delete(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_default_game_state(self, ctx: commands.Context, *state: StateFinder) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_create(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_toggle(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_category(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_autodelete(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def test_gdc(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdc_setup(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        category: discord.CategoryChannel = None,
        delete_gdc: bool = True,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def check_new_gdc(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_gdc(self, guild: discord.Guild, game_data: Optional[Game] = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_gdc(self, guild: discord.Guild) -> None:
        raise NotImplementedError()

    #######################################################################
    # gamedaythreads.py                                                   #
    #######################################################################

    @abstractmethod
    async def gdt(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_delete(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_default_game_state(self, ctx: commands.Context, *state: StateFinder) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_create(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_toggle(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_channel(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def test_gdt(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def gdt_setup(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        category: discord.CategoryChannel = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def check_new_gdt(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_gdt(self, guild: discord.Guild, game_data: Optional[Game] = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_gdt(self, guild: discord.Guild) -> None:
        raise NotImplementedError()

    #######################################################################
    # hockeyset.py                                                        #
    #######################################################################

    @hockey_commands.group(name="set")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_channels=True)
    async def hockeyset_commands(self, ctx: commands.Context) -> None:
        """
        Setup Hockey commands for the server
        """
        pass

    @abstractmethod
    async def hockey_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def leaderboardset(
        self,
        ctx: commands.Context,
        user: discord.Member,
        season: int,
        weekly: int = None,
        total: int = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def post_standings(
        self,
        ctx: commands.Context,
        standings_type: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def togglestandings(self, ctx: commands.Context):
        raise NotImplementedError()

    @abstractmethod
    async def set_game_state_updates(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        *state: StateFinder,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def add_goals(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove_goals(
        self,
        ctx: commands.Context,
        team: Optional[TeamFinder] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # notifications.py                                                    #
    #######################################################################

    @abstractmethod
    def get_role_info(self, guild: discord.Guild, data: dict) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def check_channel_notification_settings(self, channel: discord.TextChannel) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def check_default_notification_settings(self, guild: discord.Guild) -> str:
        raise NotImplementedError

    @abstractmethod
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def hockey_notification_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_default_game_start_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_default_goal_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_default_state_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_game_start_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_goal_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_state_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_ot_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_so_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # hockeypickems.py                                                    #
    #######################################################################

    @abstractmethod
    async def pickems_loop(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def save_pickems_data(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def after_pickems_loop(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def before_pickems_loop(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def pickems_name(self, game: Game) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def find_pickems_object(self, game: Game) -> List[Pickems]:
        raise NotImplementedError()

    @abstractmethod
    async def disable_pickems_buttons(self, game: Game) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_guild_pickem_winner(self, game: Game) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_pickems_message(
        self, channel: discord.TextChannel, message_id: int, content: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_pickem_object(
        self,
        guild: discord.Guild,
        game: Game,
    ) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def fix_pickem_game_start(self, game: Game):
        raise NotImplementedError()

    @abstractmethod
    async def reset_weekly(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def add_weekly_pickems_credits(
        self, guild: discord.Guild, top_members: List[int]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_pickems_channel(
        self, name: str, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        raise NotImplementedError()

    @abstractmethod
    async def make_pickems_msg(self, guild: discord.Guild, game: Game) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def create_pickems_game_message(self, channel: discord.TextChannel, game: Game):
        raise NotImplementedError()

    @abstractmethod
    async def create_pickems_channels_and_message(
        self, guilds: List[discord.Guild], day: datetime
    ) -> Dict[int, List[int]]:
        raise NotImplementedError()

    @abstractmethod
    async def create_next_pickems_day(self, guilds: List[discord.Guild]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_weekly_pickems_pages(self, guilds: List[discord.Guild]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_pickems_channels(self, guild: discord.Guild, channels: List[int]) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def tally_guild_leaderboard(self, guild: discord.Guild) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def tally_leaderboard(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_commands(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_settings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_credits(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_credits_base(
        self, ctx: commands.Context, credits: Optional[int] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_credits_top(
        self, ctx: commands.Context, credits: Optional[int] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_credits_amount(
        self, ctx: commands.Context, amount: Optional[int] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_pickems_message(
        self, ctx: commands.Context, *, message: Optional[str] = ""
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def setup_auto_pickems(
        self,
        ctx: commands.Context,
        category: Optional[discord.CategoryChannel] = None,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_auto_pickems(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_page(self, ctx, date: Optional[str] = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def rempickem(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_leaderboard_commands(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_server_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def tally_server_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_weekly_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_seasonal_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_weekly_playoffs_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_playoffs_leaderboard(self, ctx: commands.Context, true_or_false: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_weekly_preseason_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_preseason_leaderboard(
        self, ctx: commands.Context, true_or_false: bool
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # dev.py                                                              #
    #######################################################################

    @abstractmethod
    async def hockeydev(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def reset_weekly_pickems_data(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def getgoals(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def pickems_tally(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove_old_pickems(
        self, ctx: commands.Context, year: int, month: int, day: int
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def check_pickem_winner(self, ctx: commands.Context, days: int = 1) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def fix_all_pickems(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def teststandings(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cogstats(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def customemoji(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def resetgames(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def setcreated(self, ctx: commands.Context, created: bool) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def cleargdc(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_broken_channels(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove_broken_guild(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def testloop(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_seasonal_leaderboard_all(self, ctx: commands.Context) -> None:
        raise NotImplementedError()
