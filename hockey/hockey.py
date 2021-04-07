import asyncio
import discord
import json
import logging
from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Dict, List

import aiohttp
import yaml
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter

from .constants import BASE_URL, CONFIG_ID, CONTENT_URL, HEADSHOT_URL, TEAMS
from .dev import HockeyDev
from .errors import InvalidFileError
from .game import Game
from .gamedaychannels import GameDayChannels
from .hockey_commands import HockeyCommands
from .hockeypickems import HockeyPickems
from .hockeyset import HockeySetCommands
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
    HockeyDev,
    HockeyPickems,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "3.0.3"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        super().__init__(self)
        self.bot = bot
        default_global = {"teams": [], "created_gdc": False, "print": False}
        for team in TEAMS:
            team_entry = TeamEntry("Null", team, 0, [], {}, [], "")
            default_global["teams"].append(team_entry.to_json())
        default_global["teams"].append(team_entry.to_json())
        default_global["player_db"] = 0
        default_guild = {
            "standings_channel": None,
            "standings_type": None,
            "post_standings": False,
            "standings_msg": None,
            "create_channels": False,
            "category": None,
            "gdc_team": None,
            "gdc": [],
            "delete_gdc": True,
            "rules": "",
            "team_rules": "",
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
            "gdc_state_updates": ["Preview", "Live", "Final", "Goal"],
            "ot_notifications": True,
            "so_notifications": True,
            "timezone": None,
        }
        default_channel = {
            "team": [],
            "game_states": ["Preview", "Live", "Final", "Goal"],
            "to_delete": False,
            "publish_states": [],
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
            "guild_id": None,
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
            pickems={},
            pickems_channels=[],
            pickems_category=None,
            pickems_message="",
            pickems_timezone="US/Pacific",
            base_credits=0,
            top_credits=0,
            top_amount=0,
        )
        self.pickems_config.register_global(base_credits=0, top_credits=0, top_amount=0)
        self.loop: Optional[asyncio.Task] = None
        self.TEST_LOOP = False
        # used to test a continuous loop of a single game data
        self.all_pickems = {}
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

    def cog_unload(self):
        try:
            self.bot.remove_dev_env_value("hockey")
        except Exception:
            pass

        if self.loop is not None:
            self.loop.cancel()
        self.pickems_loop.cancel()
        self.bot.loop.create_task(self.session.close())

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
                await self.pickems_config.guild_from_id(g_id).leaderboard.set(data["leaderboard"])

    async def initialize(self) -> None:
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
        self._ready.set()

    async def _schema_0_to_1(self):
        log.info("Migrating old pickems to new file")
        all_guilds = await self.config.all_guilds()
        async for guild_id, data in AsyncIter(all_guilds.items(), steps=100):
            if data.get("leaderboard"):
                await self.pickems_config.guild_from_id(guild_id).leaderboard.set(
                    data["leaderboard"]
                )
                try:
                    await self.config.guild_from_id(guild_id).leaderboard.clear()
                except Exception:
                    pass
                log.info(f"Migrating leaderboard for {guild_id}")
            if data.get("pickems"):
                try:
                    await self.config.guild_from_id(guild_id).pickems.clear()
                except Exception:
                    pass
                log.info(f"Migrating pickems for {guild_id}")
            if data.get("pickems_channels"):
                await self.pickems_config.guild_from_id(guild_id).pickems_channels.set(
                    data["pickems_channels"]
                )
                try:
                    await self.config.guild_from_id(guild_id).pickems_channels.clear()
                except Exception:
                    pass
                log.info(f"Migrating pickems channels for {guild_id}")
            if data.get("pickems_category"):
                await self.pickems_config.guild_from_id(guild_id).pickems_category.set(
                    data["pickems_category"]
                )
                try:
                    await self.config.guild_from_id(guild_id).pickems_category.clear()
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
                    data = await resp.json()
            except Exception:
                log.exception("Error grabbing the schedule for today.")
                data = {"dates": []}
            if data["dates"] != []:
                self.current_games = {
                    game["link"]: {"count": 0, "game": None}
                    for game in data["dates"][0]["games"]
                    if game["status"]["abstractGameState"] != "Final"
                    and game["status"]["detailedState"] != "Postponed"
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
                    }
                }
            while self.current_games != {}:
                self.games_playing = True
                to_delete = []
                for link in self.current_games:
                    if not self.TEST_LOOP:
                        try:
                            async with self.session.get(BASE_URL + link) as resp:
                                data = await resp.json()
                        except Exception:
                            log.exception("Error grabbing game data: ")
                            continue
                    else:
                        self.games_playing = False
                        with open(str(__file__)[:-9] + "testgame.json", "r") as infile:
                            data = json.loads(infile.read())
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

                    log.debug(
                        (
                            f"{game.away_team} @ {game.home_team} "
                            f"{game.game_state} {game.away_score} - {game.home_score}"
                        )
                    )

                    if game.game_state in ["Final", "Postponed"]:
                        try:
                            await self.set_guild_pickem_winner(game)
                        except Exception:
                            log.exception("Pickems Set Winner error: ")
                        self.current_games[link]["count"] += 1
                        if posted_final:
                            self.current_games[link]["count"] = 10

                for link in self.current_games:
                    if self.current_games[link]["count"] == 10:
                        to_delete.append(link)
                for link in to_delete:
                    del self.current_games[link]
                if not self.TEST_LOOP:
                    await asyncio.sleep(60)
                else:
                    await asyncio.sleep(10)
            log.debug("Games Done Playing")

            if self.games_playing:
                await self.config.created_gdc.set(False)
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
            async with self.config.teams() as all_teams:
                for team in await self.config.teams():
                    all_teams.remove(team)
                    team["goal_id"] = {}
                    team["game_state"] = "Null"
                    team["game_start"] = ""
                    team["period"] = 0
                    all_teams.append(team)

            await asyncio.sleep(300)

    async def check_new_day(self) -> None:
        if not await self.config.created_gdc():
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
                        if await self.pickems_config.guild(guild).pickems_category():
                            guilds_to_make_new_pickems.append(guild)
                    await self.create_weekly_pickems_pages(guilds_to_make_new_pickems)

                except Exception:
                    log.error("Error creating new weekly pickems pages", exc_info=True)
            try:
                await Standings.post_automatic_standings(self.bot)
            except Exception:
                log.error("Error updating standings", exc_info=True)

            log.debug("Checking GDC")

            await self.check_new_gdc()
            await self.config.created_gdc.set(True)

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
            f"TEAMS = {team_data}"
        )
        path = Path(__file__).parent / "constants.py"
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
