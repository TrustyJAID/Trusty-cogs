import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Literal, Optional

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_number, pagify
from tabulate import tabulate

from .profile import Activities, Activity, Profile

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
        self.session = aiohttp.ClientSession()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    def cog_unload(self):
        self.check_new_metrics.cancel()
        self.bot.loop.create_task(self.session.close())

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
                data = await self.get_profile(username, 20)
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
            channel = guild.get_channel(int(channel_id))
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

    @commands.group(name="runescape", aliases=["rs"])
    async def runescape(self, ctx: commands.Context):
        """Search for a user account or profile"""
        pass

    @commands.group(name="osrs")
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
        headers = {"User-Agent": f"Red-DiscordBot Trusty-cogs wiki lookup on {self.bot.user}"}
        async with self.session.get(wiki_url, headers=headers, params=params) as r:
            if r.status == 200:
                data = await r.json()
            else:
                await ctx.send(f"I could not find information about `{search}` on the Runescape Wiki.")
                return
        msg = f"Runescape Wiki Results for `{search}`:\n"
        for search in data["query"]["search"]:
            page_id = search["pageid"]
            title = search['title']
            msg += f"[{title}]({base_url}{page_id})\n"
        await ctx.maybe_send_embed(msg)

    @runescape.command(name="nemiforest", aliases=["nemi", "forest"])
    async def runescape_nemiforest(self, ctx: commands.Context):
        """Display an image of a Nemi Forest instance with all nine nodes."""
        async with ctx.typing():
            subreddit_url = "https://api.reddit.com/r/nemiforest/new"
            params = {
                "limit": 1,
            }
            headers = {"User-Agent": f"Red-DiscordBot Trusty-cogs subreddit lookup on {self.bot.user}"}
            async with self.session.get(subreddit_url, headers=headers, params=params) as r:
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
                latest_post["title"]
                if not post_flair
                else f"[Depleted] " + latest_post["title"]
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
        headers = {"User-Agent": f"Red-DiscordBot Trusty-cogs wiki lookup on {self.bot.user}"}
        async with self.session.get(wiki_url, headers=headers, params=params) as r:
            if r.status == 200:
                data = await r.json()
            else:
                await ctx.send(f"I could not find information about `{search}` on the Runescape Wiki.")
                return
        msg = f"Old School Runescape Wiki Results for `{search}`:\n"
        for search in data["query"]["search"]:
            page_id = search["pageid"]
            title = search['title']
            msg += f"[{title}]({base_url}{page_id})\n"
        await ctx.maybe_send_embed(msg)

    @osrs.command(name="stats")
    async def osrs_stats(self, ctx: commands.Context, runescape_name: str = None) -> None:
        """Display a players stats in oldschool Runescape."""
        await ctx.trigger_typing()
        if runescape_name is None:
            runescape_name = await self.config.user(ctx.author).osrsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        details = await self.get_osrs_hiscores(runescape_name)
        if not details:
            return await ctx.send("I can't find username `{}`".format(runescape_name))
        msg = await self.osrs_stats_page(details, runescape_name)
        for page in pagify(msg):
            await ctx.send(box(page, lang="css"))

    @osrs.command(name="set")
    async def osrs_set(
        self, ctx: commands.Context, *, runescape_name: Optional[str] = None
    ) -> None:
        """
        Set your runescape name for easer commands.

        Use this command without a name to clear your settings.
        """
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

    @runescape_set.command(name="metrics")
    @commands.mod_or_permissions(manage_channels=True)
    async def runescape_set_metrics(
        self, ctx: commands.Context, runescape_name: str, channel: discord.TextChannel
    ) -> None:
        """
        Set a channel for automatic RuneMetrics updates

        `<runescape_name>` The Runescape Name of the account you want to follow
        `<channel>` The channel where updates should be posted
        """
        data = await self.get_profile(runescape_name, 20)
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

    @runescape_set.command(name="remove", aliases=["delete", "del", "rem"])
    @commands.mod_or_permissions(manage_channels=True)
    async def runescape_remove_metrics(
        self, ctx: commands.Context, runescape_name: str, channel: discord.TextChannel
    ) -> None:
        """
        Remove a channel from automatic RuneMetrics updates

        `<runescape_name>` The Runescape Name of the account you are following
        `<channel>` The channel where updates should stop being posted
        """
        data = await self.get_profile(runescape_name, 20)
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
        if not runescape_name:
            await self.config.user(ctx.author).clear()
            await ctx.send("Your Runescape name has been cleared.")
        else:
            await self.config.user(ctx.author).rsn.set(runescape_name)
            await ctx.send("Your Runescape name has been set. To change re-do this command.")

    async def osrs_highscores(self, runescape_name: str) -> str:
        return "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={}".format(
            runescape_name
        )

    async def get_osrs_hiscores(self, runescape_name: str) -> Optional[dict]:
        async with self.session.get(await self.osrs_highscores(runescape_name)) as resp:
            if resp.status != 200:
                return None
            return await resp.read()

    async def make_url_profile(self, runescape_name: str, activities: int) -> str:
        url = (
            "https://apps.runescape.com/runemetrics/profile/profile?user={}&activities={}".format(
                runescape_name, activities
            )
        )
        log.debug(url)
        return url

    async def make_url_player_details(self, runescape_name: str) -> str:
        return "http://services.runescape.com/m=website-data/playerDetails.ws?names=%5B%22{}%22%5D&callback=jQuery000000000000000_0000000000&_=0".format(
            runescape_name
        )

    async def get_player_details(self, runescape_name: str) -> dict:
        async with self.session.get(await self.make_url_player_details(runescape_name)) as resp:
            data = await resp.text()
        try:
            json_data = json.loads(
                data.replace("jQuery000000000000000_0000000000([", "").replace("]);", "")
            )
        except Exception:
            return {}
        return json_data
        # return await resp.json()

    async def get_data_profile(self, runescape_name: str, activities: int) -> dict:
        async with self.session.get(
            await self.make_url_profile(runescape_name, activities)
        ) as resp:
            data = await resp.json()
        # log.debug(data)
        return data

    async def get_profile_obj(self, profile_data: dict) -> Profile:
        ret = await Profile.from_json(profile_data)
        # log.debug(ret)
        return ret

    async def get_profile(self, runescape_name: str, activities: int = 5) -> Profile:
        data = await self.get_data_profile(runescape_name, activities)
        if "error" in data:
            return "NO PROFILE"
        return await self.get_profile_obj(data)

    @runescape.command()
    async def profile(
        self, ctx: commands.Context, runescape_name: str = None, activity: int = 10
    ) -> None:
        """Display a players profile in Runescape"""
        await ctx.trigger_typing()
        if runescape_name is None:
            runescape_name = await self.config.user(ctx.author).rsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        details = await self.get_player_details(runescape_name)
        data = await self.get_profile(runescape_name, activity)
        log.debug(details)
        if data == "NO PROFILE":
            await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
            return
        embed = await self.profile_embed(data, details)
        await ctx.send(embed=embed)

    @runescape.command()
    async def stats(self, ctx: commands.Context, *, runescape_name: str = None) -> None:
        """Display a players stats in Runescape"""
        await ctx.trigger_typing()
        if runescape_name is None:
            runescape_name = await self.config.user(ctx.author).rsn()
            if runescape_name is None:
                await ctx.send("You need to set your Runescape name first!")
                return

        data = await self.get_profile(runescape_name)
        if data == "NO PROFILE":
            await ctx.send("The account {} doesn't appear to exist!".format(runescape_name))
            return
        skills = await self.stats_message(data)
        await ctx.maybe_send_embed(skills)

    @runescape.command()
    async def reset(self, ctx: commands.Context) -> None:
        """Show Runescapes Daily, Weekly, and Monthly reset times."""
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

    async def stats_message(self, p: Profile) -> str:
        table = str(p)
        top_row_len = len(table.split("\n")[0])
        top_row = top_row_len * "-"
        spaces = int(((top_row_len - (14 + len(p.name))) / 2) - 1) * " "
        skills = (
            "```css\n{top_row}\n|{spaces}"
            "RS3 STATS FOR {user}{spaces}|"
            "\n{top_row}\n{skills}\n{top_row}```"
        ).format(spaces=spaces, top_row=top_row, user=p.name, skills=table)
        return skills

    async def osrs_stats_page(self, data: dict, runescape_name: str) -> str:
        table = await Profile.from_text(data)
        top_row_len = len(table.split("\n")[0])
        top_row = top_row_len * "-"
        spaces = int(((top_row_len - (14 + len(runescape_name))) / 2) - 1) * " "
        skills = (
            "{top_row}\n|{spaces}OSRS STATS FOR "
            "{user}{spaces}|\n{top_row}\n"
            "{skills}\n{top_row}"
        ).format(spaces=spaces, top_row=top_row, user=runescape_name, skills=table)
        return skills

    async def profile_embed(self, profile: Profile, details: dict) -> discord.Embed:
        em = discord.Embed()
        if details and details["isSuffix"]:
            em.set_author(name="{} {}".format(profile.name, details["title"]))
        elif details:
            em.set_author(name="{} {}".format(details["title"], profile.name))
        else:
            em.set_author(name=profile.name)
        activities = ""
        for activity in profile.activities:
            activities += f"[<t:{int(activity.date.timestamp())}>] {activity.details}\n"

        # em.colour = int(teams[_teams.name]["home"].replace("#", ""), 16)
        em.set_thumbnail(
            url="http://secure.runescape.com/m=avatar-rs/{}/chat.png".format(
                profile.name.replace(" ", "%20")
            )
        )
        em.add_field(name="Combat Level", value=profile.combatlevel)
        em.add_field(name="Total Level", value=humanize_number(profile.totalskill))
        em.add_field(name="Total XP", value=humanize_number(profile.totalxp))
        quests = tabulate(
            [[profile.questsstarted, profile.questsnotstarted, profile.questscomplete]],
            headers=["Started", "Not Started", "Complete"],
        )
        combat_xp = tabulate(
            [
                [
                    humanize_number(profile.magic_total),
                    humanize_number(profile.melee_total),
                    humanize_number(profile.ranged_total),
                ]
            ],
            headers=["Magic", "Melee", "Ranged"],
        )
        em.add_field(
            name="Combat XP Totals",
            value=f"```\n{combat_xp}\n```",
            inline=False,
        )
        em.add_field(
            name="Quests",
            value=f"```\n{quests}\n```",
            inline=False,
        )
        if activities:
            activities = list(pagify(activities, page_length=1024))[0]
            em.add_field(name="Activities", value=activities)
        if profile.logged_in:
            em.set_footer(
                text="Online",
                icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Green_pog.svg/64px-Green_pog.svg.png",
            )
        else:
            em.set_footer(
                text="Offline",
                icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/Red_pog.svg/64px-Red_pog.svg.png",
            )
        return em
