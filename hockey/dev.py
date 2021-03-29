import asyncio
import json
import logging
from datetime import date, datetime, timedelta

from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify

from .abc import MixinMeta
from .constants import TEAMS
from .errors import InvalidFileError
from .game import Game
from .pickems import Pickems
from .standings import Standings

try:
    from .oilers import Oilers

    LIGHTS_SET = True
except ImportError:
    LIGHTS_SET = False
    pass

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.hockey")


class HockeyDev(MixinMeta):
    """
    All the commands grouped under `[p]hockeydev`
    """

    #######################################################################
    # Owner Only Commands Mostly for Testing and debuggings               #
    #######################################################################

    @commands.group(aliases=["nhldev"])
    @checks.is_owner()
    async def hockeydev(self, ctx: commands.Context):
        """
        Secret dev only commands for Hockey

        Most of these probably shouldn't be run unless you
        know exactly what they do.
        """
        pass

    @hockeydev.command(name="resetpickemsweekly")
    async def reset_weekly_pickems_data(self, ctx: commands.Context):
        """
        Force reset all pickems data for the week
        """
        await self.reset_weekly()
        guilds_to_make_new_pickems = []
        for guild_id in await self.pickems_config.all_guilds():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            if await self.pickems_config.guild(guild).pickems_category():
                guilds_to_make_new_pickems.append(guild)
        await self.create_weekly_pickems_pages(guilds_to_make_new_pickems, Game)
        await ctx.send("Finished resetting all pickems data.")

    @hockeydev.command()
    async def getgoals(self, ctx: commands.Context):
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

    @hockeydev.command()
    async def pickems_tally(self, ctx: commands.Context):
        """
        Manually tally the leaderboard
        """
        await self.tally_leaderboard()
        await ctx.send(_("Leaderboard tallying complete."))

    @hockeydev.command()
    async def remove_old_pickems(self, ctx: commands.Context, year: int, month: int, day: int):
        """
        Remove pickems objects created before a specified date.
        """
        start = date(year, month, day)
        good_list = {}
        for guild_id in await self.pickems_config.all_guilds():
            g = self.bot.get_guild(guild_id)
            pickems = [Pickems.from_json(p) for p in await self.pickems_config.guild(g).pickems()]
            for p in pickems:
                if p.game_start > start:
                    good_list[p.name] = p.to_json()
            await self.pickems_config.guild(g).pickems.set(good_list)
        await ctx.send(_("All old pickems objects deleted."))

    @hockeydev.command()
    async def check_pickem_winner(self, ctx: commands.Context, days: int = 1):
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
                await self.set_guild_pickem_winner(game)
        await ctx.send(_("Pickems winners set."))

    @hockeydev.command()
    async def fix_all_pickems(self, ctx: commands.Context):
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
            await self.set_guild_pickem_winner(game)
        await ctx.send(_("All pickems winners set."))

    @hockeydev.command()
    async def teststandings(self, ctx: commands.Context):
        """
        Test the automatic standings function/manually update standings
        """
        async with ctx.typing():
            try:
                await Standings.post_automatic_standings(self.bot)
            except Exception:
                log.debug("error testing standings page", exc_info=True)
        await ctx.send(_("Finished fixing all standings messages."))

    @hockeydev.command()
    async def cogstats(self, ctx: commands.Context):
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
        msg = f"Number of Servers: {len(all_guilds)}\nNumber of Channels: {len(all_channels)}"
        await ctx.send(msg)

    @hockeydev.command()
    async def customemoji(self, ctx: commands.Context):
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

    @hockeydev.command()
    async def resetgames(self, ctx: commands.Context):
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

    @hockeydev.command()
    async def setcreated(self, ctx: commands.Context, created: bool):
        """
        Sets whether or not the game day channels have been created
        """
        await self.config.created_gdc.set(created)
        await ctx.send(_("created_gdc set to ") + str(created))

    @hockeydev.command()
    async def cleargdc(self, ctx: commands.Context):
        """
        Checks for manually deleted channels from the GDC channel list
        and removes them
        """
        guild = ctx.message.guild
        good_channels = []
        for channel_id in await self.config.guild(guild).gdc():
            channel = guild.get_channel(channel_id)
            if channel is None:
                await self.config.channel_from_id(channel_id).clear()
                log.info(f"Removed the following channels {channel_id}")
                continue
            else:
                good_channels.append(channel.id)
        await self.config.guild(guild).gdc.set(good_channels)
        await ctx.tick()

    @hockeydev.command()
    async def clear_broken_channels(self, ctx: commands.Context):
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
                    await self.config.guild_from_id(data["guild_id"]).clear()
                    log.info(f"Removed the following channels {channel_id}")
                    continue
                channel = guild.get_channel

            if channel is None:
                await self.config.channel_from_id(channel_id).clear()
                log.info(f"Removed the following channels {channel_id}")
                continue
            # if await self.config.channel(channel).to_delete():
            # await self.config._clear_scope(Config.CHANNEL, str(channels))
        await ctx.send(_("Broken channels removed"))

    @hockeydev.command()
    async def remove_broken_guild(self, ctx: commands.Context):
        """
        Removes a server that no longer exists on the bot
        """
        # all_guilds = await self.config.all_guilds()
        for guild_id in await self.config.all_guilds():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await self.config.guild_from_id(guild_id).clear()
            else:
                if not await self.config.guild(guild).create_channels():
                    await self.config.guild(guild).gdc.clear()

        await ctx.send(_("Saved servers the bot is no longer on have been removed."))

    @hockeydev.command(hidden=True)
    async def lights(self, ctx: commands.Context):
        """
        Tests the philips Hue light integration
        This is hard coded at the moment with no plans to make work generally
        this will be safely ignored.
        """
        if LIGHTS_SET:
            hue = Oilers(self.bot)
            hue.goal_lights()
            print("done")
        await ctx.tick()

    @hockeydev.command(hidden=True)
    async def testloop(self, ctx: commands.Context):
        """
        Toggle the test game loop
        """
        self.TEST_LOOP = not self.TEST_LOOP
        await ctx.send(_("Test loop set to ") + str(self.TEST_LOOP))

    @hockeydev.command()
    async def clear_seasonal_leaderboard_all(self, ctx: commands.Context):
        """
        Clears the bots seasonal pickems leaderboard
        """
        for guild_id in await self.pickems_config.all_guilds():
            await self.config.guild_from_id(guild_id).leaderboard.clear()
        await ctx.send(_("Seasonal pickems leaderboards cleared."))
