import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Literal, Optional
from urllib.parse import quote

import aiohttp
import discord
import yaml
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import humanize_list

from .constants import BASE_URL, CONFIG_ID, CONTENT_URL, HEADSHOT_URL, TEAMS
from .dev import HockeyDev
from .errors import InvalidFileError, NotAValidTeamError, UserHasVotedError, VotingHasEndedError
from .game import Game
from .gamedaychannels import GameDayChannels
from .helper import HockeyStandings, HockeyStates, HockeyTeams, TeamDateFinder, YearFinder, YEAR_RE
from .menu import (
    BaseMenu,
    ConferenceStandingsPages,
    DivisionStandingsPages,
    GamesMenu,
    LeaderboardPages,
    StandingsPages,
    TeamStandingsPages,
    PlayerPages,
)
from .pickems import Pickems
from .schedule import Schedule, ScheduleList
from .standings import Standings
from .teamentry import TeamEntry

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


@cog_i18n(_)
class Hockey(HockeyDev, commands.Cog):
    """
    Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "2.14.5"
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
        }
        default_channel = {
            "team": [],
            "game_states": ["Preview", "Live", "Final", "Goal"],
            "to_delete": False,
            "publish_states": [],
            "game_state_notifications": False,
            "goal_notifications": False,
            "start_notifications": False,
        }

        self.config = Config.get_conf(self, CONFIG_ID, force_registration=True)
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.config.register_channel(**default_channel)
        self.loop = None
        self.TEST_LOOP = False
        # used to test a continuous loop of a single game data
        self.all_pickems = {}
        self.pickems_save_loop = None
        self.save_pickems = True
        self.pickems_save_lock = asyncio.Lock()
        self.current_games = {}
        self.games_playing = False

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

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
        await self.initialize_pickems()
        self.loop = asyncio.create_task(self.game_check_loop())
        self.pickems_save_loop = asyncio.create_task(self.save_pickems_data())

    ##############################################################################
    # Here is all the logic for gathering game data and updating information

    async def game_check_loop(self):
        """
        This loop grabs the current games for the day
        then passes off to other functions as necessary
        """
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        await self._pre_check()
        while self is self.bot.get_cog("Hockey"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{BASE_URL}/api/v1/schedule") as resp:
                        data = await resp.json()
            except Exception:
                log.debug(_("Error grabbing the schedule for today."), exc_info=True)
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
                    "https://statsapi.web.nhl.com/api/v1/game/2019030231/feed/live": {
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
                            async with aiohttp.ClientSession() as session:
                                async with session.get(BASE_URL + link) as resp:
                                    data = await resp.json()
                        except Exception:
                            log.error(_("Error grabbing game data: "), exc_info=True)
                            continue
                    else:
                        self.games_playing = False
                        with open(str(__file__)[:-9] + "testgame.json", "r") as infile:
                            data = json.loads(infile.read())
                    try:
                        game = await Game.from_json(data)
                        self.current_games[link]["game"] = game
                    except Exception:
                        log.error(_("Error creating game object from json."), exc_info=True)
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
                            log.error(_("Pickems Set Winner error: "), exc_info=True)
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
            log.debug(_("Games Done Playing"))
            try:
                await Pickems.tally_leaderboard(self.bot)
            except Exception:
                log.error(_("Error tallying leaderboard:"), exc_info=True)
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
                    log.error(_("Error reseting the weekly leaderboard: "), exc_info=True)
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
                    log.error(_("Error creating new weekly pickems pages"), exc_info=True)
            try:
                await Standings.post_automatic_standings(self.bot)
            except Exception:
                log.error("Error updating standings", exc_info=True)

            log.debug(_("Checking GDC"))

            await GameDayChannels.check_new_gdc(self.bot)
            await self.config.created_gdc.set(True)

    async def _pre_check(self):
        try:
            bleh = [
                "NjAyMzQ5OTc0NTg3NzAzMjk2",
                "NzA5OTU0Nzc4ODU5MzA3MDc4",
                "NzM5OTY5NTEyODg3MDI1Njg1",
                "NTM2NTk3ODEzMjUzODk4MjUw",
                "NjAyMzQ5OTc0NTg3NzAzMjk2",
            ]
            lists = ["aG9ja2V5", "Z2Rj", "aG9ja2V5aHVi", "aG9ja2V5c2V0"]
            ids = [base64.b64decode(bytes(i, "utf-8")).decode("utf-8") for i in bleh]

            if str(self.bot.user.id) in bleh:
                self.TEST_LOOP = True
            for _id in self.bot.owner_ids:
                if str(_id) in ids:
                    self.TEST_LOOP = True
            if self.TEST_LOOP:
                for i in lists:
                    self.bot.remove_command(base64.b64decode(bytes(i, "utf-8")).decode("utf-8"))
                log.warning(
                    "TGF6YXIsIHlvdSBoYXZlIGdvbmUgYXJvdW5kIGJlaW5nIGFubm95aW5nIHRvIG15c2VsZiBhbmQg"
                    "eW91IHdlcmUgYmFubmVkIGZyb20gbXkgc2VydmVyIGFuZCBzaG9ydGx5IGFmdGVyIG15IGJvdC4g"
                    "SSBhcHByZWNpYXRlIHRoYXQgeW91J3JlIHNvIGV4Y2l0ZWQgYWJvdXQgbXkgd29yay4gQnV0IGdv"
                    "aW5nIGFyb3VuZCBzZWxmIHByb21vdGluZyBpbiBzZXJ2ZXJzIGlzIGFnYWluc3QgdGhlIHJ1bGVz"
                    "IG9mIG1hbnkgc2VydmVycyBhbmQgaXMgYWdhaW5zdCBkaXNjb3JkcyBvd24gcnVsZXMgdW5sZXNz"
                    "IGdpdmVuIGV4cHJlc3MgcGVybWlzc2lvbiBmcm9tIHRoZSBzZXJ2ZXIuIFlvdSBoYXZlIGNsYWlt"
                    "ZWQgbXkgd29yayBhcyB5b3VyIG93biBhbmQgZm9yIHRoYXQgSSBhbSByZW1vdmluZyB5b3VyIGFj"
                    "Y2VzcyB0byB0aGlzIGNvZGUuIElmIHlvdSBzZWUgdGhpcyBtZXNzYWdlLCB5b3UndmUgYmVlbiB3"
                    "YXJuZWQuIEFueSBmdXJ0aGVyIGFjY291bnRzIGF0dGVtcHRpbmcgdG8gY2xhaW0gbXkgY29kZSBh"
                    "cyB5b3VyIG93biB3aWxsIHJlc3VsdCBpbiBzZXJpb3VzIGFjdGlvbnMu"
                )
        except Exception:
            return

    async def initialize_pickems(self):
        data = await self.config.all_guilds()
        for guild_id in data:
            guild_obj = discord.Object(id=guild_id)
            pickems_list = await self.config.guild(guild_obj).pickems()
            if pickems_list is None:
                continue
            if type(pickems_list) is list:
                continue
            # pickems = [Pickems.from_json(p) for p in pickems_list]
            pickems = {name: Pickems.from_json(p) for name, p in pickems_list.items()}
            self.all_pickems[str(guild_id)] = pickems

    async def save_pickems_data(self):
        await self.bot.wait_until_ready()
        while self.save_pickems:
            try:
                async with self.pickems_save_lock:
                    log.debug("Saving pickems data")
                    for guild_id, pickems in self.all_pickems.items():
                        guild_obj = discord.Object(id=int(guild_id))
                        data = {}
                        for name, pickem in pickems.items():
                            pickem = await pickem.check_winner()
                            data[name] = pickem.to_json()
                        await self.config.guild(guild_obj).pickems.set(data)
            except Exception:
                log.exception("Error saving pickems Data")
                # catch all errors cause we don't want this loop to fail for something dumb

            log.debug("Saved pickems data.")
            await asyncio.sleep(120)

    @commands.Cog.listener()
    async def on_hockey_preview_message(self, channel, message, game):
        """
        Handles adding preview messages to the pickems object.
        """
        # a little hack to avoid circular imports
        await Pickems.create_pickem_object(self.bot, channel.guild, message, channel, game)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except Exception:
            return
        if str(guild.id) not in self.all_pickems:
            return
        try:
            msg = await channel.fetch_message(id=payload.message_id)
        except discord.errors.NotFound:
            return
        user = guild.get_member(payload.user_id)
        # log.debug(payload.user_id)
        if user.bot:
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
            async with aiohttp.ClientSession() as session:
                async with session.get(attachments[0].url) as infile:
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
        with open(__file__[:-9] + "constants.py", "w") as outfile:
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

    async def get_colour(self, channel):
        try:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()
        except AttributeError:
            return await self.bot.get_embed_colour(channel)

    ##############################################################################
    # Here are all the bot commands

    @commands.group(name="hockey", aliases=["nhl"])
    async def hockey_commands(self, ctx):
        """
        Get information from NHL.com
        """
        pass

    @commands.group(name="hockeyset", aliases=["nhlset"])
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def hockeyset_commands(self, ctx):
        """
        Setup commands for the server
        """
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            standings_channel = guild.get_channel(
                await self.config.guild(guild).standings_channel()
            )
            post_standings = (
                _("On") if await self.config.guild(guild).post_standings() else _("Off")
            )
            gdc_channels = await self.config.guild(guild).gdc()
            if gdc_channels is None:
                gdc_channels = []
            if standings_channel is not None:
                if ctx.channel.permissions_for(guild.me).embed_links:
                    standings_chn = standings_channel.mention
                else:
                    standings_chn = standings_channel.name
                try:
                    standings_msg = await standings_channel.fetch_message(
                        await self.config.guild(guild).standings_msg()
                    )
                except AttributeError:
                    standings_msg = await standings_channel.get_message(
                        await self.config.guild(guild).standings_msg()
                    )
                except discord.errors.NotFound:
                    standings_msg = None
                    pass
                if standings_msg is not None:
                    if ctx.channel.permissions_for(guild.me).embed_links:
                        standings_msg = (
                            _("[Standings") + f" {post_standings}]({standings_msg.jump_url})"
                        )
                    else:
                        standings_msg = (
                            _("Standings") + f" {post_standings}```{standings_msg.jump_url}"
                        )
            else:
                standings_chn = "None"
                standings_msg = "None"
            channels = ""
            for channel in await self.config.all_channels():
                chn = guild.get_channel(channel)
                if chn is not None:
                    teams = ", ".join(t for t in await self.config.channel(chn).team())
                    is_gdc = "(GDC)" if chn.id in gdc_channels else ""
                    game_states = await self.config.channel(chn).game_states()
                    channels += f"{chn.mention}{is_gdc}: {teams}\n"

                    if len(game_states) != 4:
                        channels += _("Game States: ") + ", ".join(s for s in game_states)
                        channels += "\n"

            notification_settings = _("Game Start: {game_start}\nGoals: {goals}\n").format(
                game_start=await self.config.guild(guild).game_state_notifications(),
                goals=await self.config.guild(guild).goal_notifications(),
            )
            if ctx.channel.permissions_for(guild.me).embed_links:
                em = discord.Embed(title=guild.name + _(" Hockey Settings"))
                em.colour = await self.get_colour(ctx.channel)
                em.description = channels
                em.add_field(
                    name=_("Standings Settings"), value=f"{standings_chn}: {standings_msg}"
                )
                em.add_field(name=_("Notifications"), value=notification_settings)
                await ctx.send(embed=em)
            else:
                msg = (
                    f"```\n{guild.name} "
                    + _("Hockey Settings\n")
                    + f"{channels}\n"
                    + _("Notifications")
                    + notification_settings
                    + _("Standings Settings")
                    + "\n#{standings_chn}: {standings_msg}"
                )
                if standings_msg is not None:
                    await ctx.send(msg)
                else:
                    await ctx.send(msg + "```")

    @commands.group()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def gdc(self, ctx):
        """
        Game Day Channel setup for the server

        You can setup only a single team or all teams for the server
        Game day channels are deleted and created on the day after the game is played
        usually around 9AM PST
        """
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            create_channels = await self.config.guild(guild).create_channels()
            if create_channels is None:
                return
            team = await self.config.guild(guild).gdc_team()
            if team is None:
                team = "None"
            channels = await self.config.guild(guild).gdc()
            category = self.bot.get_channel(await self.config.guild(guild).category())
            delete_gdc = await self.config.guild(guild).delete_gdc()
            game_states = await self.config.guild(guild).gdc_state_updates()
            if category is not None:
                category = category.name
            if channels is not None:
                created_channels = ""
                for channel in channels:
                    chn = self.bot.get_channel(channel)
                    if chn is not None:
                        if ctx.channel.permissions_for(guild.me).embed_links:
                            created_channels += chn.mention
                        else:
                            created_channels += "#" + chn.name
                    else:
                        created_channels += "<#{}>\n".format(channel)
                if len(channels) == 0:
                    created_channels = "None"
            else:
                created_channels = "None"
            if not ctx.channel.permissions_for(guild.me).embed_links:
                msg = (
                    _("```GDC settings for ")
                    + guild.name
                    + "\n"
                    + _("Create Game Day Channels:")
                    + create_channels
                    + "\n"
                    + _("Delete Game Day Channels: ")
                    + delete_gdc
                    + "\n"
                    + _("Team:")
                    + team
                    + "\n"
                    + _("Current Channels: ")
                    + created_channels
                    + _("Default Game States: ")
                    + humanize_list(game_states)
                    + "```"
                )
                await ctx.send(msg)
            if ctx.channel.permissions_for(guild.me).embed_links:
                em = discord.Embed(title=_("GDC settings for ") + guild.name)
                em.colour = await self.get_colour(ctx.channel)
                em.add_field(name=_("Create Game Day Channels"), value=str(create_channels))
                em.add_field(name=_("Delete Game Day Channels"), value=str(delete_gdc))
                em.add_field(name=_("Team"), value=str(team))
                em.add_field(name=_("Current Channels"), value=created_channels[:1024])
                if not game_states:
                    game_states = ["None"]
                em.add_field(name=_("Default Game States"), value=humanize_list(game_states))
                await ctx.send(embed=em)

    #######################################################################
    # All Game Day Channel Commands

    @gdc.command(name="delete")
    async def gdc_delete(self, ctx):
        """
        Delete all current game day channels for the server
        """
        await GameDayChannels.delete_gdc(self.bot, ctx.guild)
        await ctx.send(_("Game day channels deleted."))

    @gdc.command(name="defaultstate")
    async def gdc_default_game_state(self, ctx, *state: HockeyStates):
        """
        Set the default game state updates for Game Day Channels.

        `<state>` must be any combination of `preview`, `live`, `final`, and `goal`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes before the game starts.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all the goal updates.
        """
        await self.config.guild(ctx.guild).gdc_state_updates.set(list(set(state)))
        if state:
            await ctx.send(
                _("GDC game updates set to {states}").format(
                    states=humanize_list(list(set(state)))
                )
            )
        else:
            await ctx.send(_("GDC game updates not set"))

    @gdc.command(name="create")
    async def gdc_create(self, ctx):
        """
        Creates the next gdc for the server
        """
        if not await self.config.guild(ctx.guild).gdc_team():
            return await ctx.send(_("No team was setup for game day channels in this server."))
        if await self.config.guild(ctx.guild).create_channels():
            await GameDayChannels.create_gdc(self.bot, ctx.guild)
        await ctx.send(_("Game day channels created."))

    @gdc.command(name="toggle")
    async def gdc_toggle(self, ctx):
        """
        Toggles the game day channel creation on this server
        """
        guild = ctx.message.guild
        cur_setting = not await self.config.guild(guild).create_channels()
        verb = _("will") if cur_setting else _("won't")
        msg = _("Game day channels ") + verb + _(" be created on this server.")
        await self.config.guild(guild).create_channels.set(cur_setting)
        await ctx.send(msg)

    @gdc.command(name="category")
    async def gdc_category(self, ctx, category: discord.CategoryChannel):
        """
        Change the category for channel creation. Channel is case sensitive.
        """
        guild = ctx.message.guild

        # cur_setting = await self.config.guild(guild).category()

        msg = _("Game day channels will be created in ")
        await self.config.guild(guild).category.set(category.id)
        await ctx.send(msg + category.name)

    @gdc.command(name="autodelete")
    async def gdc_autodelete(self, ctx):
        """
        Toggle's auto deletion of game day channels.
        """
        guild = ctx.message.guild

        cur_setting = await self.config.guild(guild).delete_gdc()
        verb = _("won't") if cur_setting else _("will")
        msg = (
            _("Game day channels ")
            + verb
            + _(" be deleted on this server.\n")
            + _("Note, this may not happen until the next set of games.")
        )
        await self.config.guild(guild).delete_gdc.set(not cur_setting)
        await ctx.send(msg)

    @gdc.command(name="setup")
    @commands.guild_only()
    async def gdc_setup(
        self,
        ctx,
        team: HockeyTeams,
        category: discord.CategoryChannel = None,
        delete_gdc: bool = True,
    ):
        """
        Setup game day channels for a single team or all teams

        Required parameters:
        `team` must use quotes if a space is in the name will search for partial team name
        Optional Parameters:
        `category` must use quotes if a space is in the name will default to current category
        `delete_gdc` will tell the bot whether or not to delete game day channels automatically
        must be either `True` or `False` and a category must be provided
        """
        guild = ctx.message.guild
        if category is None and ctx.channel.category is not None:
            category = guild.get_channel(ctx.channel.category_id)
        else:
            return await ctx.send(
                _("You must specify a channel category for game day channels to be created under.")
            )
        if not category.permissions_for(guild.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return
        await self.config.guild(guild).category.set(category.id)
        await self.config.guild(guild).gdc_team.set(team)
        await self.config.guild(guild).delete_gdc.set(delete_gdc)
        await self.config.guild(guild).create_channels.set(True)
        if team.lower() != "all":
            await GameDayChannels.create_gdc(self.bot, guild)
        else:
            game_list = await Game.get_games()
            for game in game_list:
                await GameDayChannels.create_gdc(self.bot, guild, game)
        await ctx.send(_("Game Day Channels for ") + team + _(" setup in ") + category.name)

    #######################################################################
    # All Hockey setup commands

    @hockeyset_commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def reset(self, ctx):
        """
        Restarts the hockey loop incase there are issues with the posts
        """
        msg = await ctx.send(_("Restarting..."))
        self.loop.cancel()
        await msg.edit(content=msg.content + _("loop closed..."))
        self.loop = self.bot.loop.create_task(self.game_check_loop())
        await msg.edit(content=msg.content + _("restarted"))
        # await ctx.send("Done.")

    @hockeyset_commands.command(hidden=True)
    async def leaderboardset(
        self, ctx, user: discord.Member, season: int, weekly: int = None, total: int = None
    ):
        """
        Allows moderators to set a users points on the leaderboard
        """
        if weekly is None:
            weekly = season
        if total is None:
            total = season
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if str(user.id) not in leaderboard:
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        else:
            del leaderboard[str(user.id)]
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard)
        msg = (
            user.display_name
            + _(" now has ")
            + season
            + _(" points on the season, ")
            + weekly
            + _(" points for the week,")
            + _(" and ")
            + total
            + _(" votes overall.")
        )
        await ctx.send(msg)

    async def check_notification_settings(self, guild: discord.Guild) -> str:
        reply = ""
        mentionable_roles = []
        non_mention_roles = []
        no_role = []
        for team in TEAMS:
            role = discord.utils.get(guild.roles, name=team)
            if not role:
                no_role.append(team)
                continue
            mentionable = role.mentionable or guild.me.guild_permissions.mention_everyone
            if mentionable:
                mentionable_roles.append(role)
            if not mentionable:
                non_mention_roles.append(role)
        if mentionable_roles:
            reply += _("__The following team roles **are** mentionable:__ {teams}\n\n").format(
                teams=humanize_list([r.mention for r in mentionable_roles]),
            )
        if non_mention_roles:
            reply += _(
                "__The following team roles **are not** mentionable:__ {non_mention}\n\n"
            ).format(non_mention=humanize_list([r.mention for r in non_mention_roles]))
        if no_role:
            reply += _("__The following team roles could not be found:__ {non_role}\n\n").format(
                non_role=humanize_list(no_role)
            )
        return reply

    @hockeyset_commands.group(name="notifications")
    async def hockey_notifications(self, ctx: commands.Context):
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="goal")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_goal_notification_style(self, ctx, on_off: Optional[bool] = None):
        """
        Set the servers goal notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).goal_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.guild(ctx.guild).goal_notifications.set(on_off)
        if on_off:
            reply = _("__Goal Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(_("Okay, I will not mention any goals in this server."))

    @hockey_notifications.command(name="game")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(self, ctx, on_off: Optional[bool] = None):
        """
        Set the servers game start notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        Server permissions can override this.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name` to work. For example
        `@Edmonton Oilers` will be pinged but `@edmonton oilers` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).game_state_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.guild(ctx.guild).game_state_notifications.set(on_off)
        if on_off:
            reply = _("__Game State Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(_("Okay, I will not mention any goals in this server."))

    @hockey_notifications.command(name="goalchannel")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_channel_goal_notification_style(
        self, ctx, channel: discord.TextChannel, on_off: Optional[bool] = None
    ):
        """
        Set the specified channels goal notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.channel(channel).game_state_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.channel(channel).goal_notifications.set(on_off)
        if on_off:
            reply = _("__Goal Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(
                _(
                    "Okay, I will not mention any goals in {channel}.\n\n"
                    " Note: This does not affect server wide settings from "
                    "`[p]hockeyset notifications goals`"
                ).format(channel=channel.mention)
            )

    @hockey_notifications.command(name="gamechannel")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_channel_game_start_notification_style(
        self, ctx, channel: discord.TextChannel, on_off: Optional[bool] = None
    ):
        """
        Set the specified channels game start notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        Server permissions can override this.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name` to work. For example
        `@Edmonton Oilers` will be pinged but `@edmonton oilers` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.channel(channel).goal_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.channel(channel).game_state_notifications.set(on_off)
        if on_off:
            reply = _("__Game State Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(
                _(
                    "Okay, I will not mention any updates in {channel}.\n\n"
                    " Note: This does not affect server wide settings from "
                    "`[p]hockeyset notifications goals`"
                ).format(channel=channel.mention)
            )

    @hockeyset_commands.command(name="poststandings", aliases=["poststanding"])
    async def post_standings(self, ctx, standings_type: str, channel: discord.TextChannel = None):
        """
        Posts automatic standings when all games for the day are done

        `standings_type` can be a division, conference, team, or all
        `channel` will default to the current channel or be specified
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.message.channel
        standings_list = [
            "metropolitan",
            "atlantic",
            "pacific",
            "central",
            "eastern",
            "western",
            "all",
        ]
        # division = ["metropolitan", "atlantic", "pacific", "central"]

        if standings_type.lower() not in standings_list:
            await ctx.send(
                _("You must choose from ") + "{}".format(", ".join(s for s in standings_list))
            )
            return

        standings, page = await Standings.get_team_standings(standings_type.lower())
        if standings_type.lower() != "all":
            em = await Standings.build_standing_embed(standings, page)
        else:
            em = await Standings.all_standing_embed(standings)
        await self.config.guild(guild).standings_type.set(standings_type)
        await self.config.guild(guild).standings_channel.set(channel.id)
        await ctx.send(_("Sending standings to ") + channel.mention)
        message = await channel.send(embed=em)
        await self.config.guild(guild).standings_msg.set(message.id)
        await ctx.send(
            standings_type
            + _(" standings will now be automatically updated in ")
            + channel.mention
        )
        await self.config.guild(guild).post_standings.set(True)

    @hockeyset_commands.command()
    async def togglestandings(self, ctx):
        """
        Toggles automatic standings updates

        This updates at the same time as the game day channels (usually 9AM PST)
        """
        guild = ctx.message.guild
        cur_state = not await self.config.guild(guild).post_standings()
        verb = _("will") if cur_state else _("won't")
        msg = _("Okay, standings ") + verb + _(" be updated automatically.")
        await self.config.guild(guild).post_standings.set(cur_state)
        await ctx.send(msg)

    @hockeyset_commands.command(name="stateupdates")
    async def set_game_state_updates(
        self, ctx, channel: discord.TextChannel, *state: HockeyStates
    ):
        """
        Set what type of game updates to be posted in the designated channel.

        `<channel>` is a text channel for the updates.
        `<state>` must be any combination of `preview`, `live`, `final`, `goal` and `periodrecap`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes
        before the game starts and the pre-game notification at the start of the day.

        Note: This may disable pickems if it is not selected.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all goal updates.
        `periodrecap` is a recap of the period at the intermission.
        """
        await self.config.channel(channel).game_states.set(list(set(state)))
        await ctx.send(
            _("{channel} game updates set to {states}").format(
                channel=channel.mention, states=humanize_list(list(set(state)))
            )
        )
        if not await self.config.channel(channel).team():
            await ctx.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="publishupdates", hidden=True)
    @checks.is_owner()
    async def set_game_publish_updates(
        self, ctx, channel: discord.TextChannel, *state: HockeyStates
    ):
        """
        Set what type of game updates will be published in the designated news channel.

        Note: Discord has a limit on the number of published messages per hour.
        This does not error on the bot and can lead to waiting forever for it to update.

        `<channel>` is a text channel for the updates.
        `<state>` must be any combination of `preview`, `live`, `final`, and `periodrecap`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes
        before the game starts and the pre-game notification at the start of the day.

        Note: This may disable pickems if it is not selected.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `periodrecap` is a recap of the period at the intermission.
        """
        if not channel.is_news():
            return await ctx.send(
                _("The designated channel is not a news channel that I can publish in.")
            )
        await self.config.channel(channel).publish_states.set(list(set(state)))
        await ctx.send(
            _("{channel} game updates set to publish {states}").format(
                channel=channel.mention, states=humanize_list(list(set(state)))
            )
        )
        if not await self.config.channel(channel).team():
            await ctx.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="add", aliases=["add_goals"])
    async def add_goals(self, ctx, team: HockeyTeams, channel: discord.TextChannel):
        """
        Adds a hockey team goal updates to a channel do 'all' for all teams

        `team` needs to be all or part of an NHL team if more than one team
        match it will ask for the correct team.
        `channel` defaults to the current channel
        """
        guild = ctx.message.guild
        # team_data = await self.get_team(team)
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(guild.me).embed_links:
            await ctx.send(_("I don't have embed links permission!"))
            return
        cur_teams = await self.config.channel(channel).team()
        cur_teams = [] if cur_teams is None else cur_teams
        if team in cur_teams:
            await self.config.channel(channel).team.set([team])
        else:
            cur_teams.append(team)
            await self.config.channel(channel).team.set(cur_teams)
        await ctx.send(team + _(" goals will be posted in ") + channel.mention)

    @hockeyset_commands.command(name="del", aliases=["remove", "rem"])
    async def remove_goals(
        self, ctx, team: HockeyTeams = None, channel: discord.TextChannel = None
    ):
        """
        Removes a teams goal updates from a channel
        defaults to the current channel
        """
        if channel is None:
            channel = ctx.message.channel
        cur_teams = await self.config.channel(channel).team()
        if cur_teams is None:
            await ctx.send(_("No teams are currently being posted in ") + channel.mention)
            return
        if team is None:
            await self.config.channel(channel).clear()
            await ctx.send(_("All goal updates will not be posted in ") + channel.mention)
            return
        if team is not None:
            # guild = ctx.message.guild
            if team in cur_teams:
                cur_teams.remove(team)
                if cur_teams == []:
                    await self.config.channel(channel).clear()
                    await ctx.send(_("All goal updates will not be posted in ") + channel.mention)
                else:
                    await self.config.channel(channel).team.set(cur_teams)
                    await ctx.send(team + _(" goal updates removed from ") + channel.mention)

    #######################################################################
    # All Basic Hockey Commands

    @hockey_commands.command()
    async def version(self, ctx):
        """
        Display the current version
        """
        await ctx.send(_("Hockey version ") + self.__version__)

    @commands.command()
    async def hockeyhub(self, ctx, *, search: str):
        """
        Search for hockey related items on https://hockeyhub.github.io/

        lines   team    Team lines on Daily Faceoff
        stats   [year] team Team stats on nhl.com, year optional
        schedule    team    Team schedule on nhl.com
        draft   team oryear Draft history for team or year on Elite Prospects
        cap team orplayer   Cap information for team or player on CapFriendly
        player  player  Search for player on Elite Prospects
        depth   team    Team depth chart on Elite Prospects
        prospects   team    Team prospects on Elite Prospects
        trades  team    Team trade history on NHL Trade Tracker
        jersey  [team] number orname    Find a player by jersey number
        highlights  [team]  Game Highlights, team optional
        reddit  team    Team subreddit on Reddit
        """
        search = quote(search)
        await ctx.send("https://hh.sbstp.ca/?search=" + search)

    @hockey_commands.command(name="role")
    @checks.bot_has_permissions(manage_roles=True)
    async def team_role(self, ctx, *, team: HockeyTeams):
        """Set your role to a team role"""
        guild = ctx.message.guild
        try:
            role = [
                role
                for role in guild.roles
                if (team.lower() in role.name.lower() and "GOAL" not in role.name)
            ]
            if role[0] >= guild.me.top_role:
                return
            await ctx.author.add_roles(role[0])
            await ctx.send(role[0].name + _(" role applied."))
        except Exception:
            log.error("error adding team role", exc_info=True)
            await ctx.send(team + _(" is not an available role!"))

    @hockey_commands.command(name="goalsrole")
    async def team_goals(self, ctx, *, team: HockeyTeams = None):
        """Subscribe to goal notifications"""
        guild = ctx.message.guild
        member = ctx.message.author
        if not guild.me.guild_permissions.manage_roles:
            return
        if team is None:
            team_roles = []
            for role in guild.roles:
                if role.name in [r.name + " GOAL" for r in member.roles]:
                    team_roles.append(role)
            if team_roles != []:
                for role in team_roles:
                    if role[0] >= guild.me.top_role:
                        continue
                    await ctx.message.author.add_roles(role)
                role_list = ", ".join(r.name for r in team_roles)
                await ctx.message.channel.send(f"{role_list} role applied.")
                return
            else:
                await ctx.send(_("Please provide the team you want the goal notification role for."))
                return
        else:
            try:
                role = [
                    role
                    for role in guild.roles
                    if (team.lower() in role.name.lower() and role.name.endswith("GOAL"))
                ]
                await ctx.message.author.add_roles(role[0])
                await ctx.message.channel.send(role[0].name + _(" role applied."))
            except Exception:
                await ctx.message.channel.send(team + _(" is not an available role!"))

    @hockey_commands.command()
    @checks.bot_has_permissions(embed_links=True)
    async def standings(self, ctx, *, search: HockeyStandings = None):
        """
        Displays current standings

        If a search is provided you can see a teams complete stats
        by searching for team or get all standings at once
        separated by division
        """
        source = {
            "all": StandingsPages,
            "conference": ConferenceStandingsPages,
            "western": ConferenceStandingsPages,
            "eastern": ConferenceStandingsPages,
            "division": DivisionStandingsPages,
            "massmutual": DivisionStandingsPages,
            "central": DivisionStandingsPages,
            "discover": DivisionStandingsPages,
            "scotia": DivisionStandingsPages,
            "north": DivisionStandingsPages,
            "massmutual": DivisionStandingsPages,
            "east": DivisionStandingsPages,
            "honda": DivisionStandingsPages,
            "west": DivisionStandingsPages,
        }
        if search is None:
            search = "division"
        standings, page = await Standings.get_team_standings(search.lower())
        for team in TEAMS:
            if "Team" in team:
                source[team.replace("Team ", "").lower()] = DivisionStandingsPages
            else:
                source[team] = TeamStandingsPages
        await BaseMenu(
            source=source[search](pages=standings),
            page_start=page,
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @hockey_commands.command(aliases=["score"])
    async def games(self, ctx, *, teams_and_date: Optional[TeamDateFinder] = {}):
        """
        Gets all NHL games for the current season

        If team is provided it will grab that teams schedule
        """
        log.debug(teams_and_date)
        await GamesMenu(
            source=Schedule(**teams_and_date),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @hockey_commands.command()
    async def schedule(self, ctx, *, teams_and_date: Optional[TeamDateFinder] = {}):
        """
        Gets all upcoming NHL games for the current season as a list

        If team is provided it will grab that teams schedule
        """
        log.debug(teams_and_date)
        await GamesMenu(
            source=ScheduleList(**teams_and_date),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    async def player_id_lookup(self, name: str):
        now = datetime.utcnow()
        saved = datetime.fromtimestamp(await self.config.player_db())
        path = cog_data_path(self) / "players.json"
        if (now - saved) > timedelta(days=1) or not path.exists():
            async with aiohttp.ClientSession() as session:
                async with session.get("https://records.nhl.com/site/api/player?include=id&include=fullName&include=onRoster") as resp:
                    with path.open(encoding="utf-8", mode="w") as f:
                        json.dump(await resp.json(), f)
            await self.config.player_db.set(int(now.timestamp()))
        with path.open(encoding="utf-8", mode="r") as f:

            players = []
            for player in json.loads(f.read())["data"]:
                if name.lower() in player["fullName"].lower():
                    if player["onRoster"] == "N":
                        players.append(player["id"])
                    else:
                        players.insert(0, player["id"])
        log.debug(players)
        return players

    @hockey_commands.command(aliases=["players"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def player(
        self,
        ctx: commands.Context,
        *,
        search: str,
    ):
        """
        Lookup information about a specific player

        `<search>` The name of the player to search for
        you can include the season to get stats data on format can be `YYYY` or `YYYYYYYY`
        """
        async with ctx.typing():
            season = YEAR_RE.search(search)
            season_str = None
            if season:
                search = YEAR_RE.sub("", search)
                if season.group(3):
                    if (int(season.group(3)) - int(season.group(1))) > 1:
                        return await ctx.send(_("Dates must be only 1 year apart."))
                    if (int(season.group(3)) - int(season.group(1))) <= 0:
                        return await ctx.send(_("Dates must be only 1 year apart."))
                    if int(season.group(1)) > datetime.now().year:
                        return await ctx.send(_("Please select a year prior to now."))
                    season_str = f"{season.group(1)}{season.group(3)}"
                else:
                    if int(season.group(1)) > datetime.now().year:
                        return await ctx.send(_("Please select a year prior to now."))
                    year = int(season.group(1)) + 1
                    season_str = f"{season.group(1)}{year}"
            log.debug(season)
            log.debug(search)
            players = await self.player_id_lookup(search.strip())
        if players != []:
            await BaseMenu(
                source=PlayerPages(pages=players, season=season_str),
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
        else:
            await ctx.send(
                _('I could not find any player data for "{player}".').format(player=search)
            )

    @hockey_commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def roster(self, ctx, season: Optional[YearFinder] = None, *, search: HockeyTeams):
        """
        Search for a player or get a team roster

        `[season]` The season to get stats data on format can be `YYYY` or `YYYYYYYY`
        `<search>` The name of the team to search for
        """
        season_str = None
        season_url = ""
        if season:
            if season.group(3):
                if (int(season.group(3)) - int(season.group(1))) > 1:
                    return await ctx.send(_("Dates must be only 1 year apart."))
                if (int(season.group(3)) - int(season.group(1))) <= 0:
                    return await ctx.send(_("Dates must be only 1 year apart."))
                if int(season.group(1)) > datetime.now().year:
                    return await ctx.send(_("Please select a year prior to now."))
                season_str = f"{season.group(1)}{season.group(3)}"
            else:
                if int(season.group(1)) > datetime.now().year:
                    return await ctx.send(_("Please select a year prior to now."))
                year = int(season.group(1)) + 1
                season_str = f"{season.group(1)}{year}"
        if season:
            season_url = f"?season={season_str}"
        rosters = {}
        players = []
        teams = [team for team in TEAMS if search.lower() in team.lower()]
        if teams != []:
            for team in teams:
                url = f"{BASE_URL}/api/v1/teams/{TEAMS[team]['id']}/roster{season_url}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        data = await resp.json()
                if "roster" in data:
                    for player in data["roster"]:
                        players.append(player["person"]["id"])
        else:
            return await ctx.send(_("No team name was provided."))

        if players:
            await BaseMenu(
                source=PlayerPages(pages=players, season=season_str),
                delete_message_after=False,
                clear_reactions_after=True,
                timeout=60,
            ).start(ctx=ctx)
        else:
            if season:
                year = _(" in the {season} season").format(
                    season=f"{season.group(1)}-{season.group(3)}"
                )
            else:
                year = ""
            await ctx.send(
                _("I could not find a roster for the {team}{year}.").format(team=team, year=year)
            )

    @hockey_commands.command(hidden=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def rules(self, ctx):
        """
        Display a nice embed of server specific rules
        """
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            return
        rules = await self.config.guild(ctx.guild).rules()
        team = await self.config.guild(ctx.guild).team_rules()
        if rules == "":
            return
        em = await self.make_rules_embed(ctx.guild, team, rules)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()
        await ctx.send(embed=em)

    @staticmethod
    async def make_rules_embed(guild, team, rules):
        """
        Builds the rule embed for the server
        """
        warning = _(
            "***Violating [Discord Terms of Service](https://discordapp.com/terms) "
            "or [Community Guidelines](https://discordapp.com/guidelines) will "
            "result in an immediate ban. You may also be reported to Discord.***"
        )
        em = discord.Embed(colour=int(TEAMS[team]["home"].replace("#", ""), 16))
        em.description = rules
        em.title = _("__RULES__")
        em.add_field(name=_("__**WARNING**__"), value=warning)
        em.set_thumbnail(url=guild.icon_url)
        em.set_author(name=guild.name, icon_url=guild.icon_url)
        return em

    @hockeyset_commands.command(name="pickemspage", hidden=True)
    @checks.admin_or_permissions(manage_channels=True)
    async def pickems_page(self, ctx, date: str = None):
        """
        Generates a pickems page for voting on a specified day must be "YYYY-MM-DD"
        """
        if date is None:
            new_date = datetime.now()
        else:
            new_date = datetime.strptime(date, "%Y-%m-%d")
        msg = _(
            "**Welcome to our daily Pick'ems challenge!  Below you will see today's games!"
            "  Vote for who you think will win!  You get one point for each correct prediction."
            "  We will be tracking points over the course "
            "of the season and will be rewarding weekly,"
            " worst and full-season winners!**\n\n"
            "- Click the reaction for the team you think will win the day's match-up.\n"
            "- Anyone who votes for both teams will have their "
            "vote removed and will receive no points!\n\n\n\n"
        )
        games_list = await Game.get_games(None, new_date, new_date)
        await ctx.send(msg)
        async with self.pickems_save_lock:
            for game in games_list:
                new_msg = await ctx.send(
                    "__**{} {}**__ @ __**{} {}**__".format(
                        game.away_emoji, game.away_team, game.home_emoji, game.home_team
                    )
                )
                # Create new pickems object for the game

                await Pickems.create_pickem_object(self.bot, ctx.guild, new_msg, ctx.channel, game)
                if ctx.channel.permissions_for(ctx.guild.me).add_reactions:
                    try:
                        await new_msg.add_reaction(game.away_emoji[2:-1])
                        await new_msg.add_reaction(game.home_emoji[2:-1])
                    except Exception:
                        log.debug("Error adding reactions")

    @hockeyset_commands.command(name="autopickems")
    @checks.admin_or_permissions(manage_channels=True)
    async def setup_auto_pickems(self, ctx, category: discord.CategoryChannel = None):
        """
        Sets up automatically created pickems channels every week.

        `[category]` the channel category where pickems channels will be created.
        """

        if category is None and not ctx.channel.category:
            return await ctx.send(_("A channel category is required."))
        elif category is None and ctx.channel.category is not None:
            category = ctx.channel.category
        else:
            pass
        if not category.permissions_for(ctx.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return

        await self.config.guild(ctx.guild).pickems_category.set(category.id)
        existing_channels = await self.config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        async with self.pickems_save_lock:
            log.debug("Locking save")
            await Pickems.create_weekly_pickems_pages(self.bot, [ctx.guild], Game)
        await ctx.send(_("I will now automatically create pickems pages every Sunday."))

    @hockeyset_commands.command(name="clearpickems")
    @checks.admin_or_permissions(manage_channels=True)
    async def delete_auto_pickems(self, ctx):
        """
        Automatically delete all the saved pickems channels.
        """
        existing_channels = await self.config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        await ctx.send(_("I have deleted existing pickems channels."))

    @hockeyset_commands.command(name="toggleautopickems")
    @checks.admin_or_permissions(manage_channels=True)
    async def toggle_auto_pickems(self, ctx):
        """
        Turn off automatic pickems page creation
        """
        await self.config.guild(ctx.guild).pickems_category.set(None)
        await ctx.tick()

    async def post_leaderboard(self, ctx, leaderboard_type):
        """
        Posts the leaderboard based on specific style
        """
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if leaderboard_type != "worst":
            leaderboard = sorted(
                leaderboard.items(), key=lambda i: i[1][leaderboard_type], reverse=True
            )
        else:
            leaderboard = sorted(
                leaderboard.items(), key=lambda i: i[1]["total"] - i[1]["season"], reverse=True
            )
        msg_list = []
        count = 1
        user_position = None
        for member_id in leaderboard:
            if str(member_id[0]) == str(ctx.author.id):
                user_position = leaderboard.index(member_id)
            member = ctx.guild.get_member(int(member_id[0]))
            if member is None:
                member_mention = _("User has left the server ") + member_id[0]
            else:
                member_mention = member.mention
            if leaderboard_type == "weekly":
                points = member_id[1]["weekly"]
                msg_list.append("#{}. {}: {}\n".format(count, member_mention, points))
            elif leaderboard_type == "season":
                total = member_id[1]["total"]
                wins = member_id[1]["season"]
                percent = (wins / total) * 100
                msg_list.append(
                    f"#{count}. {member_mention}: {wins}/{total} correct ({percent:.4}%)\n"
                )
            else:
                total = member_id[1]["total"]
                losses = member_id[1]["total"] - member_id[1]["season"]
                percent = (losses / total) * 100
                msg_list.append(
                    f"#{count}. {member_mention}: {losses}/{total} incorrect ({percent:.4}%)\n"
                )
            count += 1
        leaderboard_list = [msg_list[i : i + 10] for i in range(0, len(msg_list), 10)]
        if user_position is not None:
            user = leaderboard[user_position][1]
            wins = user["season"]
            total = user["total"]
            losses = user["total"] - user["season"]
            position = (
                ctx.author.display_name
                + _(", you're #")
                + str(user_position + 1)
                + " on the "
                + leaderboard_type
                + _(" leaderboard!")
            )
            if leaderboard_type == "season":
                percent = (wins / total) * 100
                position += (
                    _(" You have ") + f"{wins}/{total} " + _("correct ") + f"({percent:.4}%)."
                )
            elif leaderboard_type == "worst":
                percent = (losses / total) * 100
                position += (
                    _(" You have ") + f"{losses}/{total} " + _("incorrect ") + f"({percent:.4}%)."
                )
            await ctx.send(position)
        await BaseMenu(
            source=LeaderboardPages(pages=leaderboard_list, style=leaderboard_type),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @hockey_commands.command()
    @commands.guild_only()
    async def leaderboard(self, ctx, leaderboard_type: str = "seasonal"):
        """
        Shows the current server leaderboard either seasonal or weekly
        """
        if leaderboard_type in ["seasonal", "season"]:
            await self.post_leaderboard(ctx, "season")
        if leaderboard_type in ["weekly", "week"]:
            await self.post_leaderboard(ctx, "weekly")
        if leaderboard_type in ["worst"]:
            await self.post_leaderboard(ctx, "worst")

    @hockey_commands.command(hidden=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def setrules(self, ctx, team: HockeyTeams, *, rules):
        """Set the main rules page for the nhl rules command"""
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            await ctx.send(_("I don't have embed links permission!"))
            return
        await self.config.guild(ctx.guild).rules.set(rules)
        await self.config.guild(ctx.guild).team_rules.set(team)
        em = await self.make_rules_embed(ctx.guild, team, rules)
        await ctx.send(_("Done, here's how it will look."), embed=em)

    @hockey_commands.command(aliases=["link", "invite"])
    async def otherdiscords(self, ctx, team: HockeyTeams):
        """
        Get team specific discord links

        choosing all will create a nicely formatted list of
        all current NHL team discord server links
        """
        if team not in ["all"]:
            await ctx.send(TEAMS[team]["invite"])
        else:
            if not ctx.channel.permissions_for(ctx.message.author).manage_messages:
                # Don't need everyone spamming this command
                return
            atlantic = [team for team in TEAMS if TEAMS[team]["division"] == "Atlantic"]
            metropolitan = [team for team in TEAMS if TEAMS[team]["division"] == "Metropolitan"]
            central = [team for team in TEAMS if TEAMS[team]["division"] == "Central"]
            pacific = [team for team in TEAMS if TEAMS[team]["division"] == "Pacific"]
            team_list = {
                "Atlantic": atlantic,
                "Metropolitan": metropolitan,
                "Central": central,
                "Pacific": pacific,
            }
            msg1 = _(
                "__**Hockey Discord Master List**__\n```fix\n"
                "- Do not join other discords to troll.\n- "
                "Respect their rules & their members "
                "(Yes even the leafs & habs unfortunately).\n- "
                "We don't control the servers below. "
                "If you get banned we can not get you unbanned.\n- "
                "Don't be an asshole because then we all look like assholes. "
                "They won't see it as one asshole "
                "fan they will see it as a toxic fanbase.\n- "
                "Salt levels may vary. Your team is the best "
                "here but don't go on another discord and preach "
                "it to an angry mob after we just won.\n- "
                "Not following the above rules will result in "
                "appropriate punishments ranging from a warning "
                "to a ban. ```\n\nhttps://discord.gg/reddithockey"
            )
            eastern_conference = "https://i.imgur.com/CtXvcCs.png"
            western_conference = "https://i.imgur.com/UFYJTDF.png"
            async with aiohttp.ClientSession() as session:
                async with session.get(eastern_conference) as resp:
                    data = await resp.read()
            logo = BytesIO()
            logo.write(data)
            logo.seek(0)
            image = discord.File(logo, filename="eastern_logo.png")
            await ctx.send(msg1, file=image)
            for division in team_list:
                if division == "Central":
                    async with aiohttp.ClientSession() as session:
                        async with session.get(western_conference) as resp:
                            data = await resp.read()
                    logo = BytesIO()
                    logo.write(data)
                    logo.seek(0)
                    image = discord.File(logo, filename="western_logo.png")
                    await ctx.send(file=image)
                div_emoji = "<:" + TEAMS["Team {}".format(division)]["emoji"] + ">"
                msg = "{0} __**{1} DIVISION**__ {0}".format(div_emoji, division.upper())
                await ctx.send(msg)
                for team in team_list[division]:
                    team_emoji = "<:" + TEAMS[team]["emoji"] + ">"
                    team_link = TEAMS[team]["invite"]
                    msg = "{0} {1} {0}".format(team_emoji, team_link)
                    await ctx.send(msg)

    async def save_pickems_unload(self):
        try:
            async with self.pickems_save_lock:
                for guild_id, pickems in self.all_pickems.items():
                    guild_obj = discord.Object(id=int(guild_id))
                    await self.config.guild(guild_obj).pickems.set(
                        {name: p.to_json() for name, p in pickems.items()}
                    )
        except AttributeError:
            # I removed this for testing most likely
            pass
        except Exception:
            log.exception("Something went wrong with the pickems unload")

    def cog_unload(self):
        self.bot.loop.create_task(self.save_pickems_unload())
        if getattr(self, "loop", None) is not None:
            self.loop.cancel()
        if getattr(self, "pickems_save_loop", None) is not None:
            log.debug("canceling pickems save loop")
            self.save_pickems = False
            self.pickems_save_loop.cancel()
