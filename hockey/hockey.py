import discord
import aiohttp
import asyncio
import json
import yaml
import logging

from io import BytesIO
from typing import Union
from datetime import datetime, timedelta, date
from urllib.parse import quote

from redbot.core import commands, checks, Config, VersionInfo, version_info
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list


from .teamentry import TeamEntry
from .menu import hockey_menu
from .embeds import make_rules_embed
from .helper import HockeyStandings, HockeyTeams, get_season, HockeyStates
from .errors import UserHasVotedError, VotingHasEndedError, NotAValidTeamError, InvalidFileError
from .game import Game
from .pickems import Pickems
from .standings import Standings
from .gamedaychannels import GameDayChannels
from .constants import BASE_URL, CONFIG_ID, TEAMS, HEADSHOT_URL

try:
    from .oilers import Oilers

    LIGHTS_SET = True
except ImportError:
    LIGHTS_SET = False
    pass

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


@cog_i18n(_)
class Hockey(commands.Cog):
    """
        Gather information and post goal updates for NHL hockey teams
    """

    __version__ = "2.8.15"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        default_global = {"teams": [], "created_gdc": False, "print": False}
        for team in TEAMS:
            team_entry = TeamEntry("Null", team, 0, [], {}, [], "")
            default_global["teams"].append(team_entry.to_json())
        default_global["teams"].append(team_entry.to_json())
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
            "pickems": [],
            "leaderboard": {},
            "pickems_category": None,
            "pickems_channels": [],
            "game_state_notifications": False,
            "goal_notifications": False,
            "gdc_state_updates": ["Preview", "Live", "Final", "Goal"],
        }
        default_channel = {
            "team": [],
            "game_states": ["Preview", "Live", "Final", "Goal"],
            "to_delete": False,
            "publish_states": [],
        }

        self.config = Config.get_conf(self, CONFIG_ID, force_registration=True)
        self.config.register_global(**default_global, force_registration=True)
        self.config.register_guild(**default_guild, force_registration=True)
        self.config.register_channel(**default_channel, force_registration=True)
        self.loop = bot.loop.create_task(self.game_check_loop())
        self.TEST_LOOP = False  # used to test a continuous loop of a single game data
        self.all_pickems = {}
        self.pickems_save_loop = bot.loop.create_task(self.save_pickems_data())
        self.save_pickems = True
        self.pickems_save_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

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
        while self is self.bot.get_cog("Hockey"):
            # await self.refactor_data()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(BASE_URL + "/api/v1/schedule") as resp:
                        data = await resp.json()
            except Exception:
                log.debug(_("Error grabbing the schedule for today."), exc_info=True)
                data = {"dates": []}
            if data["dates"] != []:
                games = [
                    game["link"]
                    for game in data["dates"][0]["games"]
                    if game["status"]["abstractGameState"] != "Final"
                ]
            else:
                games = []
                # Only try to create game day channels if there's no games for the day
                # Otherwise make the game day channels once we see
                # the first preview message to delete old ones
                await self.check_new_day()
            games_playing = False
            if self.TEST_LOOP:
                games = [1]
            while games != []:
                to_remove = {}
                games_playing = True
                for link in games:
                    if link not in to_remove:
                        to_remove[link] = 0
                    if not self.TEST_LOOP:
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(BASE_URL + link) as resp:
                                    data = await resp.json()
                        except Exception:
                            log.error(_("Error grabbing game data: "), exc_info=True)
                            continue
                    else:
                        games_playing = False
                        with open(str(__file__)[:-9] + "testgame.json", "r") as infile:
                            data = json.loads(infile.read())
                    try:
                        game = await Game.from_json(data)
                    except Exception:
                        log.error(_("Error creating game object from json."), exc_info=True)
                        continue
                    try:
                        await self.check_new_day()
                        await game.check_game_state(self.bot)
                    except Exception:
                        log.error("Error checking game state: ", exc_info=True)

                    log.debug(
                        (
                            f"{game.away_team} @ {game.home_team} "
                            f"{game.game_state} {game.away_score} - {game.home_score}"
                        )
                    )

                    if game.game_state == "Final":
                        try:
                            await Pickems.set_guild_pickem_winner(self.bot, game)
                        except Exception:
                            log.error(_("Pickems Set Winner error: "), exc_info=True)
                        if game.first_star is None:
                            # Wait a bit longer until the three stars show up
                            to_remove[link] += 1

                for link, count in to_remove.items():
                    if count >= 1:
                        games.remove(link)
                await asyncio.sleep(60)
            log.debug(_("Games Done Playing"))
            try:
                await Pickems.tally_leaderboard(self.bot)
            except Exception:
                log.error(_("Error tallying leaderboard:"), exc_info=True)
                pass
            if games_playing:
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
            for guild_id, pickems in self.all_pickems.items():
                guild_obj = discord.Object(id=int(guild_id))
                async with self.pickems_save_lock:
                    log.debug("Saving pickems data")
                    await self.config.guild(guild_obj).pickems.set(
                        {name: p.to_json() for name, p in pickems.items()}
                    )
            await asyncio.sleep(60)

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
        except AttributeError:
            msg = await channel.get_message(id=payload.message_id)
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
                        channels += (
                            _("Game Sates: ")
                            + ", ".join(s for s in game_states)
                        )
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
                em.add_field(name=_("Current Channels"), value=created_channels)
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
                _("GDC game updates set to {states}").format(states=humanize_list(list(set(state))))
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

    @hockeyset_commands.command(name="goalnotifications")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_goal_notification_style(self, ctx, style: Union[bool, str]):
        """
            Set the servers goal notification style. Options are:

            `True` - The bot will try to find correct role names for each team and mention that role.
            Server permissions can override this.
            `False` - The bot will not post any mention for roles.
            `Auto` - The bot will automatically adjust the roles permission for the notification and then remove it after.
        """
        if isinstance(style, str):
            if style.lower() != "auto":
                return await ctx.send(_("That is not a valid style."))
        await self.config.guild(ctx.guild).goal_notifications.set(style)
        await ctx.tick()

    @hockeyset_commands.command(name="gamenotifications")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(self, ctx, style: Union[bool, str]):
        """
            Set the servers game start notification style. Options are:

            `True` - The bot will try to find correct role names for each team and mention that role.
            Server permissions can override this.
            `False` - The bot will not post any mention for roles.
            `Auto` - The bot will automatically adjust the roles permission for the notification and then remove it after.
        """
        if isinstance(style, str):
            if style.lower() != "auto":
                return await ctx.send(_("That is not a valid style."))
        await self.config.guild(ctx.guild).game_state_notifications.set(style)
        await ctx.tick()

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
            em = await Standings.all_standing_embed(standings, page)
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
            `<state>` must be any combination of `preview`, `live`, `final`, and `goal`.

            `preview` updates are the pre-game notifications 60, 30, and 10 minutes
            before the game starts and the pre-game notification at the start of the day.

            Note: This may disable pickems if it is not selected.
            `live` are the period start notifications.
            `final` is the final game update including 3 stars.
            `goal` is all the goal updates.
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
    async def set_game_publish_updates(
        self, ctx, channel: discord.TextChannel, *state: HockeyStates
    ):
        """
            Set what type of game updates will be published in the designated news channel.

            `<channel>` is a text channel for the updates.
            `<state>` must be any combination of `preview`, `live`, `final`, and `goal`.

            `preview` updates are the pre-game notifications 60, 30, and 10 minutes
            before the game starts and the pre-game notification at the start of the day.

            Note: This may disable pickems if it is not selected.
            `live` are the period start notifications.
            `final` is the final game update including 3 stars.
            `goal` is all the goal updates.
        """
        if not channel.is_news():
            return await ctx.send(_("The designated channel is not a news channel that I can publish in."))
        await self.config.channel(channel).publish_states.set(list(set(state)))
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
            await ctx.send(role[0].name + _("role applied."))
        except Exception:
            log.error("error adding team role", exc_info=True)
            await ctx.send(team + _(" is not an available role!"))

    @hockey_commands.command(name="goals")
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
    async def standings(self, ctx, *, search: HockeyStandings = None):
        """
            Displays current standings

            If a search is provided you can see a teams complete stats
            by searching for team or get all standings at once
            separated by division
        """
        if search is None:
            standings, page = await Standings.get_team_standings("division")
            await hockey_menu(ctx, "standings", standings)
            return
        standings, page = await Standings.get_team_standings(search.lower())
        if search != "all":
            await hockey_menu(ctx, "standings", standings, None, page)
        else:
            await hockey_menu(ctx, "all", standings, None, page)

    @hockey_commands.command(aliases=["score"])
    async def games(self, ctx, *, team: HockeyTeams = None):
        """
            Gets all NHL games for the current season

            If team is provided it will grab that teams schedule
        """
        games_list: list = []
        page_num = 0
        today = datetime.now()
        start_date = datetime.strptime(f"{get_season()[0]}-7-1", "%Y-%m-%d")
        games_list = await Game.get_games_list(team, start_date)
        for game in games_list:
            game_time = datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ")
            if game_time >= today:
                page_num = games_list.index(game)
                break
        if games_list != []:
            await hockey_menu(ctx, "game", games_list, None, page_num)
        else:
            if team:
                await ctx.message.channel.send(team + _(" have no recent or upcoming games!"))
            else:
                await ctx.send(_("There are currently no scheduled upcoming NHL games."))

    @hockey_commands.command(aliases=["player"])
    async def players(self, ctx, *, search):
        """
            Search for a player or get a team roster
        """
        rosters = {}
        players = []
        teams = [team for team in TEAMS if search.lower() in team.lower()]
        if teams != []:
            for team in teams:
                url = f"{BASE_URL}/api/v1/teams/{TEAMS[team]['id']}/roster"
                async with self.session.get(url) as resp:
                    data = await resp.json()
                for player in data["roster"]:
                    players.append(player)
        else:
            for team in TEAMS:
                url = f"{BASE_URL}/api/v1/teams/{TEAMS[team]['id']}/roster"
                async with self.session.get(url) as resp:
                    data = await resp.json()
                try:
                    rosters[team] = data["roster"]
                except KeyError:
                    pass

            for team in rosters:
                for player in rosters[team]:
                    if search.lower() in player["person"]["fullName"].lower():
                        players.append(player)

        if players != []:
            await hockey_menu(ctx, "roster", players)
        else:
            await ctx.send(search + _(" is not an NHL team or Player!"))

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
        em = await make_rules_embed(ctx.guild, team, rules)
        if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await ctx.message.delete()
        await ctx.send(embed=em)

    @hockey_commands.command(name="pickemspage", hidden=True)
    @checks.admin_or_permissions(manage_messages=True)
    async def pickems_page(self, ctx, date: str = None):
        """
            Generates a pickems page for voting on a specified day must be "DD-MM-YYYY"
        """
        if date is None:
            new_date = datetime.now()
        else:
            new_date = datetime.strptime(date, "%d-%m-%Y")
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
        for game in games_list:
            new_msg = await ctx.send(
                "__**{} {}**__ @ __**{} {}**__".format(
                    game.away_emoji, game.away_team, game.home_emoji, game.home_team
                )
            )
            # Create new pickems object for the game

            await Pickems.create_pickem_object(ctx.guild, new_msg, ctx.channel, game)
            if ctx.channel.permissions_for(ctx.guild.me).add_reactions:
                try:
                    await new_msg.add_reaction(game.away_emoji[2:-1])
                    await new_msg.add_reaction(game.home_emoji[2:-1])
                except Exception:
                    log.debug("Error adding reactions")
        await self.initialize_pickems()

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
        async with self.pickems_save_lock:
            log.debug("Locking save")
            await Pickems.create_weekly_pickems_pages(self.bot, [ctx.guild], Game)
            # await self.initialize_pickems()
        await ctx.send(_("I will now automatically create pickems pages every Sunday."))

    @hockeyset_commands.command(name="toggleautopickems")
    @checks.admin_or_permissions(manage_channels=True)
    async def toggle_auto_pickems(self, ctx):
        """
            Turn off automatic pickems page creation
        """
        await self.config.guild(ctx.guild).pickems_category.set(None)
        await ctx.tick()

    @hockeyset_commands.command(name="resetpickemsweekly", hidden=True)
    @checks.is_owner()
    async def reset_weekly_pickems_data(self, ctx: commands.Context):
        """
            Force reset all pickems data for the week
        """
        await Pickems.reset_weekly(self.bot)
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
        await ctx.send("Finished resetting all pickems data.")

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
        await hockey_menu(ctx, leaderboard_type, leaderboard_list)

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
        em = await make_rules_embed(ctx.guild, team, rules)
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
                "appropriate punishments ranging from a warning"
                "to a ban. ```\n\nhttps://discord.gg/reddithockey"
            )
            eastern_conference = "https://i.imgur.com/CtXvcCs.png"
            western_conference = "https://i.imgur.com/UFYJTDF.png"
            async with self.session.get(eastern_conference) as resp:
                data = await resp.read()
            logo = BytesIO()
            logo.write(data)
            logo.seek(0)
            image = discord.File(logo, filename="eastern_logo.png")
            await ctx.send(msg1, file=image)
            for division in team_list:
                if division == "Central":
                    async with self.session.get(western_conference) as resp:
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

    @hockey_commands.command(hidden=True)
    @checks.is_owner()
    async def getgoals(self, ctx):
        """
            Testing function with testgame.json
        """
        # to_remove = []
        # games_playing = True
        # log.debug(link)
        with open("/mnt/e/github/Trusty-cogs/hockey/testgame.json", "r") as infile:
            data = json.loads(infile.read())
        # log.debug(data)
        game = await Game.from_json(data)
        await game.check_game_state(self.bot)
        if (game.home_score + game.away_score) != 0:
            await game.check_team_goals(self.bot)
        all_teams = await self.config.teams()
        for team in await self.config.teams():
            if team["team_name"] in [game.home_team, game.away_team]:
                all_teams.remove(team)
                team["goal_id"] = {}
                team["game_state"] = "Null"
                team["game_start"] = ""
                team["period"] = 0
                all_teams.append(team)

        await self.config.teams.set(all_teams)
        await ctx.send("Done testing.")

    @hockeyset_commands.command(hidden=True)
    @checks.is_owner()
    async def pickems_tally(self, ctx):
        """
            Manually tally the leaderboard
        """
        await Pickems.tally_leaderboard(self.bot)
        await ctx.send(_("Leaderboard tallying complete."))

    @hockeyset_commands.command(hidden=True)
    @checks.is_owner()
    async def remove_old_pickems(self, ctx, year: int, month: int, day: int):
        """
            Remove pickems objects created before a specified date.
        """
        start = date(year, month, day)
        good_list = []
        for guild_id in await self.config.all_guilds():
            g = self.bot.get_guild(guild_id)
            pickems = [Pickems.from_json(p) for p in await self.config.guild(g).pickems()]
            for p in pickems:
                if p.game_start > start:
                    good_list.append(p)
            await self.config.guild(g).pickems.set([p.to_json() for p in good_list])
        await ctx.send(_("All old pickems objects deleted."))

    @hockeyset_commands.command(hidden=True)
    @checks.is_owner()
    async def check_pickem_winner(self, ctx, days: int = 1):
        """
            Manually check all pickems objects for winners

            `days` number of days to look back
        """
        days = days + 1
        now = datetime.now()
        for i in range(1, days):
            delta = timedelta(days=-i)
            check_day = now + delta
            games = await Game.get_games(None, check_day, check_day)
            for game in games:
                await Pickems.set_guild_pickem_winner(self.bot, game)
        await ctx.send(_("Pickems winners set."))

    @hockeyset_commands.command(hidden=True)
    @checks.is_owner()
    async def fix_all_pickems(self, ctx):
        """
            Fixes winner on all current pickems objects if possible
        """
        oldest = datetime.now()
        for guild_id, pickems in self.all_pickems.items():
            for name, p in pickems.items():
                if p.game_start < oldest:
                    oldest = p.game_start
        games = await Game.get_games(None, oldest, datetime.now())
        for game in games:
            await Pickems.set_guild_pickem_winner(self.bot, game)
        await ctx.send(_("All pickems winners set."))

    @gdc.command(hidden=True, name="test")
    @checks.is_owner()
    async def test_gdc(self, ctx):
        """
            Test checking for new game day channels
        """
        await GameDayChannels.check_new_gdc(self.bot)

    @hockeyset_commands.command()
    @checks.is_owner()
    async def teststandings(self, ctx):
        """
            Test the automatic standings function/manually update standings
        """
        try:
            await Standings.post_automatic_standings(self.bot)
        except Exception:
            log.debug("error testing standings page", exc_info=True)

    @hockeyset_commands.command()
    @checks.is_owner()
    async def cogstats(self, ctx):
        """
            Display current number of servers and channels
            the cog is storing in console
        """
        all_channels = await self.config.all_channels()
        all_guilds = await self.config.all_guilds()
        guild_list = {}
        for channels in all_channels.keys():
            channel = self.bot.get_channel(channels)
            if channel is None:
                log.debug(channels)
                continue
            if channel.guild.name not in guild_list:
                guild_list[channel.guild.name] = 1
            else:
                guild_list[channel.guild.name] += 1
        msg = "Servers:{}\nNumber of Channels: {}\nNumber of Servers: {}".format(
            guild_list, len(all_channels), len(all_guilds)
        )
        log.debug(msg)

    #######################################################################
    # Owner Only Commands Mostly for Testing

    @hockeyset_commands.command()
    @checks.is_owner()
    async def customemoji(self, ctx):
        """
            Set custom emojis for the bot to use

            Requires you to upload a .yaml file with
            emojis that the bot can see
            an example may be found
            [here](https://github.com/TrustyJAID/Trusty-cogs/blob/master/hockey/emoji.yaml)
            if no emoji is provided for a team the Other
            slot will be filled instead
            It's recommended to have an emoji for every team
            to utilize all features of the cog such as pickems
        """
        attachments = ctx.message.attachments
        if attachments == []:
            await ctx.send(_("Upload the .yaml file to use. Type `exit` to cancel."))
            msg = await self.wait_for_file(ctx)
            if msg is None:
                return
            try:
                await self.change_custom_emojis(msg.attachments)
            except InvalidFileError:
                await ctx.send(_("That file doesn't seem to be formatted correctly."))
                return
        else:
            try:
                await self.change_custom_emojis(attachments)
            except InvalidFileError:
                await ctx.send(_("That file doesn't seem to be formatted correctly."))
                return
        new_msg = "".join(("<:" + TEAMS[e]["emoji"] + ">") for e in TEAMS)
        await ctx.send(_("New emojis set to: ") + new_msg)
        await ctx.send("You should reload the cog for everything to work correctly.")

    @hockeyset_commands.command()
    @checks.is_owner()
    async def resetgames(self, ctx):
        """
            Resets the bots game data incase something goes wrong
        """
        all_teams = await self.config.teams()
        for team in await self.config.teams():
            all_teams.remove(team)
            team["goal_id"] = {}
            team["game_state"] = "Null"
            team["game_start"] = ""
            team["period"] = 0
            all_teams.append(team)

        await self.config.teams.set(all_teams)
        await ctx.send(_("Saved game data reset."))

    @gdc.command()
    @checks.is_owner()
    async def setcreated(self, ctx, created: bool):
        """
            Sets whether or not the game day channels have been created
        """
        await self.config.created_gdc.set(created)
        await ctx.send(_("created_gdc set to ") + str(created))

    @gdc.command()
    @checks.is_owner()
    async def cleargdc(self, ctx):
        """
            Checks for manually deleted channels from the GDC channel list
            and removes them
        """
        guild = ctx.message.guild
        good_channels = []
        for channels in await self.config.guild(guild).gdc():
            channel = self.bot.get_channel(channels)
            if channel is None:
                await self.config._clear_scope(Config.CHANNEL, str(channels))
                log.info("Removed the following channels" + str(channels))
                continue
            else:
                good_channels.append(channel.id)
        await self.config.guild(guild).gdc.set(good_channels)

    @hockeyset_commands.command()
    @checks.is_owner()
    async def clear_broken_channels(self, ctx):
        """
            Removes missing channels from the config
        """
        for channels in await self.config.all_channels():
            channel = self.bot.get_channel(channels)
            if channel is None:
                await self.config._clear_scope(Config.CHANNEL, str(channels))
                log.info("Removed the following channels" + str(channels))
                continue
            # if await self.config.channel(channel).to_delete():
            # await self.config._clear_scope(Config.CHANNEL, str(channels))
        await ctx.send(_("Broken channels removed"))

    @hockeyset_commands.command()
    @checks.is_owner()
    async def remove_broken_guild(self, ctx):
        """
            Removes a server that no longer exists on the bot
        """
        # all_guilds = await self.config.all_guilds()
        for guilds in await self.config.all_guilds():
            guild = self.bot.get_guild(guilds)
            if guild is None:
                await self.config._clear_scope(Config.GUILD, str(guilds))
            else:
                if not await self.config.guild(guild).create_channels():
                    await self.config.guild(guild).gdc.set([])

        await ctx.send(_("Saved servers the bot is no longer on have been removed."))

    @hockeyset_commands.command()
    @checks.is_owner()
    async def clear_weekly(self, ctx):
        """
            Clears the weekly tracker on the current servers pickems

            May not be necessary anymore
        """
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if leaderboard is None:
            leaderboard = {}
        for user in leaderboard:
            leaderboard[str(user)]["weekly"] = 0
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard)

    @hockey_commands.command(hidden=True)
    @checks.is_owner()
    async def lights(self, ctx):
        """
            Tests the philips Hue light integration
            This is hard coded at the moment with no plans to make work generally
            this will be safely ignored.
        """
        if LIGHTS_SET:
            hue = Oilers(self.bot)
            hue.goal_lights()
            print("done")
        else:
            return

    @hockeyset_commands.command(hidden=True)
    @checks.is_owner()
    async def testloop(self, ctx):
        """
            Toggle the test game loop
        """
        self.TEST_LOOP = not self.TEST_LOOP
        await ctx.send(_("Test loop set to ") + str(self.TEST_LOOP))

    @hockeyset_commands.command()
    @checks.is_owner()
    async def rempickem(self, ctx):
        """
            Clears the servers current pickems object list
        """
        await self.config.guild(ctx.guild).pickems.set([])
        await ctx.send(_("All pickems removed on this server."))

    @hockeyset_commands.command()
    @checks.is_owner()
    async def remleaderboard(self, ctx):
        """
            Clears the servers pickems leaderboard
        """
        await self.config.guild(ctx.guild).leaderboard.set({})
        await ctx.send(_("Server leaderboard reset."))

    async def save_pickems_unload(self):
        for guild_id, pickems in self.all_pickems.items():
            guild_obj = discord.Object(id=int(guild_id))
            await self.config.guild(guild_obj).pickems.set(
                {name: p.to_json() for name, p in pickems.items()}
            )

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        self.bot.loop.create_task(self.save_pickems_unload())
        if getattr(self, "loop", None) is not None:
            self.loop.cancel()
        if getattr(self, "pickems_save_loop", None) is not None:
            log.debug("canceling pickems save loop")
            self.save_pickems = False
            self.pickems_save_loop.cancel()

    __del__ = cog_unload
    __unload = cog_unload
