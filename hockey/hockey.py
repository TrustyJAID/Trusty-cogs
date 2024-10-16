from __future__ import annotations

import asyncio
import json
from abc import ABC
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import aiohttp
import discord
import yaml
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box

from .api import GameState, NewAPI, Schedule
from .constants import BASE_URL, CONFIG_ID, CONTENT_URL, HEADSHOT_URL, TEAMS
from .dev import HockeyDev
from .errors import InvalidFileError
from .gamedaychannels import GameDayChannels
from .gamedaythreads import GameDayThreads
from .helper import utc_to_local
from .hockey_commands import HockeyCommands
from .hockeypickems import HockeyPickems
from .hockeyset import HockeySetCommands
from .notifications import HockeyNotifications
from .pickems import Pickems
from .standings import Standings

if TYPE_CHECKING:
    from .game import Game
    from .goal import Goal

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


@cog_i18n(_)
class Hockey(
    HockeyCommands,
    HockeySetCommands,
    GameDayChannels,
    GameDayThreads,
    HockeyDev,
    HockeyPickems,
    HockeyNotifications,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "4.4.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, CONFIG_ID, force_registration=True)
        self.config.register_global(
            teams=[],
            created_gdc=False,
            print=False,
            last_day=0,
            enable_slash=False,
            loop_error_channel=None,
            loop_error_guild=None,
            player_db=0,
            schema_version=0,
        )
        self.config.register_guild(
            standings_channel=None,
            standings_type=None,
            post_standings=False,
            standings_msg=None,
            create_channels=False,
            create_threads=False,
            category=None,
            gdc_team=None,
            gdt_team=None,
            gdt_channel=None,
            gdc=[],
            gdt=[],
            gdc_chans={},
            gdt_chans={},
            delete_gdc=True,
            update_gdt=True,
            rules="",
            team_rules="",
            game_state_notifications=False,
            goal_notifications=False,
            start_notifications=False,
            default_start_roles={},
            default_state_roles={},
            default_goal_roles={},
            gdc_state_updates=["Preview", "Live", "Final", "Goal"],
            gdt_state_updates=["Preview", "Live", "Final", "Goal"],
            ot_notifications=True,
            so_notifications=True,
            timezone=None,
            include_goal_image=False,
            gdt_countdown=True,
            gdc_countdown=True,
            gdt_role=None,
        )
        self.config.register_channel(
            team=[],
            game_states=["Preview", "Live", "Final", "Goal"],
            countdown=True,
            to_delete=False,
            update=True,
            publish_states=[],
            game_state_notifications=False,
            goal_notifications=False,
            start_notifications=False,
            game_start_roles={},
            game_state_roles={},
            game_goal_roles={},
            guild_id=None,
            parent=None,
            include_goal_image=False,
        )
        self.pickems_config = Config.get_conf(
            None, CONFIG_ID, cog_name="Hockey_Pickems", force_registration=True
        )
        self.pickems_config.register_guild(
            leaderboard={},
            last_week_leaderboard={},
            pickems={},
            pickems_channels={},
            pickems_channel=None,
            pickems_category=None,
            pickems_message="",
            pickems_timezone="US/Pacific",
            base_credits=0,
            top_credits=0,
            top_amount=0,
            show_count=True,
        )
        self.pickems_config.register_global(
            base_credits=0,
            top_credits=0,
            top_amount=0,
            allowed_guilds=[],
            only_allowed=False,
            unavailable_msg=None,
        )
        self.loop: Optional[asyncio.Task] = None
        self.TEST_LOOP = False
        # used to test a continuous loop of a single game data
        self.all_pickems: Dict[str, Dict[str, Pickems]] = {}
        self.pickems_loop.start()
        self.current_games = {}
        self.games_playing = False
        self.session = aiohttp.ClientSession()
        self._ready: asyncio.Event = asyncio.Event()
        # self._ready is used to prevent pickems from opening
        # data from the wrong file location
        self._repo = ""
        self._commit = ""
        self.api = NewAPI()
        self.saving_goals = {}
        self._edit_tasks = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def cog_unload(self):
        try:
            self.bot.remove_dev_env_value("hockey")
        except Exception:
            pass

        if self.loop is not None:
            self.loop.cancel()
        await self.session.close()
        await self.api.close()
        self.pickems_loop.cancel()
        await self.after_pickems_loop()

    async def _get_commit(self):
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "hockey":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        all_guilds = await self.config.all_guilds()
        for g_id, data in all_guilds.items():
            if str(user_id) in data["leaderboard"]:
                del data["leaderboard"][str(user_id)]
                await self.pickems_config.guild_from_id(int(g_id)).leaderboard.set(
                    data["leaderboard"]
                )

    async def add_cog_to_dev_env(self):
        await self.bot.wait_until_red_ready()
        if 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("hockey", lambda x: self)
            except Exception:
                pass
        await self._get_commit()

    def hockey_loop_error(self, future: asyncio.Future):
        try:
            if not future.done():
                message = "Hockey encountered an error: `{exception}`\n{stack}".format(
                    exception=future.exception(), stack=box(str(future.get_stack()))
                )
                log.exception(message)
                asyncio.create_task(self.hockey_send_error_task(message))
        except asyncio.CancelledError:
            # we ignore cancelled errors
            pass

    async def hockey_send_error_task(self, message: str):
        guild = None
        channel = None
        if guild_id := await self.config.loop_error_guild():
            guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        if channel_id := await self.config.loop_error_channel():
            channel = guild.get_channel(channel_id)
        if channel is None:
            return
        await channel.send(message)

    async def cog_load(self) -> None:
        asyncio.create_task(self.add_cog_to_dev_env())
        self.loop = asyncio.create_task(self.game_check_loop())
        self.loop.add_done_callback(self.hockey_loop_error)
        await self.migrate_settings()
        if version_info > VersionInfo.from_str("3.5.9"):
            self.hockey_commands.app_command.allowed_contexts = (
                discord.app_commands.installs.AppCommandContext(
                    guild=True, dm_channel=True, private_channel=True
                )
            )
            self.hockey_commands.app_command.allowed_installs = (
                discord.app_commands.installs.AppInstallationType(guild=True, user=True)
            )

    async def migrate_settings(self) -> None:
        schema_version = await self.config.schema_version()
        if schema_version == 0:
            await self._schema_0_to_1()
            schema_version += 1
            await self.config.schema_version.set(schema_version)
        if schema_version == 1:
            await self._schema_1_to_2()
            schema_version += 1
            await self.config.schema_version.set(schema_version)
        if schema_version == 2:
            await self._schema_2_to_3()
            schema_version += 1
            await self.config.schema_version.set(schema_version)
        self._ready.set()

    async def _schema_2_to_3(self) -> None:
        await self.config.teams.clear()

    async def _schema_1_to_2(self) -> None:
        log.info("Adding new leaderboard keys for pickems")
        DEFAULT_LEADERBOARD = {
            "season": 0,
            "weekly": 0,
            "total": 0,
            "playoffs": 0,
            "playoffs_weekly": 0,
            "playoffs_total": 0,
            "pre-season": 0,
            "pre-season_weekly": 0,
            "pre-season_total": 0,
        }
        all_guilds = await self.pickems_config.all_guilds()
        for guild_id in all_guilds.keys():
            async with self.pickems_config.guild_from_id(
                int(guild_id)
            ).leaderboard() as leaderboard:
                async for user_id, data in AsyncIter(leaderboard.items()):
                    for key, value in DEFAULT_LEADERBOARD.items():
                        if key not in data:
                            leaderboard[user_id][key] = value

    async def _schema_0_to_1(self):
        log.info("Migrating old pickems to new file")
        all_guilds = await self.config.all_guilds()
        async for guild_id, data in AsyncIter(all_guilds.items(), steps=100):
            if data.get("leaderboard"):
                await self.pickems_config.guild_from_id(int(guild_id)).leaderboard.set(
                    data["leaderboard"]
                )
                try:
                    await self.config.guild_from_id(int(guild_id)).leaderboard.clear()
                except Exception:
                    pass
                log.info("Migrating leaderboard for %s", guild_id)
            if data.get("pickems"):
                try:
                    await self.config.guild_from_id(int(guild_id)).pickems.clear()
                except Exception:
                    pass
                log.info("Migrating pickems for %s", guild_id)
            if data.get("pickems_channels"):
                if not isinstance(data["pickems_channels"], list):
                    # this is just because I don't care but should get it working
                    await self.pickems_config.guild_from_id(int(guild_id)).pickems_channels.set(
                        data["pickems_channels"]
                    )
                try:
                    await self.config.guild_from_id(int(guild_id)).pickems_channels.clear()
                except Exception:
                    pass
                log.info("Migrating pickems channels for %s", guild_id)
            if data.get("pickems_category"):
                await self.pickems_config.guild_from_id(int(guild_id)).pickems_category.set(
                    data["pickems_category"]
                )
                try:
                    await self.config.guild_from_id(int(guild_id)).pickems_category.clear()
                except Exception:
                    pass
                log.info("Migrating pickems categories for %s", guild_id)

    ##############################################################################
    # Here is all the logic for gathering game data and updating information     #
    # This is essentially the "core" of the Hockey cog and dictates all the      #
    # main timing logic which is in turn dictated by nhl.com                     #
    ##############################################################################

    async def game_check_loop(self) -> None:
        """
        This loop grabs the current games for the day
        then passes off to other functions as necessary
        """
        await self.bot.wait_until_red_ready()
        await self._ready.wait()
        while True:
            try:
                schedule = await self.api.get_schedule()
                if schedule.days == []:
                    await asyncio.sleep(30)
                    continue
            except aiohttp.client_exceptions.ClientConnectorError:
                # this will most likely happen if there's a temporary failure in name resolution
                # this ends up calling the check_new_day earlier than expected causing
                # game day channels and pickems to fail to update prpoperly
                # continue after waiting 30 seconds should prevent that.
                schedule = Schedule([])
                await asyncio.sleep(30)
                continue
            except Exception:
                log.exception("Error grabbing the schedule for today.")
                data = {"dates": []}
                await asyncio.sleep(60)
                continue
            if schedule.days != []:
                for game in schedule.days[0]:
                    if game.game_state.value >= GameState.final.value:
                        continue
                    if game.schedule_state != "OK":
                        continue
                    if (game.game_start - datetime.now(timezone.utc)) > timedelta(days=1):
                        continue
                    self.current_games[game.id] = {
                        "count": 0,
                        "game": None,
                        "disabled_buttons": False,
                    }
            else:
                # Only try to create game day channels if there's no games for the day
                # Otherwise make the game day channels once we see
                # the first preview message to delete old ones
                await self.check_new_day()
            if self.TEST_LOOP:
                self.current_games = {
                    2020020474: {
                        "count": 0,
                        "game": None,
                        "disabled_buttons": False,
                    }
                }
            while self.current_games != {}:
                self.games_playing = True
                to_delete = []
                for game_id, data in self.current_games.items():
                    if data["game"] is not None:
                        await self.fix_pickem_game_start(data["game"])
                    if data["game"] is not None and data["game"].game_start - timedelta(
                        hours=1
                    ) >= datetime.now(timezone.utc):
                        log.trace(
                            "Skipping %s @ %s checks until closer to game start.",
                            data["game"].away_team,
                            data["game"].home_team,
                        )
                        continue
                    data = await self.api.get_game_from_id(game_id)
                    if data is None:
                        continue
                    try:
                        game = await self.api.get_game_from_id(game_id)
                        self.current_games[game_id]["game"] = game
                    except Exception:
                        log.exception("Error creating game object from json.")
                        continue
                    try:
                        await self.check_new_day()
                        posted_final = await game.check_game_state(
                            self.bot, self.current_games[game_id]["count"]
                        )
                    except Exception:
                        log.exception("Error checking game state: ")
                        posted_final = False
                    if (
                        game.game_state.is_live()
                        and not self.current_games[game_id]["disabled_buttons"]
                    ):
                        log.verbose("Disabling buttons for %r", game)
                        await self.disable_pickems_buttons(game)
                        self.current_games[game_id]["disabled_buttons"] = True

                    log.trace(
                        "%s @ %s %s %s - %s",
                        game.away_team,
                        game.home_team,
                        game.game_state,
                        game.away_score,
                        game.home_score,
                    )

                    if game.game_state.value > GameState.over.value:
                        self.current_games[game_id]["count"] += 1
                        if posted_final or game.game_state is GameState.official_final:
                            try:
                                await self.set_guild_pickem_winner(game, edit_message=True)
                            except Exception:
                                log.exception("Pickems Set Winner error: ")
                            self.current_games[game_id]["count"] = 21
                    await asyncio.sleep(1)

                for link in self.current_games:
                    if self.current_games[link]["count"] == 21:
                        to_delete.append(link)
                try:
                    for link in to_delete:
                        del self.current_games[link]
                        del self.saving_goals[link]
                except KeyError:
                    pass
                if not self.api.testing:
                    await asyncio.sleep(60)
                else:
                    await asyncio.sleep(10)
            log.debug("Games Done Playing")

            if self.games_playing:
                try:
                    await self.tally_leaderboard()
                    # Only tally the leaderboard once per day
                    # The tally function will iterate
                    # over all servers and pull all pickems games
                    # This is stored temporarily until we're done
                    # iterating over all guilds and then forget
                    # about the results
                except Exception:
                    log.exception("Error tallying leaderboard:")
                    pass
                self.games_playing = False

            # Final cleanup of config incase something went wrong
            # Should be mostly unnecessary at this point
            await self.config.teams.clear()

            await asyncio.sleep(300)

    async def get_game_data(self, link: str) -> Optional[Dict[str, Any]]:
        if not self.TEST_LOOP:
            try:
                async with self.session.get(BASE_URL + link) as resp:
                    data = await resp.json()
            except Exception:
                log.exception("Error grabbing game data: ")
                return None
        else:
            self.games_playing = False
            with open(str(__file__)[:-9] + "testgame.json", "r") as infile:
                data = json.loads(infile.read())
        return data

    async def check_new_day(self) -> None:
        now = utc_to_local(datetime.now(timezone.utc))
        if now.day != await self.config.last_day():
            if datetime.now().weekday() == 6:
                try:
                    await self.reset_weekly()
                except Exception:
                    log.error("Error reseting the weekly leaderboard: ", exc_info=True)
            try:
                guilds_to_make_new_pickems = []
                for guild_id in await self.pickems_config.all_guilds():
                    guild = self.bot.get_guild(guild_id)
                    if guild is None:
                        continue
                    if await self.pickems_config.guild(guild).pickems_channel():
                        guilds_to_make_new_pickems.append(guild)
                asyncio.create_task(self.create_next_pickems_day(guilds_to_make_new_pickems))

            except Exception:
                log.error("Error creating new weekly pickems pages", exc_info=True)
            try:
                asyncio.create_task(Standings.post_automatic_standings(self.bot))
            except Exception:
                log.error("Error updating standings", exc_info=True)

            log.debug("Checking GDC")
            loop = asyncio.get_running_loop()

            loop.create_task(self.check_new_gdc())
            loop.create_task(self.check_new_gdt())
            # await self.config.created_gdc.set(True)
            await self.config.last_day.set(now.day)

    async def change_custom_emojis(self, attachments: List[discord.Attachment]) -> None:
        """
        This overwrites the emojis in constants.py
         with values in a properly formatted .yaml file
        """
        try:
            async with self.session.get(attachments[0].url) as infile:
                data = yaml.safe_load(await infile.read())
        except yaml.error.YAMLError as exc:
            raise InvalidFileError("Error Parsing the YAML") from exc
        # new_dict = {}
        for team in TEAMS:
            TEAMS[team]["emoji"] = data[team][0] if data[team][0] is not None else data["Other"][0]
        team_data = json.dumps(TEAMS, indent=4, sort_keys=True, separators=(",", " : "))
        constants_string = (
            f'BASE_URL = "{BASE_URL}"\n'
            f'HEADSHOT_URL = "{HEADSHOT_URL}"\n'
            f'CONTENT_URL = "{CONTENT_URL}"\n'
            f"CONFIG_ID = {CONFIG_ID}\n"
            f"TEAMS = {team_data}\n"
        )
        path = Path(__file__).parent / "new-constants.py"
        constants_string = constants_string.replace("true", "True").replace("false", "False")
        with path.open("w") as outfile:
            outfile.write(constants_string)

    def get_current_game_data(self, game_id: int) -> Optional[Game]:
        return self.current_games.get(game_id, {}).get("game")

    def get_current_goal(self, game_id: int, goal_id: int) -> Optional[Goal]:
        game = self.get_current_game_data(game_id)
        if game:
            return game.get_goal_from_id(goal_id)
        return None

    def get_goal_save_event(self, game_id: int, goal_id: str, set_event: bool) -> asyncio.Event:
        """
        Get an asyncio Event for saving goals.
        If set_event is True and the event does not exist it will return in a set state.
        This is for when the cog is reloaded and it's seeing the event for the first time we can
        reasonably assume that the event is done saving.
        """
        if game_id not in self.saving_goals:
            self.saving_goals[game_id] = {}
        if goal_id not in self.saving_goals[game_id]:
            self.saving_goals[game_id][goal_id] = asyncio.Event()
            if set_event:
                self.saving_goals[game_id][goal_id].set()
        return self.saving_goals[game_id][goal_id]

    async def wait_for_file(self, ctx: commands.Context) -> None:
        """
        Waits for the author to upload a file
        """
        msg = None
        while msg is None:

            def check(m):
                return m.author == ctx.message.author and m.attachments != []

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("Emoji changing cancelled"))
                break
            if msg.content.lower().strip() == "exit":
                await ctx.send(_("Emoji changing cancelled"))
            break
        return msg
