import asyncio
import json
import logging
from abc import ABC
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import aiohttp
import discord
import yaml
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter

from .constants import BASE_URL, CONFIG_ID, CONTENT_URL, HEADSHOT_URL, TEAMS
from .dev import HockeyDev
from .errors import InvalidFileError
from .game import Game
from .gamedaychannels import GameDayChannels
from .gamedaythreads import GameDayThreads
from .helper import utc_to_local
from .hockey_commands import HockeyCommands
from .hockeypickems import HockeyPickems
from .hockeyset import HockeySetCommands
from .pickems import Pickems
from .standings import Standings
from .teamentry import TeamEntry

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


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
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "3.3.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        default_global = {
            "teams": [],
            "created_gdc": False,
            "print": False,
            "last_day": 0,
            "enable_slash": False,
        }
        default_global["player_db"] = 0
        default_guild = {
            "standings_channel": None,
            "standings_type": None,
            "post_standings": False,
            "standings_msg": None,
            "create_channels": False,
            "create_threads": False,
            "category": None,
            "gdc_team": None,
            "gdt_team": None,
            "gdt_channel": None,
            "gdc": [],
            "gdt": [],
            "delete_gdc": True,
            "update_gdt": True,
            "rules": "",
            "team_rules": "",
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
            "gdc_state_updates": ["Preview", "Live", "Final", "Goal"],
            "gdt_state_updates": ["Preview", "Live", "Final", "Goal"],
            "ot_notifications": True,
            "so_notifications": True,
            "timezone": None,
            "include_goal_image": False,
        }
        default_channel = {
            "team": [],
            "game_states": ["Preview", "Live", "Final", "Goal"],
            "to_delete": False,
            "update": True,
            "publish_states": [],
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
            "guild_id": None,
            "parent": None,
            "include_goal_image": False,
        }

        self.config = Config.get_conf(self, CONFIG_ID, force_registration=True)
        self.config.register_global(**default_global, schema_version=0)
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)
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
        )
        self.pickems_config.register_global(
            base_credits=0,
            top_credits=0,
            top_amount=0,
            allowed_guilds=[],
            only_allowed=False,
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

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self):
        try:
            self.bot.remove_dev_env_value("hockey")
        except Exception:
            pass

        if self.loop is not None:
            self.loop.cancel()
        await self.session.close()
        self.pickems_loop.cancel()
        count = 0
        while self.pickems_loop.is_being_cancelled():
            if count > 10:
                log.error("Pickems took more than 10 seconds to finish closing its loop.")
                break
            await asyncio.sleep(1)
            count += 1

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

    async def cog_load(self) -> None:
        if 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("hockey", lambda x: self)
            except Exception:
                pass
        self.loop = asyncio.create_task(self.game_check_loop())
        await self.migrate_settings()

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
                log.info(f"Migrating leaderboard for {guild_id}")
            if data.get("pickems"):
                try:
                    await self.config.guild_from_id(int(guild_id)).pickems.clear()
                except Exception:
                    pass
                log.info(f"Migrating pickems for {guild_id}")
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
                log.info(f"Migrating pickems channels for {guild_id}")
            if data.get("pickems_category"):
                await self.pickems_config.guild_from_id(int(guild_id)).pickems_category.set(
                    data["pickems_category"]
                )
                try:
                    await self.config.guild_from_id(int(guild_id)).pickems_category.clear()
                except Exception:
                    pass
                log.info(f"Migrating pickems categories for {guild_id}")

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
                async with self.session.get(f"{BASE_URL}/api/v1/schedule") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                    else:
                        log.info("Error checking schedule. %s", resp.status)
                        await asyncio.sleep(30)
                        continue
            except aiohttp.client_exceptions.ClientConnectorError:
                # this will most likely happen if there's a temporary failure in name resolution
                # this ends up calling the check_new_day earlier than expected causing
                # game day channels and pickems to fail to update prpoperly
                # continue after waiting 30 seconds should prevent that.
                data = {"dates": []}
                await asyncio.sleep(30)
                continue
            except Exception:
                log.exception("Error grabbing the schedule for today.")
                data = {"dates": []}
                await asyncio.sleep(60)
                continue
            if data["dates"] != []:
                for game in data["dates"][0]["games"]:
                    if game["status"]["abstractGameState"] == "Final":
                        continue
                    if game["status"]["detailedState"] == "Postponed":
                        continue
                    self.current_games[game["link"]] = {
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
                    "https://statsapi.web.nhl.com/api/v1/game/2020020474/feed/live": {
                        "count": 0,
                        "game": None,
                        "disabled_buttons": False,
                    }
                }
            while self.current_games != {}:
                self.games_playing = True
                to_delete = []
                for link, data in self.current_games.items():
                    if data["game"] is not None:
                        await self.fix_pickem_game_start(data["game"])
                    if data["game"] is not None and data["game"].game_start - timedelta(
                        hours=1
                    ) >= datetime.now(timezone.utc):
                        log.debug(
                            "Skipping %s @ %s checks until closer to game start.",
                            data["game"].away_team,
                            data["game"].home_team,
                        )
                        continue
                    data = await self.get_game_data(link)
                    if data is None:
                        continue
                    try:
                        game = await Game.from_json(data)
                        self.current_games[link]["game"] = game
                    except Exception:
                        log.exception("Error creating game object from json.")
                        continue
                    try:
                        await self.check_new_day()
                        posted_final = await game.check_game_state(
                            self.bot, self.current_games[link]["count"]
                        )
                    except Exception:
                        log.exception("Error checking game state: ")
                        posted_final = False
                    if (
                        game.game_state in ["Live"]
                        and not self.current_games[link]["disabled_buttons"]
                    ):
                        log.debug("Disabling buttons for %r", game)
                        await self.disable_pickems_buttons(game)
                        self.current_games[link]["disabled_buttons"] = True

                    log.debug(
                        "%s @ %s %s %s - %s",
                        game.away_team,
                        game.home_team,
                        game.game_state,
                        game.away_score,
                        game.home_score,
                    )

                    if game.game_state in ["Final", "Postponed"]:
                        self.current_games[link]["count"] += 1
                        if posted_final:
                            try:
                                await self.set_guild_pickem_winner(game, edit_message=True)
                            except Exception:
                                log.exception("Pickems Set Winner error: ")
                            self.current_games[link]["count"] = 21
                    await asyncio.sleep(1)

                for link in self.current_games:
                    if self.current_games[link]["count"] == 21:
                        to_delete.append(link)
                for link in to_delete:
                    del self.current_games[link]
                if not self.TEST_LOOP:
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
