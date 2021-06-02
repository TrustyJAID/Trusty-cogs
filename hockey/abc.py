import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Literal, Optional, Dict, Union

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .game import Game
from .helper import (
    HockeyStandings,
    HockeyStates,
    HockeyTeams,
    TeamDateFinder,
    YearFinder,
    TimezoneFinder,
)
from .pickems import Pickems


class MixinMeta(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.
    """

    def __init__(self, *_args):
        self.config: Config
        self.bot: Red
        self.loop: Optional[asyncio.Task]
        self.TEST_LOOP: bool
        self.all_pickems: dict
        self.session: aiohttp.ClientSession
        self.pickems_config: Config
        self._ready: asyncio.Event

    #######################################################################
    # hockey_commands.py                                                  #
    #######################################################################

    @abstractmethod
    async def hockey_commands(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def version(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def hockeyhub(self, ctx: commands.Context, *, search: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def team_role(self, ctx: commands.Context, *, team: HockeyTeams) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def team_goals(self, ctx: commands.Context, *, team: HockeyTeams = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def standings(self, ctx: commands.Context, *, search: HockeyStandings = None) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def games(
        self, ctx: commands.Context, *, teams_and_date: Optional[TeamDateFinder] = {}
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def schedule(
        self, ctx: commands.Context, *, teams_and_date: Optional[TeamDateFinder] = {}
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def player_id_lookup(self, name: str) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def player(
        self,
        ctx: commands.Context,
        *,
        search: str,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def roster(
        self, ctx: commands.Context, season: Optional[YearFinder] = None, *, search: HockeyTeams
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def rules(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def post_leaderboard(
        self, ctx: commands.Context, leaderboard_type: Literal["season", "weekly", "worst"]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def leaderboard(self, ctx: commands.Context, leaderboard_type: str = "seasonal") -> None:
        raise NotImplementedError()

    @abstractmethod
    async def setrules(self, ctx: commands.Context, team: HockeyTeams, *, rules) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def otherdiscords(self, ctx: commands.Context, team: HockeyTeams) -> None:
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
    async def gdc_default_game_state(self, ctx: commands.Context, *state: HockeyStates) -> None:
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
        team: HockeyTeams,
        category: discord.CategoryChannel = None,
        delete_gdc: bool = True,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chn_name(self, game: Game) -> str:
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
    # hockeyset.py                                                        #
    #######################################################################

    @commands.group(name="hockeyset", aliases=["nhlset"])
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
    async def set_hockey_timezone(
        self, ctx: commands.Context, timezone: Optional[TimezoneFinder] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def list_hockey_timezones(self, ctx: commands.Context) -> None:
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
    async def check_notification_settings(self, guild: discord.Guild) -> str:
        raise NotImplementedError

    @abstractmethod
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_goal_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
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

    @abstractmethod
    async def set_game_start_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_channel_goal_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_channel_game_start_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
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
        self, ctx: commands.Context, channel: discord.TextChannel, *state: HockeyStates
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def set_game_publish_updates(
        self, ctx: commands.Context, channel: discord.TextChannel, *state: HockeyStates
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def add_goals(
        self, ctx: commands.Context, team: HockeyTeams, channel: Optional[discord.TextChannel]
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def remove_goals(
        self,
        ctx: commands.Context,
        team: Optional[HockeyTeams] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        raise NotImplementedError()

    #######################################################################
    # hockeypickems.py                                                    #
    #######################################################################

    @abstractmethod
    async def on_hockey_preview_message(
        self, channel: discord.TextChannel, message: discord.Message, game: Game
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def handle_pickems_response(
        self,
        user: discord.Member,
        channel: discord.TextChannel,
        emoji: Optional[Union[discord.Emoji, str]],
        message_id: int,
        reply_message: Optional[str],
    ):
        raise NotImplementedError()

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
    async def set_guild_pickem_winner(self, game: Game) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def edit_pickems_message(
        self, channel: discord.TextChannel, message_id: int, content: str
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def create_pickem_object(
        self,
        guild: discord.Guild,
        message: discord.Message,
        channel: discord.TextChannel,
        game: Game,
    ) -> bool:
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
    async def set_pickems_timezone(
        self, ctx: commands.Context, timezone: Optional[TimezoneFinder] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def setup_auto_pickems(
        self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_auto_pickems(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def toggle_auto_pickems(self, ctx: commands.Context) -> None:
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
    async def lights(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def testloop(self, ctx: commands.Context) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def clear_seasonal_leaderboard_all(self, ctx: commands.Context) -> None:
        raise NotImplementedError()
