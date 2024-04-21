import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import pagify

from .abc import HockeyMixin
from .constants import TEAMS
from .errors import InvalidFileError
from .game import Game
from .helper import get_channel_obj
from .menu import BaseMenu, SimplePages
from .pickems import Pickems
from .standings import Standings

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.hockey")


class HockeyDev(HockeyMixin):
    """
    All the commands grouped under `[p]hockeydev`
    """

    #######################################################################
    # Owner Only Commands Mostly for Testing and debuggings               #
    #######################################################################

    @commands.group(aliases=["nhldev"], with_app_command=False)
    @commands.is_owner()
    async def hockeydev(self, ctx: commands.Context) -> None:
        """
        Secret dev only commands for Hockey

        Most of these probably shouldn't be run unless you
        know exactly what they do.
        """
        pass

    @hockeydev.group(name="cleanup")
    async def cleanup(self, ctx: commands.Context):
        """
        Cleanup saved channels/guilds that no longer exist.
        """

    @cleanup.command(name="guilds")
    async def cleanup_guilds(self, ctx: commands.Context):
        """
        Check for missing guilds and clear their data
        """
        all_guilds = await self.config.all_guilds()
        for guild_id in all_guilds:
            if not self.bot.get_guild(guild_id):
                await self.config.guild_from_id(guild_id).clear()
        await ctx.tick(message="Done.")

    @cleanup.command(name="channels")
    async def cleanup_channels(self, ctx: commands.Context):
        """
        Check for missing guilds and clear their data
        """
        all_channels = await self.config.all_channels()
        for channel_id, data in all_channels.items():
            channel = await get_channel_obj(self.bot, channel_id, data)
            if channel is None:
                await self.config.channel_from_id(channel_id).clear()
        await ctx.tick(message="Done.")

    @hockeydev.command(name="errorchannel")
    async def set_loop_error_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Specify an error channel for the hockey loop.
        """
        if not channel.permissions_for(ctx.me).send_messages:
            await ctx.send(
                "I need permission to send messages in {channel}".format(channel=channel.mention)
            )
            return
        await self.config.loop_error_channel.set(channel.id)
        await self.config.loop_error_guild.set(channel.guild.id)
        await ctx.send(
            "I will attempt to send error messages in {channel}.".format(channel=channel.mention)
        )

    @hockeydev.command(with_app_command=False)
    async def getgoals(self, ctx: commands.Context) -> None:
        """
        Testing function with testgame.json
        """
        # to_remove = []
        # games_playing = True
        # log.debug(link)
        with open("/mnt/e/github/Trusty-cogs/hockey/testgame.json", "r") as infile:
            data = json.loads(infile.read())
        log.verbose("getgoals testgame.json data: %s", data)
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

    @hockeydev.group(name="pickems", with_app_command=False)
    async def pickems_dev_commands(self, ctx: commands.Context) -> None:
        """
        Dev commands for testing and building pickems
        """
        pass

    @pickems_dev_commands.command(name="backup")
    async def backup_pickems(self, ctx: commands.Context):
        """
        Backup Pickems
        """
        data = await self.pickems_config.all_guilds()
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        save = cog_data_path(self).joinpath(f"Pickems-Backup-{date_str}.json")
        with save.open("w") as outfile:
            outfile.write(json.dumps(data))
        await ctx.send(f"I have backed up pickems data to `{save}`.")

    @pickems_dev_commands.command(name="resetweekly", with_app_command=False)
    async def reset_weekly_pickems_data(self, ctx: commands.Context) -> None:
        """
        Force reset all pickems data for the week
        """
        await self.reset_weekly()
        guilds_to_make_new_pickems = []
        for guild_id in await self.pickems_config.all_guilds():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            if await self.pickems_config.guild(guild).pickems_channel():
                guilds_to_make_new_pickems.append(guild)
        await self.create_weekly_pickems_pages(guilds_to_make_new_pickems)
        await ctx.send("Finished resetting all pickems data.")

    @pickems_dev_commands.command(name="announce", with_app_command=False)
    async def announce_pickems(self, ctx: commands.Context, *, message: str) -> None:
        """
        Announce a message in all setup pickems channels

        This is only useful if there was an error and you want to
        announce to people that their vote might not have counted.
        """
        all_guilds = await self.pickems_config.all_guilds()
        for guild_id, data in all_guilds.items():
            g = self.bot.get_guild(guild_id)
            if g is None:
                continue
            if data["pickems_channels"]:
                for channel_id in data["pickems_channels"]:
                    chan = g.get_channel(channel_id)
                    if chan:
                        try:
                            await chan.send(message)
                        except Exception:
                            pass
        await ctx.send(_("Message announced in pickems channels."))

    @pickems_dev_commands.command(name="toggle")
    async def pickems_dev_toggle(self, ctx: commands.Context):
        """
        Toggle the ability for users to setup pickems on their servers
        """
        allowed_only = not await self.pickems_config.only_allowed()
        await self.pickems_config.only_allowed.set(allowed_only)
        if allowed_only:
            msg = _("Pickems will only be enabled for allowed guilds.")
        else:
            msg = _("Pickems will be enabled for everyone.")

        await ctx.send(msg)

    @pickems_dev_commands.command(name="msg")
    async def pickems_dev_msg(self, ctx: commands.Context, *, msg: Optional[str] = None):
        """
        Set the message sent to users attempting to add pickems when it
        is disabled.
        """
        if msg and len(msg) > 2000:
            await ctx.send(_("Your message needs to be fewer than 2000 characters."))
            return
        await self.pickems_config.unavailable_msg.set(msg)
        await ctx.send(_("Pickems Unavailable message set to:\n{msg}").format(msg=msg))

    @pickems_dev_commands.command(name="addguild")
    async def pickems_add_guild(self, ctx: commands.Context, guild_id: int):
        """
        Add a guild to the pickems allowed guilds
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await ctx.send(_("I am not currently in {guild_id}.").format(guild_id=guild_id))
            return
        async with self.pickems_config.allowed_guilds() as allowed:
            if guild_id not in allowed:
                allowed.append(guild_id)
        await ctx.send(_("{guild} added to pickems allowed guilds.").format(guild=guild.name))

    @pickems_dev_commands.command(name="remguild")
    async def pickems_remove_guild(self, ctx: commands.Context, guild_id: int):
        """
        Remove a guild from the pickems allowed guilds
        """
        async with self.pickems_config.allowed_guilds() as allowed:
            if guild_id in allowed:
                allowed.remove(guild_id)
        await self.pickems_config.guild_from_id(guild_id).pickems_channel.clear()
        await self.pickems_config.guild_from_id(guild_id).pickems_category.clear()
        await ctx.send(
            _("Guild {guild_id} removed from the pickems allowed guilds.").format(
                guild_id=guild_id
            )
        )

    @pickems_dev_commands.command(name="fix")
    async def fix_pickems_views(self, ctx: commands.Context):
        """
        For some reason reloading doesn't re-add the views to the bots persistent
        views list. This command does that if for whatever reason after reloading
        the cog the views are not registering votes.
        """
        for guild_id, pickems in self.all_pickems.items():
            for name, pickem in pickems.items():
                self.bot.add_view(pickem)
        await ctx.send(_("Added all pickems views to the bot."))

    @pickems_dev_commands.command(name="list")
    async def list_pickems_guilds(self, ctx: commands.Context):
        """
        List all guilds allowed to have pickems
        """
        guild_ids = await self.pickems_config.allowed_guilds()
        guilds = []
        for guild_id in guild_ids:
            g = self.bot.get_guild(guild_id)
            if g is not None:
                guilds.append(f"{g.id} - {g.name}")
            else:
                guilds.append(f"{guild_id}")
        msg = "\n".join(g for g in guilds)
        for page in pagify(msg):
            await ctx.send(page)

    @pickems_dev_commands.command(name="make", with_app_command=False)
    async def make_fake_pickems(self, ctx: commands.Context) -> None:
        """
        Testing function with testgame.json
        """
        # to_remove = []
        # games_playing = True
        # log.debug(link)
        with open("/mnt/e/github/Trusty-cogs/hockey/testgame.json", "r") as infile:
            data = json.loads(infile.read())
        log.verbose("make_fake_pickems - testgame.json: %s", data)
        game = await Game.from_json(data)
        fake_pickem = await self.get_pickem_object(ctx.guild, game)
        msg = await self.make_pickems_msg(ctx.guild, game)
        msg = await ctx.send(msg, view=fake_pickem)
        fake_pickem.messages.append(f"{ctx.channel.id}-{msg.id}")
        fake_pickem._should_save = True

    @pickems_dev_commands.command(name="disable", with_app_command=False)
    async def disable_fake_pickems(self, ctx: commands.Context) -> None:
        """
        Test final functions for pickems
        """
        with open("/mnt/e/github/Trusty-cogs/hockey/testgame.json", "r") as infile:
            data = json.loads(infile.read())
        log.verbose("disable_fake_pickems - testgame.json: %s", data)
        game = await Game.from_json(data)
        await self.disable_pickems_buttons(game)

    @pickems_dev_commands.command(name="final", with_app_command=False)
    async def finalize_fake_pickems(self, ctx: commands.Context) -> None:
        """
        Test a game final for pickems
        """
        with open("/mnt/e/github/Trusty-cogs/hockey/testgame.json", "r") as infile:
            data = json.loads(infile.read())
        log.verbose("finalize_fake_pickems - testgame.json: %s", data)
        game = await Game.from_json(data)
        await self.set_guild_pickem_winner(game)

    @pickems_dev_commands.command(name="tally", with_app_command=False)
    async def pickems_tally(self, ctx: commands.Context) -> None:
        """
        Manually tally the leaderboard for all servers
        """
        async with ctx.typing():
            try:
                await self.tally_leaderboard()
            except Exception:
                log.exception("Error manually tallying pickems Leaderboard.")
                await ctx.send(
                    _(
                        "There was an error tallying pickems leaerboard. Check the console fore errors."
                    )
                )
                return
        await ctx.send(_("Leaderboard tallying complete."))

    @pickems_dev_commands.command(name="removeold", with_app_command=False)
    async def remove_old_pickems(
        self, ctx: commands.Context, year: int, month: int, day: int
    ) -> None:
        """
        Remove pickems objects created before a specified date.
        """
        async with ctx.typing():
            start = date(year, month, day)
            good_list = {}
            for guild_id in await self.pickems_config.all_guilds():
                g = self.bot.get_guild(guild_id)
                pickems = [
                    Pickems.from_json(p) for p in await self.pickems_config.guild(g).pickems()
                ]
                for p in pickems:
                    if p.game_start > start:
                        good_list[p.name] = p.to_json()
                await self.pickems_config.guild(g).pickems.set(good_list)
        await ctx.send(_("All old pickems objects deleted."))

    @pickems_dev_commands.command(name="checkwinner", with_app_command=False)
    async def check_pickem_winner(self, ctx: commands.Context, days: int = 1) -> None:
        """
        Manually check all pickems objects for winners

        `days` number of days to look back
        """
        async with ctx.typing():
            days = days + 1
            now = datetime.now(timezone.utc)
            for i in range(1, days):
                delta = timedelta(days=-i)
                check_day = now + delta
                games = await Game.get_games(None, check_day, check_day)
                for game in games:
                    await self.set_guild_pickem_winner(game)
        await ctx.send(_("Pickems winners set."))

    @pickems_dev_commands.command(name="fixall", with_app_command=False)
    async def fix_all_pickems(self, ctx: commands.Context) -> None:
        """
        Fixes winner on all current pickems objects if possible
        """
        oldest = datetime.now(timezone.utc)
        for guild_id, pickems in self.all_pickems.items():
            for name, p in pickems.items():
                if p.game_start < oldest:
                    oldest = p.game_start
        games = await Game.get_games(None, oldest, datetime.now(timezone.utc))
        for game in games:
            await self.set_guild_pickem_winner(game)
        await ctx.send(_("All pickems winners set."))

    @hockeydev.command(with_app_command=False)
    async def teststandings(self, ctx: commands.Context) -> None:
        """
        Test the automatic standings function/manually update standings
        """
        async with ctx.typing():
            try:
                await Standings.post_automatic_standings(self.bot)
            except Exception:
                log.debug("error testing standings page", exc_info=True)
        await ctx.send(_("Finished fixing all standings messages."))

    @hockeydev.command(with_app_command=False)
    @commands.bot_has_permissions(embed_links=True)
    async def cogstats(self, ctx: commands.Context) -> None:
        """
        Display current number of servers and channels
        the cog is storing in console
        """
        async with ctx.typing():
            all_channels = await self.config.all_channels()
            all_pickems = await self.pickems_config.all_guilds()
            guild_list: dict = {
                "guilds": [],
                "goal_updates": {"total": 0},
                "gdc": {"total": 0},
                "standings": {"total": 0},
                "pickems": {"voters": [], "channels": 0, "waiting_pickems": []},
            }
            for guild in self.bot.guilds:
                hockey_data = await self.config.guild(guild).all()
                if gdc := hockey_data.get("gdc"):
                    if guild.id not in guild_list["guilds"]:
                        guild_list["guilds"].append(guild.id)
                    for channel_id in gdc:
                        if guild.get_channel(channel_id):
                            guild_list["gdc"]["total"] += 1
                    if gdc_team := hockey_data.get("gdc_team"):
                        if gdc_team not in guild_list["gdc"]:
                            guild_list["gdc"][gdc_team] = 0
                        guild_list["gdc"][gdc_team] += 1
                if hockey_data.get("post_standings"):
                    if guild.id not in guild_list["guilds"]:
                        guild_list["guilds"].append(guild.id)
                    guild_list["standings"]["total"] += 1
                    if standings := hockey_data.get("standings_type"):
                        if standings not in guild_list["standings"]:
                            guild_list["standings"][standings] = 0
                        guild_list["standings"][standings] += 1
            async for channel_id, data in AsyncIter(all_channels.items()):
                channel = await get_channel_obj(self.bot, channel_id, data)
                if not channel:
                    continue
                if channel.guild.id not in guild_list["guilds"]:
                    guild_list["guilds"].append(channel.guild.id)
                guild_list["goal_updates"]["total"] += 1
                for team in data["team"]:
                    if team not in guild_list["goal_updates"]:
                        guild_list["goal_updates"][team] = 0
                    guild_list["goal_updates"][team] += 1
            async for guild_id, data in AsyncIter(all_pickems.items()):
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                if guild.id not in guild_list["guilds"]:
                    guild_list["guilds"].append(guild.id)
                if leaderboard := data.get("leaderboard", {}):
                    guild_list["pickems"]["voters"] += list(leaderboard.keys())
                if channels := data.get("pickems_channels"):
                    for channel_id in channels:
                        if guild.get_channel(channel_id):
                            guild_list["pickems"]["channels"] += 1
                if pickems := data.get("pickems", {}):
                    guild_list["pickems"]["waiting_pickems"] += pickems.keys()

            msg = ""
            for key, value in guild_list.items():
                if key == "guilds":
                    msg += f"__Total Guilds:__ **{len(value)}**\n"
                if key == "pickems":
                    msg += "**Pickems**\n"
                    for name, count in value.items():
                        if name == "voters":
                            msg += f"__Total Pickems Voters:__ **{len(count)}**\n"
                            msg += f"__Total Unique Pickems Voters:__ **{len(set(count))}**\n"
                        if name == "waiting_pickems":
                            msg += f"__Total Waiting Pickems:__ **{len(set(count))}**\n"
                        if name == "channels":
                            msg += f"__Total Pickems Channels:__ **{count}**\n"
                    msg += "\n"
                if key == "goal_updates":
                    for name, count in value.items():
                        msg += f"__{str(name).title()} Goal Update Channels:__ **{count}**\n"
                    msg += "\n"
                if key == "gdc":
                    for name, count in value.items():
                        msg += f"__{str(name).title()} GDC:__ **{count}**\n"
                    msg += "\n"
                if key == "standings":
                    for name, count in value.items():
                        msg += f"__{str(name).title()} Standings Updates:__ **{count}**\n"
                    msg += "\n"
            embed_list = []
            for pages in pagify(msg, page_length=6000):
                embed = discord.Embed(title=_("Hockey Statistics"))
                count = 0
                for page in pagify(pages, page_length=1024):
                    if count <= 1:
                        if embed.description:
                            embed.description += page
                        else:
                            embed.description = page
                        count += 1
                        continue
                    embed.add_field(name=_("Stats Continued"), value=page)
                embed_list.append(embed)
        await BaseMenu(
            source=SimplePages(pages=embed_list),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @hockeydev.command(with_app_command=False)
    async def customemoji(self, ctx: commands.Context) -> None:
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
        msg = _("New emojis set to: ") + new_msg
        for page in pagify(msg):
            await ctx.send(page)
        await ctx.send("You should reload the cog for everything to work correctly.")

    @hockeydev.command(with_app_command=False)
    async def resetgames(self, ctx: commands.Context) -> None:
        """
        Resets the bots game data incase something goes wrong
        """
        await self.config.teams.clear()
        await ctx.send(_("Saved game data reset."))

    @hockeydev.command(with_app_command=False)
    async def setcreated(self, ctx: commands.Context, created: bool) -> None:
        """
        Sets whether or not the game day channels have been created
        """
        await self.config.created_gdc.set(created)
        await ctx.send(_("created_gdc set to ") + str(created))

    @hockeydev.command(with_app_command=False)
    async def cleargdc(self, ctx: commands.Context) -> None:
        """
        Checks for manually deleted channels from the GDC channel list
        and removes them
        """
        guild = ctx.message.guild
        good_channels = []
        gdc_chans = await self.config.guild(guild).gdc_chans()
        for channel_id in gdc_chans.values():
            channel = guild.get_channel(channel_id)
            if channel is None:
                await self.config.channel_from_id(channel_id).clear()
                log.info("Removed the following channels %s", channel_id)
                continue
            else:
                good_channels.append(channel.id)
        await self.config.guild(guild).gdc.set(good_channels)
        await ctx.tick()

    @hockeydev.command(name="clearbrokenchannels", with_app_command=False)
    async def clear_broken_channels(self, ctx: commands.Context) -> None:
        """
        Removes missing channels from the config
        """
        all_channels = await self.config.all_channels()
        for channel_id, data in all_channels.items():
            if not data["guild_id"]:
                channel = self.bot.get_channel(channel_id)
                guild = channel.guild
                await self.config.channel(channel).guild_id.set(guild.id)
            else:
                guild = self.bot.get_guild(data["guild_id"])
                if not guild:
                    await self.config.channel_from_id(channel_id).clear()
                    await self.config.guild_from_id(int(data["guild_id"])).clear()
                    log.info("Removed the following channels %s", channel_id)
                    continue
                channel = guild.get_channel

            if channel is None:
                await self.config.channel_from_id(channel_id).clear()
                log.info("Removed the following channels %s", channel_id)
                continue
            # if await self.config.channel(channel).to_delete():
            # await self.config._clear_scope(Config.CHANNEL, str(channels))
        await ctx.send(_("Broken channels removed"))

    @hockeydev.command(with_app_command=False)
    async def remove_broken_guild(self, ctx: commands.Context) -> None:
        """
        Removes a server that no longer exists on the bot
        """
        # all_guilds = await self.config.all_guilds()
        for guild_id in await self.config.all_guilds():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await self.config.guild_from_id(int(guild_id)).clear()
            else:
                if not await self.config.guild(guild).create_channels():
                    await self.config.guild(guild).gdc.clear()

        await ctx.send(_("Saved servers the bot is no longer on have been removed."))

    @hockeydev.command(hidden=True, with_app_command=False)
    async def testloop(self, ctx: commands.Context) -> None:
        """
        Toggle the test game loop
        """
        self.TEST_LOOP = not self.TEST_LOOP
        await ctx.send(_("Test loop set to ") + str(self.TEST_LOOP))

    @hockeydev.command(with_app_command=False)
    async def clear_seasonal_leaderboard_all(self, ctx: commands.Context) -> None:
        """
        Clears the bots seasonal pickems leaderboard
        """
        for guild_id in await self.pickems_config.all_guilds():
            await self.pickems_config.guild_from_id(int(guild_id)).leaderboard.clear()
        await ctx.send(_("Seasonal pickems leaderboards cleared."))
