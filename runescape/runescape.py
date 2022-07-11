import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Literal, Optional

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold, box, humanize_list, humanize_number

from .profile import (
    Activities,
    Activity,
    APIError,
    OSRSProfile,
    PlayerDetails,
    PrivateProfileError,
    Profile,
)

log = logging.getLogger("red.trusty-cogs.runescape")

IMAGE_URL = "https://runescape.wiki/w/Special:FilePath/"


LVL_RE = re.compile(r"Levelled Up (\w+)", flags=re.I)
XP_RE = re.compile(r"\d+XP IN (.+)", flags=re.I)
KILLED_RE = re.compile(r"(?:I )?(?:killed|defeated) (?:\d+ |the )?([a-z \-,]+)", flags=re.I)
FOUND_RE = re.compile(r"I found (?:a pair of|some|a|an) (.+)", flags=re.I)


class Runescape(commands.Cog):
    """
    Display Runescape account info
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.3"

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

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

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

    @tasks.loop(seconds=60)
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
        timestamp = int(activity.date.timestamp())
        url = f"https://apps.runescape.com/runemetrics/app/overview/player/{profile.name}"
        msg = f"{profile.name}: {activity.text}\n{activity.details}\n\n<t:{timestamp}>"
        image_url = None
        page = None
        if match := KILLED_RE.search(activity.text):
            page = match.group(1).strip()
            if page.endswith("s"):
                page = page[:-1]
            page = page.replace(" ", "_")
            if "-" in page:
                page = page.title()
            else:
                page = page.capitalize()
            image_url = IMAGE_URL + page + ".png"
        if match := XP_RE.search(activity.text):
            page = match.group(1).strip()
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"
        if match := LVL_RE.search(activity.text):
            page = match.group(1).strip()
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"
        if match := FOUND_RE.search(activity.text):
            page = match.group(1).strip() + " detail"
            image_url = IMAGE_URL + page.replace(" ", "_").capitalize() + ".png"

        for channel_id, guild_id in channels.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue
            if not channel.permissions_for(guild.me).send_messages:
                continue
            if channel.permissions_for(guild.me).embed_links:
                em = discord.Embed(description=f"[{msg}]({url})")
                if image_url:
                    em.set_thumbnail(url=image_url)
                await channel.send(embed=em)
            else:
                await channel.send(msg)

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

    @runescape.group(name="osrs")
    async def osrs(self, ctx: commands.Context) -> None:
        """Search for OSRS highscores"""
        pass

    @runescape.command(name="wiki")
    async def runescape_wiki(self, ctx: commands.Context, *, search: str):
        """Look for something on the runescape Wiki."""
        base_url = "https://runescape.wiki/w/?curid="
        wiki_url = "https://runescape.wiki/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": search,
            "format": "json",
        }
        async with ctx.typing():
            async with self.session.get(wiki_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(
                        f"I could not find information about `{search}` on the Runescape Wiki."
                    )
                    return
            msg = f"Runescape Wiki Results for `{search}`:\n"
            for search in data["query"]["search"]:
                page_id = search["pageid"]
                title = search["title"]
                msg += f"[{title}]({base_url}{page_id})\n"
        await ctx.maybe_send_embed(msg)

    @runescape.command(name="vis", aliases=["viswax"])
    async def runescape_viswax(self, ctx: commands.Context):
        """
        Get the current combinations for vis wax

        https://runescape.wiki/w/Rune_Goldberg_Machine
        """
        async with ctx.typing():
            today = datetime.now(timezone.utc).replace(minute=0)
            daily = today + timedelta(hours=((0 - today.hour) % 24))
            wiki_url = "https://runescape.wiki/api.php"
            params = {
                "action": "parse",
                "page": "Rune_Goldberg_Machine",
                "section": "1",
                "prop": "wikitext",
                "format": "json",
            }
            async with self.session.get(wiki_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(
                        "I could not find the curren vis wax combinations on the Runescape Wiki."
                    )
                    return
            wikitext = data["parse"]["wikitext"]["*"]
            rune_re = re.compile(r"({{[^||]+\|([a-zA-Z ]+)\|[^||]+}})")
            # date_re = re.compile(r"date=(.+)\|")
            # date = date_re.search(wikitext)
            slot_1 = []
            slot_2 = [[], [], []]
            count = 0
            for rune in rune_re.finditer(wikitext):
                if len(slot_1) < 3:
                    slot_1.append(bold(rune.group(2)))
                else:
                    if count == 3:
                        count = 0
                    slot_2[count].append(bold(rune.group(2)))
                    count += 1
            _from = "\n" + wikitext.split("|")[-2]
            msg = f"Runescape Vis Wax Refreshes <t:{int(daily.timestamp())}:R>:\n"
            for i in range(len(slot_1)):
                msg += f"__Combination {i+1}__: {slot_1[i]} and either {humanize_list(slot_2[i], style='or')}\n"
            msg += _from + "\nhttps://runescape.wiki/w/Rune_Goldberg_Machine"
        await ctx.maybe_send_embed(msg)

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
        base_url = "https://runescape.wiki/w/"
        wiki_url = "https://api.weirdgloop.org/exchange/history/rs/latest"
        params = {
            "name": search,
        }
        async with ctx.typing():
            error_msg = f"I could not find `{search}` on the Runescape Grand Exchange."
            async with self.session.get(wiki_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(error_msg)
                    return
                if not data.get("success", True):
                    await ctx.send(error_msg)
                    return
            log.debug(data)
            embed = discord.Embed(
                title=f"Runescape GE Results for `{search}`", colour=await ctx.embed_colour()
            )
            for name, data in data.items():
                price = humanize_number(data["price"])
                item_url = base_url + name.replace(" ", "_")
                detail_url = IMAGE_URL + name.replace(" ", "_") + "_detail.png"
                if embed.description is not None:
                    embed.description += f"[{name}]({item_url}) - {price}\n"
                else:
                    embed.description = f"[{name}]({item_url}) - {price}\n"
                embed.set_thumbnail(url=detail_url)
        await ctx.send(embed=embed)

    @osrs.command(name="wiki")
    async def osrs_wiki(self, ctx: commands.Context, *, search: str):
        """Look for something on the runescape Wiki."""
        base_url = "https://oldschool.runescape.wiki/w/?curid="
        wiki_url = "https://oldschool.runescape.wiki/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": search,
            "format": "json",
        }
        async with ctx.typing():
            async with self.session.get(wiki_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(
                        f"I could not find information about `{search}` on the Runescape Wiki."
                    )
                    return
            msg = f"Old School Runescape Wiki Results for `{search}`:\n"
            for search in data["query"]["search"]:
                page_id = search["pageid"]
                title = search["title"]
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
        base_url = "https://oldschool.runescape.wiki/w/"
        image_url = "https://oldschool.runescape.wiki/w/Special:FilePath/"
        wiki_url = "https://api.weirdgloop.org/exchange/history/osrs/latest"
        params = {
            "name": search,
        }
        async with ctx.typing():
            error_msg = f"I could not find `{search}` on the Runescape Grand Exchange."
            async with self.session.get(wiki_url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                else:
                    await ctx.send(error_msg)
                    return
                if not data.get("success", True):
                    await ctx.send(error_msg)
                    return
            log.debug(data)
            embed = discord.Embed(
                title=f"OldSchool Runescape GE Results for `{search}`",
                colour=await ctx.embed_colour(),
            )
            for name, data in data.items():
                price = humanize_number(data["price"])
                item_url = base_url + name.replace(" ", "_")
                detail_url = image_url + name.replace(" ", "_") + "_detail.png"
                if embed.description is not None:
                    embed.description += f"[{name}]({item_url}) - {price}\n"
                else:
                    embed.description = f"[{name}]({item_url}) - {price}\n"
                embed.set_thumbnail(url=detail_url)
        await ctx.send(embed=embed)

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
            today = datetime.now(timezone.utc).replace(minute=0)
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
