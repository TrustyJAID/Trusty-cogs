import asyncio
import json
import logging
from copy import copy
from datetime import datetime
from typing import Literal
from pathlib import Path

import aiohttp
import discord
import yaml
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n

from .constants import BASE_URL, CONFIG_ID, CONTENT_URL, HEADSHOT_URL, TEAMS
from .dev import HockeyDev
from .errors import InvalidFileError, NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game
from .gamedaychannels import GameDayChannels
from .hockey_commands import HockeyCommands
from .hockeyset import HockeySetCommands

from .pickems import Pickems
from .standings import Standings
from .teamentry import TeamEntry

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


@cog_i18n(_)
class Hockey(HockeyCommands, HockeySetCommands, GameDayChannels, HockeyDev, commands.Cog):
    """
    Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "2.15.2"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
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
            "pickems": {},
            "leaderboard": {},
            "pickems_category": None,
            "pickems_channels": [],
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
            "gdc_state_updates": ["Preview", "Live", "Final", "Goal"],
            "ot_notifications": True,
            "so_notifications": True,
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
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)
        self.loop = None
        self.TEST_LOOP = False
        # used to test a continuous loop of a single game data
        self.all_pickems = {}
        self.pickems_loop.start()
        self.pickems_save_lock = asyncio.Lock()
        self.current_games = {}
        self.games_playing = False
        self.session = aiohttp.ClientSession()

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
        self.bot.loop.create_task(self.session.close())
        if self.loop is not None:
            self.loop.cancel()
        self.pickems_loop.cancel()

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
                await self.config.guild_from_id(g_id).leaderboard.set(data["leaderboard"])

    async def initialize(self):
        if 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("hockey", lambda x: self)
            except Exception:
                pass
        self.loop = asyncio.create_task(self.game_check_loop())

    ##############################################################################
    # Here is all the logic for gathering game data and updating information

    async def game_check_loop(self):
        """
        This loop grabs the current games for the day
        then passes off to other functions as necessary
        """
        await self.bot.wait_until_red_ready()
        while True:
            try:
                async with self.session.get(f"{BASE_URL}/api/v1/schedule") as resp:
                    data = await resp.json()
            except Exception:
                log.debug("Error grabbing the schedule for today.", exc_info=True)
                data = {"dates": []}
            if data["dates"] != []:
                self.current_games = {
                    game["link"]: {"count": 0, "game": None}
                    for game in data["dates"][0]["games"]
                    if game["status"]["abstractGameState"] != "Final"
                    and game["status"]["detailedState"] != "Postponed"
                }
            else:
                games = []
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
                            log.error("Error grabbing game data: ", exc_info=True)
                            continue
                    else:
                        self.games_playing = False
                        with open(str(__file__)[:-9] + "testgame.json", "r") as infile:
                            data = json.loads(infile.read())
                    try:
                        game = await Game.from_json(data)
                        self.current_games[link]["game"] = game
                    except Exception:
                        log.error("Error creating game object from json.", exc_info=True)
                        continue
                    try:
                        await self.check_new_day()
                        posted_final = await game.check_game_state(
                            self.bot, self.current_games[link]["count"]
                        )
                    except Exception:
                        log.error("Error checking game state: ", exc_info=True)

                    log.debug(
                        (
                            f"{game.away_team} @ {game.home_team} "
                            f"{game.game_state} {game.away_score} - {game.home_score}"
                        )
                    )

                    if game.game_state in ["Final", "Postponed"]:
                        try:
                            await Pickems.set_guild_pickem_winner(self.bot, game)
                        except Exception:
                            log.error("Pickems Set Winner error: ", exc_info=True)
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
            try:
                await Pickems.tally_leaderboard(self.bot)
            except Exception:
                log.error("Error tallying leaderboard:", exc_info=True)
                pass
            if self.games_playing:
                await self.config.created_gdc.set(False)

            # Final cleanup of config incase something went wrong
            # Should be mostly unnecessary at this point
            all_teams = await self.config.teams()
            for team in await self.config.teams():
                all_teams.remove(team)
                team["goal_id"] = {}
                team["game_state"] = "Null"
                team["game_start"] = ""
                team["period"] = 0
                all_teams.append(team)

            await self.config.teams.set(all_teams)
            await asyncio.sleep(300)

    async def check_new_day(self):
        if not await self.config.created_gdc():
            if datetime.now().weekday() == 6:
                try:
                    await Pickems.reset_weekly(self.bot)
                except Exception:
                    log.error("Error reseting the weekly leaderboard: ", exc_info=True)
                try:
                    guilds_to_make_new_pickems = []
                    for guild_id in await self.config.all_guilds():
                        guild = self.bot.get_guild(guild_id)
                        if guild is None:
                            continue
                        if await self.config.guild(guild).pickems_category():
                            guilds_to_make_new_pickems.append(guild)
                    async with self.pickems_save_lock:
                        await Pickems.create_weekly_pickems_pages(
                            self.bot, guilds_to_make_new_pickems, Game
                        )

                except Exception:
                    log.error("Error creating new weekly pickems pages", exc_info=True)
            try:
                await Standings.post_automatic_standings(self.bot)
            except Exception:
                log.error("Error updating standings", exc_info=True)

            log.debug("Checking GDC")

            await self.check_new_gdc()
            await self.config.created_gdc.set(True)

    @tasks.loop(seconds=120)
    async def pickems_loop(self):
        await self.save_pickems_data()
        log.debug("Saved pickems data.")

    async def save_pickems_data(self):
        try:
            async with self.pickems_save_lock:
                log.debug("Saving pickems data")
                all_pickems = copy(self.all_pickems)
                for guild_id, pickems in all_pickems.items():
                    data = {}
                    for name, pickem in pickems.items():
                        pickem = await pickem.check_winner()
                        data[name] = pickem.to_json()
                    await self.config.guild_from_id(guild_id).pickems.set(data)
        except Exception:
            log.exception("Error saving pickems Data")
            # catch all errors cause we don't want this loop to fail for something dumb

    @pickems_loop.after_loop
    async def after_pickems_loop(self):
        if self.pickems_loop.is_being_cancelled():
            await self.save_pickems_data()

    @pickems_loop.before_loop
    async def before_pickems_loop(self):
        await self.bot.wait_until_ready()
        data = await self.config.all_guilds()
        for guild_id, data in data.items():
            pickems_list = data.get("pickems", {})
            if pickems_list is None:
                log.info(f"Resetting pickems in {guild_id} for incompatible type")
                await self.config.guild_from_id(guild_id).pickems.clear()
                continue
            if type(pickems_list) is list:
                log.info(f"Resetting pickems in {guild_id} for incompatible type")
                await self.config.guild_from_id(guild_id).pickems.clear()
                continue
            # pickems = [Pickems.from_json(p) for p in pickems_list]
            pickems = {name: Pickems.from_json(p) for name, p in pickems_list.items()}
            self.all_pickems[str(guild_id)] = pickems

    @commands.Cog.listener()
    async def on_hockey_preview_message(self, channel, message, game):
        """
        Handles adding preview messages to the pickems object.
        """
        # a little hack to avoid circular imports
        await Pickems.create_pickem_object(self.bot, channel.guild, message, channel, game)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        if str(guild.id) not in self.all_pickems:
            return
        user = guild.get_member(payload.user_id)
        # log.debug(payload.user_id)
        if not user or user.bot:
            return
        try:
            msg = await channel.fetch_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.errors.Forbidden):
            return

        is_pickems_vote = False
        for name, pickem in self.all_pickems[str(guild.id)].items():
            if msg.id in pickem.message:
                is_pickems_vote = True
                reply_message = ""
                try:
                    # log.debug(payload.emoji)
                    pickem.add_vote(user.id, payload.emoji)
                except UserHasVotedError as team:
                    if msg.channel.permissions_for(msg.guild.me).manage_messages:
                        emoji = (
                            pickem.home_emoji
                            if str(payload.emoji.id) in pickem.away_emoji
                            else pickem.away_emoji
                        )
                        await msg.remove_reaction(emoji, user)
                    reply_message = _("You have already voted! Changing vote to: ") + str(team)
                except VotingHasEndedError as error_msg:
                    if msg.channel.permissions_for(msg.guild.me).manage_messages:
                        await msg.remove_reaction(payload.emoji, user)
                    reply_message = _("Voting has ended!") + str(error_msg)
                except NotAValidTeamError:
                    if msg.channel.permissions_for(msg.guild.me).manage_messages:
                        await msg.remove_reaction(payload.emoji, user)
                    reply_message = _("Don't clutter the voting message with emojis!")
                if reply_message != "":
                    try:
                        await user.send(reply_message)
                    except Exception:
                        pass

    async def change_custom_emojis(self, attachments):
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

    async def wait_for_file(self, ctx):
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
