from datetime import datetime, timedelta, timezone
from typing import Dict, Literal, Optional

import aiohttp
import discord
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

from .menus import BaseMenu, GEChartPages, GESinglePages
from .profile import (
    Activities,
    Activity,
    APIError,
    OSRSProfile,
    PlayerDetails,
    PrivateProfileError,
    Profile,
)
from .tms import TMSTransformer, TravellingMerchant
from .viswax import RuneGoldberg
from .wikiapi import GameEnum, WikiAPI, WikiAPIError
from .wilderness import WildernessFlashEvents

log = getLogger("red.trusty-cogs.runescape")


class Runescape(commands.Cog):
    """
    Display Runescape account info
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.5.2"

    def __init__(self, bot):
        self.bot: Red = bot
        self.config: Config = Config.get_conf(self, 1845134845412)
        self.config.register_user(rsn=None, osrsn=None)
        self.config.register_global(metrics={})
        self.metrics: Dict[str, Activities] = {}
        self.check_new_metrics.start()
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": f"Red-DiscordBot Trusty-cogs on {self.bot.user}"}
        )
        self.wiki_api = WikiAPI(session=self.session)
        self._repo = ""
        self._commit = ""

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\nCog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def cog_load(self):
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "runescape":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def cog_unload(self):
        self.check_new_metrics.cancel()
        await self.session.close()

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    @tasks.loop(seconds=180)
    async def check_new_metrics(self):
        for username, activities in self.metrics.items():
            try:
                data = await Profile.get(username, 20, session=self.session)
            except Exception:
                log.exception("Error pulling profile info for %s", username)
                continue
            for activity in reversed(data.activities):
                if activity.id not in activities.posted_activities:
                    await self.post_activity(data, activities.channels, activity)
                    activities.last_timestamp = int(activity.date.timestamp())
                    activities.last_id = activity.id
                    activities.posted_activities.append(activity.id)
                    async with self.config.metrics() as metrics:
                        metrics[username] = activities.to_json()

    async def post_activity(
        self, profile: Profile, channels: Dict[str, int], activity: Activity
    ) -> None:
        embed = activity.embed(profile)
        text = activity.format_text(profile)

        for channel_id, guild_id in channels.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel or isinstance(channel, (discord.ForumChannel, discord.CategoryChannel)):
                continue
            if not channel.permissions_for(guild.me).send_messages:
                continue
            if channel.permissions_for(guild.me).embed_links:
                await channel.send(embed=embed)
            else:
                await channel.send(text)

    @check_new_metrics.before_loop
    async def before_checking_metrics(self):
        await self.bot.wait_until_red_ready()
        metrics = await self.config.metrics()
        for username, data in metrics.items():
            self.metrics[username] = Activities(**data)

    @check_new_metrics.after_loop
    async def after_checking_metrics(self):
        if self.check_new_metrics.is_being_cancelled():
            async with self.config.metrics() as metrics:
                for username, activities in self.metrics.items():
                    metrics[username] = activities.to_json()

    @commands.hybrid_group(name="runescape", aliases=["rs"])
    async def runescape(self, ctx: commands.Context):
        """Search for a user account or profile"""
        pass

    @runescape.command(name="wiki")
    async def runescape_wiki(self, ctx: commands.Context, *, search: str):
        """Look for something on the runescape Wiki."""
        base_url = "https://runescape.wiki/w/?curid="
        async with ctx.typing():
            try:
                data = await self.wiki_api.search(GameEnum.runescape, search)
            except WikiAPIError as e:
                log.debug(e)
                await ctx.send(
                    f"I could not find information about `{search}` on the Runescape Wiki."
                )
                return
            msg = f"Runescape Wiki Results for `{search}`:\n"
            for _search in data["query"]["search"]:
                page_id = _search["pageid"]
                title = _search["title"]
                msg += f"[{title}]({base_url}{page_id})\n"
        await ctx.maybe_send_embed(msg)

    @runescape.command(name="vis", aliases=["viswax"])
    async def runescape_viswax(self, ctx: commands.Context):
        """
        Get the current combinations for vis wax

        https://runescape.wiki/w/Rune_Goldberg_Machine
        """
        await ctx.typing()
        rgb = RuneGoldberg()
        if await ctx.embed_requested():
            em = rgb.embed()
            await ctx.send(embed=em)
        else:
            await ctx.send(str(rgb))

    @runescape.command(name="tms", aliases=["merchant"])
    async def runescape_merchant(self, ctx: commands.Context, item: Optional[TMSTransformer]):
        """
        Get the current Travelling Merchant items

        https://runescape.wiki/w/Travelling_Merchant's_Shop
        - `[item]` if provided can list the next 5 times that item appears.
        """
        await ctx.typing()
        if item is None:
            tms = TravellingMerchant()
            if await ctx.embed_requested():
                embeds = tms.embeds()
                await ctx.send(embeds=embeds)
            else:
                await ctx.send(str(tms))
        else:
            tms = await TravellingMerchant.find_next(item, 5)
            msg = f"Next 5 {item} at the Travelling Merchant's Shop\n"
            msg += "\n".join(i.list_items() for i in tms)
            if await ctx.embed_requested():
                em = discord.Embed(
                    title="Travelling Merchant's Shop",
                    description=msg,
                    url="https://runescape.wiki/w/Travelling_Merchant's_Shop",
                )
                em.set_thumbnail(url=item.image_url)
                await ctx.send(embed=em)
            else:
                await ctx.send(msg)

    @runescape.command(name="nemiforest", aliases=["nemi", "forest"])
    async def runescape_nemiforest(self, ctx: commands.Context):
        """Display an image of a Nemi Forest instance with all nine nodes."""
        async with ctx.typing():
            subreddit_url = "https://api.reddit.com/r/nemiforest/new"
            params = {
                "limit": 1,
            }

            async with self.session.get(subreddit_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(
                        "I could not find any Nemi Forest instance. Reddit is probably down."
                    )
                    return

            reddit_icon_url = "https://www.redditinc.com/assets/images/site/reddit-logo.png"
            latest_post: Dict = data["data"]["children"][0]["data"]
            post_author: str = latest_post["author"]
            post_flair = latest_post["link_flair_text"]
            post_title: str = (
                latest_post["title"] if not post_flair else f"[Depleted] " + latest_post["title"]
            )
            post_url: str = latest_post["url"]
            post_time = int(latest_post["created_utc"])

            embed_color = await ctx.embed_color()
            embed = discord.Embed(
                title=post_title, description=f"<t:{post_time}:R>", color=embed_color
            )
            embed.set_image(url=post_url)
            embed.set_footer(
                text=f"Instance provided by {post_author} via r/NemiForest",
                icon_url=reddit_icon_url,
            )
        await ctx.send(embed=embed)

    @runescape.command(name="ge")
    @commands.bot_has_permissions(embed_links=True)
    async def runescape_ge(self, ctx: commands.Context, *, search: str):
        """Look for something on the runescape Grand Exchange.

        You can lookup multiple items at once by separating them with `|`
        e.g. `[p]rs ge bond|fractured staff of armadyl`
        """
        async with ctx.typing():
            try:
                if len(search.split("|")) > 1:
                    data = await self.wiki_api.latest(game=GameEnum.runescape, name=search)
                    source = GESinglePages(data, self.wiki_api)
                else:
                    data = await self.wiki_api.last90d(game=GameEnum.runescape, name=search)
                    source = GEChartPages([data], self.wiki_api)
            except WikiAPIError as e:
                await ctx.send(e)
                return
        await BaseMenu(source, self).start(ctx)

    @runescape.group(name="set")
    async def runescape_set(self, ctx: commands.Context) -> None:
        """
        Set various runescape cog settings
        """
        pass

    @runescape_set.command(name="metrics", with_app_command=False)
    @commands.mod_or_permissions(manage_channels=True)
    async def runescape_set_metrics(
        self, ctx: commands.Context, runescape_name: str, channel: discord.TextChannel
    ) -> None:
        """
        Set a channel for automatic RuneMetrics updates

        `<runescape_name>` The Runescape Name of the account you want to follow
        `<channel>` The channel where updates should be posted
        """
        async with ctx.typing():
            data = await Profile.get(runescape_name, 20, session=self.session)
            if data == "NO PROFILE":
                await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
                return
            if runescape_name.lower() not in self.metrics:
                activities = Activities(
                    channels={str(channel.id): channel.guild.id},
                    last_id=None,
                    username=runescape_name.lower(),
                    last_timestamp=0,
                    posted_activities=[],
                )
                self.metrics[runescape_name.lower()] = activities
            else:
                self.metrics[runescape_name.lower()].channels[str(channel.id)] = channel.guild.id
        async with self.config.metrics() as metrics:
            metrics[runescape_name.lower()] = self.metrics[runescape_name.lower()].to_json()
        await ctx.send(
            f"{runescape_name} will now have RuneMetrics updates posted in {channel.mention}"
        )

    @runescape_set.command(name="remove", aliases=["delete", "del", "rem"], with_app_command=False)
    @commands.mod_or_permissions(manage_channels=True)
    async def runescape_remove_metrics(
        self, ctx: commands.Context, runescape_name: str, channel: discord.TextChannel
    ) -> None:
        """
        Remove a channel from automatic RuneMetrics updates

        `<runescape_name>` The Runescape Name of the account you are following
        `<channel>` The channel where updates should stop being posted
        """
        async with ctx.typing():
            data = await Profile.get(runescape_name, 20, session=self.session)
        if data == "NO PROFILE":
            await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
            return
        if runescape_name.lower() not in self.metrics:
            await ctx.send("The account {} is not being followed!".format(runescape_name))
        else:
            if str(channel.id) in self.metrics[runescape_name.lower()].channels:
                del self.metrics[runescape_name.lower()].channels[str(channel.id)]
                async with self.config.metrics() as metrics:
                    metrics[runescape_name.lower()] = self.metrics[
                        runescape_name.lower()
                    ].to_json()
                await ctx.send(
                    "The account {} will no longer have rune metrics updates in {}".format(
                        runescape_name, channel.mention
                    )
                )
                if len(self.metrics[runescape_name.lower()].channels) == 0:
                    del self.metrics[runescape_name.lower()]
                    async with self.config.metrics() as metrics:
                        del metrics[runescape_name.lower()]
            else:
                await ctx.send(
                    "The account {} is not posting metrics updates in {}".format(
                        runescape_name, channel.mention
                    )
                )

    @runescape_set.command(name="username")
    async def set_username(
        self, ctx: commands.Context, *, runescape_name: Optional[str] = None
    ) -> None:
        """
        Set your runescape name for easer commands.

        Use this command without a name to clear your settings.
        """
        async with ctx.typing():
            if not runescape_name:
                await self.config.user(ctx.author).clear()
                await ctx.send("Your Runescape name has been cleared.")
            else:
                await self.config.user(ctx.author).rsn.set(runescape_name)
                await ctx.send("Your Runescape name has been set. To change re-do this command.")

    @runescape.command()
    async def profile(
        self, ctx: commands.Context, runescape_name: str = None, activity: int = 10
    ) -> None:
        """Display a players profile in Runescape"""
        async with ctx.typing():
            if runescape_name is None:
                runescape_name = await self.config.user(ctx.author).rsn()
                if runescape_name is None:
                    await ctx.send("You need to set your Runescape name first!")
                    return

            try:
                details = await PlayerDetails.get(runescape_name, session=self.session)
            except APIError:
                details = None
            try:
                profile = await Profile.get(runescape_name, activity, session=self.session)
            except PrivateProfileError:
                await ctx.send("That account has their profile set to private.")
                return
            except APIError:
                await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
                return
            embed = await profile.embed(details)
        await ctx.send(embed=embed)

    @runescape.command()
    async def stats(self, ctx: commands.Context, *, runescape_name: str = None) -> None:
        """Display a players stats in Runescape"""
        async with ctx.typing():
            if runescape_name is None:
                runescape_name = await self.config.user(ctx.author).rsn()
                if runescape_name is None:
                    await ctx.send("You need to set your Runescape name first!")
                    return
            try:
                profile = await Profile.get(runescape_name, session=self.session)
            except PrivateProfileError:
                await ctx.send("That account has their profile set to private.")
                return
            except APIError:
                await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
                return
            skills = profile.stats_table()
        await ctx.maybe_send_embed(skills)

    @runescape.command()
    async def reset(self, ctx: commands.Context) -> None:
        """Show Runescapes Daily, Weekly, and Monthly reset times."""
        async with ctx.typing():
            today = datetime.now(timezone.utc).replace(minute=0, second=0)
            daily = today + timedelta(hours=((0 - today.hour) % 24))
            weekly = daily + timedelta(days=((2 - daily.weekday()) % 7))
            monthly = datetime(
                year=daily.year, month=daily.month, day=28, hour=0, tzinfo=timezone.utc
            ) + timedelta(days=4)
            weekly_reset_str = int(weekly.timestamp())
            daily_reset_str = int(daily.timestamp())
            monthly_reset_str = int(monthly.timestamp())
            msg = (
                "Daily Reset is <t:{daily}:R> (<t:{daily}>).\n"
                "Weekly reset is <t:{weekly}:R> (<t:{weekly}>).\n"
                "Monthly Reset is <t:{month}:R> (<t:{month}>)."
            ).format(weekly=weekly_reset_str, daily=daily_reset_str, month=monthly_reset_str)
        await ctx.send(msg)

    @runescape.command(aliases=["flash", "wildyflash", "wildy"])
    async def wilderness(self, ctx: commands.Context) -> None:
        """Show Runescapes Daily, Weekly, and Monthly reset times."""
        async with ctx.typing():
            msg = "## Wilderness Flash Event Schedule\n"
            max_spaces = 26
            today = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            for event in sorted(
                [e for e in WildernessFlashEvents], key=lambda x: x.get_next(today)
            ):
                special = "*" if event.special else ""
                event_name = special + str(event)
                url = "https://runescape.wiki/w/Wilderness_Flash_Events#" + str(event).replace(
                    " ", "_"
                )
                ts = discord.utils.format_dt(event.get_next(today), "R")
                special_header = "### " if event.special else ""
                msg += f"{special_header}- `{event_name.ljust(max_spaces)}` - {ts} [link]({url})\n"
            wild_rewards_url = "https://runescape.wiki/w/Sack_of_very_wild_rewards"
            msg += (
                f"-# *Special events can drop a [sack of very wild rewards]({wild_rewards_url})."
            )
        await ctx.maybe_send_embed(msg)

    ######################################################################################
    # oldschool Runescape commands                                                       #
    ######################################################################################

    @runescape.group(name="osrs")
    async def osrs(self, ctx: commands.Context) -> None:
        """Search for OSRS highscores"""
        pass

    @osrs.command(name="wiki")
    async def osrs_wiki(self, ctx: commands.Context, *, search: str):
        """Look for something on the runescape Wiki."""
        base_url = "https://oldschool.runescape.wiki/w/?curid="
        async with ctx.typing():
            try:
                data = await self.wiki_api.search(GameEnum.oldschool, search)
            except WikiAPIError as e:
                log.debug(e)
                await ctx.send(
                    f"I could not find information about `{search}` on the Runescape Wiki."
                )
                return
            msg = f"Old School Runescape Wiki Results for `{search}`:\n"
            for _search in data["query"]["search"]:
                page_id = _search["pageid"]
                title = _search["title"]
                msg += f"[{title}]({base_url}{page_id})\n"
        await ctx.maybe_send_embed(msg)

    @osrs.command(name="ge")
    @commands.bot_has_permissions(embed_links=True)
    async def osrs_ge(self, ctx: commands.Context, *, search: str):
        """
        Look for something on the runescape Grand Exchange.

        You can lookup multiple items at once by separating them with `|`
        e.g. `[p]rs osrs ge bond|abyssal whip`
        """
        async with ctx.typing():
            try:
                if len(search.split("|")) > 1:
                    data = await self.wiki_api.latest(game=GameEnum.oldschool, name=search)
                    source = GESinglePages(data, self.wiki_api)
                else:
                    data = await self.wiki_api.last90d(game=GameEnum.oldschool, name=search)
                    source = GEChartPages([data], self.wiki_api)
            except WikiAPIError as e:
                await ctx.send(e)
                return
        await BaseMenu(source, self).start(ctx)

    @osrs.command(name="stats")
    async def osrs_stats(self, ctx: commands.Context, runescape_name: str = None) -> None:
        """Display a players stats in oldschool Runescape."""
        async with ctx.typing():
            if runescape_name is None:
                runescape_name = await self.config.user(ctx.author).osrsn()
                if runescape_name is None:
                    await ctx.send("You need to set your Runescape name first!")
                    return

            try:
                profile = await OSRSProfile.get(runescape_name, session=self.session)
            except APIError:
                await ctx.send(f"I can't find username `{runescape_name}`")
                return
            msg = await profile.get_stats_table()
        await ctx.maybe_send_embed(box(msg, lang="css"))

    @osrs.command(name="activities")
    @commands.bot_has_permissions(embed_links=True)
    async def osrs_activities(self, ctx: commands.Context, runescape_name: str = None) -> None:
        """Display a players Activities in oldschool Runescape Hiscores."""
        async with ctx.typing():
            if runescape_name is None:
                runescape_name = await self.config.user(ctx.author).osrsn()
                if runescape_name is None:
                    await ctx.send("You need to set your Runescape name first!")
                    return

            try:
                profile = await OSRSProfile.get(runescape_name, session=self.session)
            except APIError:
                await ctx.send(f"I can't find username `{runescape_name}`")
                return
            msg = await profile.get_profile_table()
            em = discord.Embed(description=box(msg, lang="css"), colour=await ctx.embed_colour())
        await ctx.send(embed=em)

    @osrs.command(name="set")
    async def osrs_set(
        self, ctx: commands.Context, *, runescape_name: Optional[str] = None
    ) -> None:
        """
        Set your runescape name for easer commands.

        Use this command without a name to clear your settings.
        """
        async with ctx.typing():
            if not runescape_name:
                await self.config.user(ctx.author).clear()
                await ctx.send("Your Runescape name has been cleared.")
            else:
                await self.config.user(ctx.author).osrsn.set(runescape_name)
                await ctx.send("Your Old School Runescape name has been set.")
