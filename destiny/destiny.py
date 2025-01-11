import asyncio
import csv
import datetime
import functools
import random
import re
from io import StringIO
from typing import Dict, List, Literal, Optional

import discord
from discord import app_commands
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    humanize_number,
    humanize_timedelta,
    pagify,
    text_to_file,
)
from redbot.core.utils.views import SetApiView
from tabulate import tabulate
from yarl import URL

from .api import DestinyAPI
from .converter import (
    LOADOUT_COLOURS,
    BungieXAccount,
    DestinyActivity,
    DestinyActivityModeType,
    DestinyCharacter,
    DestinyComponents,
    DestinyComponentType,
    DestinyItemType,
    DestinyManifestCacheStyle,
    DestinyRandomConverter,
    SearchInfo,
    StatsPage,
)
from .errors import Destiny2APIError, Destiny2MissingManifest, ServersUnavailable
from .menus import (
    BaseMenu,
    BasePages,
    BungieNewsSource,
    BungieTweetsSource,
    ClanPendingView,
    LoadoutPages,
    PostmasterPages,
    YesNoView,
)

DEV_BOTS = (552261846951002112,)
# If you want parsing the manifest data to be easier add your
# bots ID to this list otherwise this should help performance
# on bots that are just running the cog like normal

IMAGE_URL = URL("https://www.bungie.net")

_ = Translator("Destiny", __file__)
log = getLogger("red.trusty-cogs.Destiny")


@cog_i18n(_)
class Destiny(commands.Cog):
    """
    Get information from the Destiny 2 API
    """

    __version__ = "2.0.0"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 35689771456)
        self.config.register_global(
            api_token={"api_key": "", "client_id": "", "client_secret": ""},
            manifest_version="",
            enable_slash=False,
            manifest_channel=None,
            manifest_guild=None,
            manifest_notified_version=None,
            cache_manifest=0,
            manifest_auto=False,
            cog_version="0",
        )
        self.config.register_user(oauth={}, account={}, characters={})
        self.config.register_guild(
            clan_id=None,
            commands={},
            news_channel=None,
            posted_news=[],
            posted_tweets=[],
            tweets_channel=None,
        )
        self.dashboard_authed: Dict[int, dict] = {}
        self.message_authed: Dict[int, dict] = {}
        self.waiting_auth: Dict[int, asyncio.Event] = {}
        self.manifest_check_loop.start()
        self.news_checker.start()
        self.tweet_checker.start()
        self._manifest: dict = {}
        self._loadout_temp: dict = {}
        self._repo = ""
        self._commit = ""
        self._ready = asyncio.Event()
        self.api: DestinyAPI

    async def cog_unload(self):
        try:
            self.bot.remove_dev_env_value("destiny")
        except Exception:
            pass
        await self.api.close()
        self.manifest_check_loop.cancel()
        self.news_checker.cancel()
        self.tweet_checker.cancel()

    async def load_cache(self):
        tokens = await self.bot.get_shared_api_tokens("bungie")
        self.api = DestinyAPI(self, **tokens)
        if await self.config.cache_manifest() < 2:
            self._ready.set()
            return
        loop = asyncio.get_running_loop()
        for file in cog_data_path(self).iterdir():
            if (
                not file.is_file()
                or not file.name.endswith(".json")
                or file.name.startswith("settings")
            ):
                # ignore config's settings file and
                continue
            task = functools.partial(self.api.load_file, file=file)
            name = file.name.replace(".json", "")
            try:
                self.api._manifest[name] = await asyncio.wait_for(
                    loop.run_in_executor(None, task), timeout=180
                )
            except asyncio.TimeoutError:
                log.info("Error loading manifest data")
                continue
        self._ready.set()

    async def cog_load(self):
        if self.bot.user.id in DEV_BOTS:
            try:
                self.bot.add_dev_env_value("destiny", lambda x: self)
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        await self._migrate_v1_v2()
        loop.create_task(self.load_cache())
        loop.create_task(self._get_commit())

    async def _migrate_v1_v2(self):
        if await self.config.cog_version() < "1":
            tokens = await self.config.api_token()
            await self.bot.set_shared_api_tokens("bungie", **tokens)
            await self.config.api_token.clear()
            await self.config.cog_version.set("1")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, tokens: dict):
        if service_name != "bungie":
            return
        for key, value in tokens.items():
            if key == "api_key":
                self.api.api_key = value
            if key == "client_id":
                self.api._client_id = value
            if key == "client_secret":
                self.api._client_secret = value

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding a user's data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    async def _get_commit(self):
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "destiny":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._ready.wait()
        return True

    async def wait_for_auth(self, user_id: int):
        if user_id not in self.waiting_auth:
            raise RuntimeError("Tried to wait for a user's auth but they're not expecting it.")
        await self.waiting_auth[user_id].wait()

    @commands.Cog.listener()
    async def on_oauth_receive(self, user_id: int, payload: dict):
        if payload["provider"] != "destiny":
            return
        if "code" not in payload:
            log.error("Received Destiny OAuth without a code parameter %s - %s", user_id, payload)
            return
        self.dashboard_authed[int(user_id)] = payload
        self.waiting_auth[int(user_id)].set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id not in self.waiting_auth:
            return
        match = re.search(r"\?code=(?P<code>[a-z0-9]+)|(exit|stop)", message.content, flags=re.I)
        if match:
            self.message_authed[message.author.id] = {"code": match.group(1)}
            self.waiting_auth[message.author.id].set()

    @tasks.loop(seconds=300)
    async def tweet_checker(self):
        all_tweets = []
        for account in BungieXAccount:
            try:
                all_tweets.extend(await self.api.bungie_tweets(account))
            except Exception:
                log.exception("Error Checking bungiehelp.org")
                continue
        all_tweets.sort(key=lambda x: x.time)
        if len(all_tweets) < 1:
            return

        guilds = await self.config.all_guilds()
        article_keys = [a.id for a in all_tweets]
        for guild_id, data in guilds.items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            channel = guild.get_channel(data["tweets_channel"])
            if channel is None:
                continue
            if not channel.permissions_for(guild.me).send_messages:
                continue
            for tweet in all_tweets:
                if tweet.id in data["posted_tweets"]:
                    continue
                if not tweet.url:
                    continue
                await channel.send(content=tweet.url)
                data["posted_tweets"].append(tweet.id)
            if len(data["posted_tweets"]) > 100:
                for old in data["posted_tweets"].copy():
                    if old not in article_keys and len(data["posted_tweets"]) > 100:
                        data["posted_tweets"].remove(old)
            await self.config.guild(guild).posted_tweets.set(data["posted_tweets"])

    @tweet_checker.before_loop
    async def before_tweet_checker(self):
        await self.bot.wait_until_red_ready()
        await self._ready.wait()

    @tasks.loop(seconds=300)
    async def news_checker(self):
        try:
            news = await self.api.get_news()
        except Destiny2APIError as e:
            log.error("Error checking Destiny news sources: %s", e)
            return
        except Exception:
            log.exception("Error Checking Destiny news sources")
            return
        if len(news.NewsArticles) < 1:
            return
        source = BungieNewsSource(news)
        guilds = await self.config.all_guilds()
        article_keys = [a.save_id() for a in news.NewsArticles]
        for guild_id, data in guilds.items():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            channel = guild.get_channel(data["news_channel"])
            if channel is None:
                continue
            if not channel.permissions_for(guild.me).send_messages:
                continue
            for article in news.NewsArticles:
                if article.UniqueIdentifier in data["posted_news"]:
                    # modify the data to include the new save ID here
                    data["posted_news"].remove(article.UniqueIdentifier)
                    data["posted_news"].append(article.save_id())
                    continue
                if article.save_id() in data["posted_news"]:
                    continue
                kwargs = await source.format_page(None, article)
                if not channel.permissions_for(guild.me).embed_links:
                    kwargs["embed"] = None
                await channel.send(**kwargs)
                data["posted_news"].append(article.save_id())
            if len(data["posted_news"]) > 25:
                for old in data["posted_news"].copy():
                    if old not in article_keys and len(data["posted_news"]) > 25:
                        data["posted_news"].remove(old)
            await self.config.guild(guild).posted_news.set(data["posted_news"])

    @news_checker.before_loop
    async def before_news_checker(self):
        await self.bot.wait_until_red_ready()
        await self._ready.wait()

    @tasks.loop(seconds=3600)
    async def manifest_check_loop(self):
        guild = self.bot.get_guild(await self.config.manifest_guild())
        if not guild:
            return
        channel = guild.get_channel(await self.config.manifest_channel())
        if not channel:
            return
        manifest_version = await self.config.manifest_version()
        if manifest_version is None:
            # ignore if the manifest has never been downloaded
            return
        try:
            manifest_data = await self.api.get_manifest_data()
            if manifest_data is None:
                return
        except Exception:
            log.exception("Error getting manifest data")
            return
        notify_version = await self.config.manifest_notified_version()
        if manifest_data["version"] != notify_version:
            await self.config.manifest_notified_version.set(manifest_data["version"])
            if await self.config.manifest_auto():
                try:
                    await self.api.get_manifest()
                except Exception:
                    return
                msg = _("I have downloaded the latest Destiny Manifest: {version}").format(
                    version=manifest_data["version"]
                )
                await channel.send(msg)
            else:
                msg = _(
                    "There is a Destiny Manifest update available from {old_ver} to version {version}"
                ).format(old_ver=manifest_version, version=manifest_data["version"])
                await channel.send(msg)

    @commands.hybrid_group(name="destiny")
    async def destiny(self, ctx: commands.Context) -> None:
        """Get information from the Destiny 2 API"""

    @destiny.group(name="set")
    async def destiny_set(self, ctx: commands.Context) -> None:
        """Setup for the Destiny cog"""

    @destiny_set.command(name="news")
    @commands.mod_or_permissions(manage_messages=True)
    async def destiny_set_news(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Setup a channel to receive Destiny news articles automatically

        - `<channel>` The channel you want news articles posted in.
        """
        if ctx.guild is None:
            await ctx.send(_("This command can only be run inside a server."))
            return
        if channel is not None:
            if not channel.permissions_for(ctx.me).send_messages:
                await ctx.send(
                    _("I don't have permission to send messages in {channel}.").format(
                        channel=channel.mention
                    )
                )
                return
            try:
                news = await self.api.get_news()
            except Destiny2APIError:
                await ctx.send(
                    _("There was an error getting the current news posts. Please try again later.")
                )
                return
            current = [a.save_id() for a in news.NewsArticles]
            await self.config.guild(ctx.guild).posted_news.set(current)
            await self.config.guild(ctx.guild).news_channel.set(channel.id)
            await ctx.send(
                _("I will now post new Destiny articles in {channel}.").format(
                    channel=channel.mention
                )
            )
        else:
            await self.config.guild(ctx.guild).posted_news.clear()
            await self.config.guild(ctx.guild).news_channel.clear()
            await ctx.send(_("I will no longer automaticall post news articles in this server."))

    @destiny_set.command(name="tweets")
    @commands.mod_or_permissions(manage_messages=True)
    async def destiny_set_tweets(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Setup a channel to receive Bungie Help tweets automatically

        - `<channel>` The channel you want tweets posted in.
        """
        if ctx.guild is None:
            await ctx.send(_("This command can only be run inside a server."))
            return
        if channel is not None:
            if not channel.permissions_for(ctx.me).send_messages:
                await ctx.send(
                    _("I don't have permission to send messages in {channel}.").format(
                        channel=channel.mention
                    )
                )
                return
            try:
                tweets = []
                for account in BungieXAccount:
                    tweets.extend(await self.bungie_tweets(account))
            except Destiny2APIError:
                await ctx.send(
                    _("There was an error getting the current news posts. Please try again later.")
                )
                return
            current = [a.id for a in tweets]
            await self.config.guild(ctx.guild).posted_tweets.set(current)
            await self.config.guild(ctx.guild).tweets_channel.set(channel.id)
            await ctx.send(
                _("I will now post new Bungie Help tweets in {channel}.").format(
                    channel=channel.mention
                )
            )
        else:
            await self.config.guild(ctx.guild).posted_tweets.clear()
            await self.config.guild(ctx.guild).tweets_channel.clear()
            await ctx.send(_("I will no longer automaticall post Bungie Help in this server."))

    async def send_error_msg(self, ctx: commands.Context, error: Exception):
        if isinstance(error, ServersUnavailable):
            msg = _("The Destiny API servers appear to be offline. Try again later.")
        else:
            msg = _("I can't seem to find your Destiny profile.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg, ephemeral=True)
            else:
                await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.send(msg)

    @destiny.command()
    async def forgetme(self, ctx: commands.Context) -> None:
        """
        Remove your authorization to the destiny API on the bot
        """
        async with ctx.typing(ephemeral=False):
            await self.red_delete_data_for_user(requester="user", user_id=ctx.author.id)
        msg = _("Your authorization has been reset.")
        await ctx.send(msg)

    @destiny.group(aliases=["s"])
    async def search(self, ctx: commands.Context) -> None:
        """
        Search for a destiny item, vendor, record, etc.
        """

    @search.command(aliases=["item"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.max_concurrency(1, commands.BucketType.default)
    async def items(
        self, ctx: commands.Context, details_or_lore: Optional[SearchInfo] = None, *, search: str
    ) -> None:
        """
        Search for a specific item in Destiny 2

        `[details_or_lore]` signify what information to display for the item
        by default this command will show all available perks on weapons
        using `details`, `true`, or `stats` will show the weapons stat bars
        using `lore` here will instead display the weapons lore card instead if it exists.
        """
        async with ctx.typing(ephemeral=False):
            show_lore = True if details_or_lore is False else False
            if search.startswith("lore "):
                search = search.replace("lore ", "")

            try:
                if search.isdigit() or isinstance(search, int):
                    try:
                        items = await self.api.get_definition(
                            "DestinyInventoryItemDefinition", [search]
                        )
                    except Exception:
                        items = await self.api.search_definition(
                            "DestinyInventoryItemDefinition", search
                        )
                else:
                    items = await self.api.search_definition(
                        "DestinyInventoryItemDefinition", search
                    )
            except Destiny2MissingManifest as e:
                await ctx.send(e)
                return
            if not items:
                await ctx.send(_("`{search}` could not be found.").format(search=search))
                return
            embeds = []
            log.trace("Item: %s", items[0])
            for item in items.values():
                embed = discord.Embed()

                damage_type = ""
                try:
                    damage_data = (
                        await self.api.get_definition(
                            "DestinyDamageTypeDefinition", [item["defaultDamageTypeHash"]]
                        )
                    )[str(item["defaultDamageTypeHash"])]
                    damage_type = damage_data["displayProperties"]["name"]
                except KeyError:
                    pass
                description = (
                    damage_type
                    + " "
                    + item["itemTypeAndTierDisplayName"]
                    + "\n"
                    + item["flavorText"]
                    + "\n\n"
                )
                if item["itemType"] in [3] and not show_lore:
                    stats_str = ""
                    rpm = ""
                    recoil = ""
                    magazine = ""
                    for stat_hash, value in item["stats"]["stats"].items():
                        if stat_hash in ["1935470627", "1480404414", "1885944937"]:
                            continue

                        stat_info = (
                            await self.api.get_definition("DestinyStatDefinition", [stat_hash])
                        )[str(stat_hash)]
                        stat_name = stat_info["displayProperties"]["name"]
                        if not stat_name:
                            continue
                        prog = "█" * int(value["value"] / 10)
                        empty = "░" * int((100 - value["value"]) / 10)
                        bar = f"{prog}{empty}"
                        if stat_hash == "4284893193":
                            rpm = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if stat_hash == "3871231066":
                            recoil = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if stat_hash == "2715839340":
                            magazine = f"{stat_name}: **{value['value']}**\n"
                            continue
                        if details_or_lore:
                            stats_str += f"{stat_name}: **{value['value']}** \n{bar}\n"
                    stats_str += rpm + recoil + magazine
                    description += stats_str
                    embed.description = description
                    perks = await self.api.get_weapon_possible_perks(item)
                    for key, value in perks.items():
                        embed.add_field(name=key, value=value[:1024])
                if "loreHash" in item and (show_lore or item["itemType"] in [2]):
                    lore = (
                        await self.api.get_definition("DestinyLoreDefinition", [item["loreHash"]])
                    )[str(item["loreHash"])]
                    description += _("Lore: \n\n") + lore["displayProperties"]["description"]
                if len(description) > 2048:
                    count = 0
                    for page in pagify(description, page_length=1024):
                        if count == 0:
                            embed.description = page
                        else:
                            embed.add_field(name=_("Lore Continued"), value=page)
                        count += 1
                else:
                    embed.description = description

                name = item["displayProperties"]["name"]
                embed.title = name
                icon_url = IMAGE_URL.join(URL(item["displayProperties"]["icon"]))
                embed.set_author(name=name, icon_url=icon_url)
                embed.set_thumbnail(url=icon_url)
                if item.get("screenshot", False):
                    embed.set_image(url=IMAGE_URL.join(URL(item["screenshot"])))
                embeds.append(embed)
        if not embeds:
            await ctx.send(_("That item search could not be found."))
            return
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @items.autocomplete("search")
    async def parse_search_items(self, interaction: discord.Interaction, current: str):
        possible_options = await self.api.search_definition("simpleitems", current)
        choices = []
        for hash_key, data in possible_options.items():
            name = data["displayProperties"]["name"]
            if name:
                choices.append(app_commands.Choice(name=name, value=hash_key))
        return choices[:25]

    @destiny.command(name="joinme")
    @commands.bot_has_permissions(embed_links=True)
    async def destiny_join_command(self, ctx: commands.Context) -> None:
        """
        Get your Steam ID to give people to join your in-game fireteam
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            bungie_id = await self.config.user(ctx.author).oauth.membership_id()
            creds = await self.api.get_bnet_user(ctx.author, bungie_id)
            bungie_name = creds.get("uniqueName", "")
            join_code = f"\n```css\n/join {bungie_name}\n```"
            msg = _(
                "Use the following code in game to join {author}'s Fireteam:{join_code}"
            ).format(author=ctx.author.display_name, join_code=join_code)
            join_code = f"\n```css\n/join {bungie_name}\n```"
        await ctx.send(msg)

    @destiny.group()
    @commands.bot_has_permissions(embed_links=True)
    async def clan(self, ctx: commands.Context) -> None:
        """
        Clan settings
        """

    @clan.command(name="info")
    @commands.bot_has_permissions(embed_links=True)
    async def show_clan_info(self, ctx: commands.Context, clan_id: Optional[str] = None):
        """
        Display basic information about the clan set in this server
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            if clan_id:
                clan_re = re.compile(
                    r"(https:\/\/)?(www\.)?bungie\.net\/.*(groupid=(\d+))", flags=re.I
                )
                clan_invite = clan_re.search(clan_id)
                if clan_invite:
                    clan_id = clan_invite.group(4)
            elif ctx.guild is not None:
                clan_id = await self.config.guild(ctx.guild).clan_id()
            if not clan_id:
                prefix = ctx.clean_prefix
                msg = _(
                    "No clan ID has been setup for this server. "
                    "Use `{prefix}destiny clan set` to set one."
                ).format(prefix=prefix)
                await ctx.send(msg)
                return
            try:
                clan_info = await self.api.get_clan_info(ctx.author, clan_id)
                rewards = await self.api.get_clan_weekly_reward_state(ctx.author, clan_id)
                embed = await self.make_clan_embed(clan_info, rewards)
            except Exception:
                log.exception("Error getting clan info")
                msg = _("I could not find any information about this servers clan.")
                await ctx.send(msg)
                return
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=_("Request to join the clan"),
                url=f"https://www.bungie.net/en/ClanV2?groupid={clan_id}",
            )
        )
        await ctx.send(embed=embed, view=view)

    async def make_clan_embed(self, clan_info: dict, rewards: dict) -> discord.Embed:
        milestone_hash = rewards.get("milestoneHash", {})
        reward_string = ""
        if milestone_hash:
            emojis = {True: "✅", False: "❌"}
            milestones = await self.api.get_definition(
                "DestinyMilestoneDefinition", [str(milestone_hash)]
            )
            milestone_info = milestones[str(milestone_hash)]

            for reward_cats in rewards.get("rewards", []):
                reward_cat = milestone_info["rewards"][str(reward_cats["rewardCategoryHash"])]
                reward_string += reward_cat["displayProperties"]["name"] + "\n"
                for reward in reward_cats["entries"]:
                    reward_entry = reward_cat["rewardEntries"][str(reward["rewardEntryHash"])]
                    reward_string += f"{emojis[reward['earned']]} - {reward_entry['displayProperties']['name']}\n"
        clan_id = clan_info["detail"]["groupId"]
        clan_name = clan_info["detail"]["name"]
        clan_about = clan_info["detail"]["about"]
        clan_motto = clan_info["detail"]["motto"]
        clan_callsign = clan_info["detail"]["clanInfo"]["clanCallsign"]
        clan_xp_data = clan_info["detail"]["clanInfo"]["d2ClanProgressions"]["584850370"]
        weekly_progress = clan_xp_data["weeklyProgress"]
        weekly_limit = clan_xp_data["weeklyLimit"]
        level = clan_xp_data["level"]
        level_cap = clan_xp_data["levelCap"]
        members = clan_info["detail"]["memberCount"]
        max_members = clan_info["detail"]["features"]["maximumMembers"]
        clan_creation_date = datetime.datetime.strptime(
            clan_info["detail"]["creationDate"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=datetime.timezone.utc)
        clan_xp_str = _(
            "Level: {level}/{level_cap}\nWeekly Progress: " "{weekly_progress}/{weekly_limit}"
        ).format(
            level=level,
            level_cap=level_cap,
            weekly_progress=weekly_progress,
            weekly_limit=weekly_limit,
        )

        join_link = f"https://www.bungie.net/en/ClanV2?groupid={clan_id}"
        embed = discord.Embed(
            title=f"{clan_name} [{clan_callsign}]", description=clan_about, url=join_link
        )
        embed.add_field(name=_("Motto"), value=clan_motto, inline=False)
        embed.add_field(name=_("Clan XP"), value=clan_xp_str)
        embed.add_field(name=_("Members"), value=f"{members}/{max_members}")
        embed.add_field(name=_("Clan Founded"), value=discord.utils.format_dt(clan_creation_date))
        if reward_string:
            embed.add_field(name=_("Weekly Clan Rewards Earned"), value=reward_string)
        return embed

    @clan.command(name="set")
    @commands.bot_has_permissions(embed_links=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def set_clan_id(self, ctx: commands.Context, clan_id: str) -> None:
        """
        Set the clan ID for this server

        `<clan_id>` Must be either the clan's ID or you can provide
        the clan invite link at the `clan profile` setting on bungie.net

        example link: `https://www.bungie.net/en/ClanV2?groupid=1234567`
        the numbers after `groupid=` is the clan ID.
        """
        if ctx.guild is None:
            await ctx.send(_("This command can only be run inside a server."))
            return
        await ctx.defer()
        if not await self.api.has_oauth(ctx):
            return
        clan_re = re.compile(r"(https:\/\/)?(www\.)?bungie\.net\/.*(groupid=(\d+))", flags=re.I)
        clan_invite = clan_re.search(clan_id)
        if clan_invite:
            clan_id = clan_invite.group(4)
        try:
            clan_info = await self.api.get_clan_info(ctx.author, clan_id)
            embed = await self.make_clan_embed(clan_info, {})
        except Exception:
            log.exception("Error getting clan info")
            msg = _("I could not find a clan with that ID.")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).clan_id.set(clan_id)
            msg = {"content": _("Server's clan set to"), "embed": embed}
            await ctx.send(**msg)

    @clan.command(name="pending")
    @commands.bot_has_permissions(embed_links=True)
    async def clan_pending(self, ctx: commands.Context) -> None:
        """
        Display pending clan members.

        Clan admin can further approve specified clan members
        by reacting to the resulting message.
        """
        if ctx.guild is None:
            await ctx.send(_("This command can only be run inside a server."))
            return
        await ctx.defer()
        if not await self.api.has_oauth(ctx):
            return
        clan_id = await self.config.guild(ctx.guild).clan_id()
        if not clan_id:
            prefix = ctx.clean_prefix
            msg = _(
                "No clan ID has been setup for this server. "
                "Use `{prefix}destiny clan set` to set one."
            ).format(prefix=prefix)
            await ctx.send(msg)
        clan_pending = await self.api.get_clan_pending(ctx.author, clan_id)
        if not clan_pending["results"]:
            msg = _("There is no one pending clan approval.")
            await ctx.send(msg)
            return
        view = ClanPendingView(self, ctx, clan_id, clan_pending["results"])
        await view.start()

    @clan.command(name="roster")
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def get_clan_roster(
        self, ctx: commands.Context, output_format: Optional[Literal["csv", "md", "raw"]] = None
    ) -> None:
        """
        Get the full clan roster

        `[output_format]` if `csv` is provided this will upload a csv file of
        the clan roster instead of displaying the output.
        """
        if ctx.guild is None:
            await ctx.send(_("This command can only be run inside a server."))
            return
        if not await self.api.has_oauth(ctx):
            return
        clan_id = await self.config.guild(ctx.guild).clan_id()
        if not clan_id:
            prefix = ctx.clean_prefix
            msg = _(
                "No clan ID has been setup for this server. "
                "Use `{prefix}destiny clan set` to set one."
            ).format(prefix=prefix)
            await ctx.send(msg)
            return
        async with ctx.typing(ephemeral=False):
            clan = await self.api.get_clan_members(ctx.author, clan_id)
            headers = [
                "Discord Name",
                "Discord ID",
                "Destiny Name",
                "Destiny ID",
                "Bungie Name",
                "Bungie.net ID",
                "Last Seen Destiny",
                "Steam ID",
                "Join Date",
            ]
            clan_mems = ""
            rows = []
            saved_users = await self.config.all_users()
            for member in clan["results"]:
                last_online = datetime.datetime.utcfromtimestamp(
                    int(member["lastOnlineStatusChange"])
                )
                join_date = datetime.datetime.strptime(
                    member["joinDate"], "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                destiny_name = member["destinyUserInfo"]["LastSeenDisplayName"]
                destiny_id = member["destinyUserInfo"]["membershipId"]
                clan_mems += destiny_name + "\n"
                discord_id = None
                discord_name = None
                bungie_id = None
                # bungie_name = None
                steam_id = None
                destiny = member.get("destinyUserInfo", {})
                new_bungie_name = destiny.get("bungieGlobalDisplayName", "")
                new_bungie_name_code = destiny.get("bungieGlobalDisplayNameCode", "")
                new_bungie_name = f"{new_bungie_name}#{new_bungie_name_code}"
                try:
                    bungie_id = member["bungieNetUserInfo"]["membershipId"]
                    # bungie_name = member["bungieNetUserInfo"]["displayName"]
                    creds = await self.api.get_bnet_user_credentials(ctx.author, bungie_id)
                    steam_id = ""
                    for cred in creds:
                        if "credentialAsString" in cred:
                            steam_id = cred["credentialAsString"]
                except Exception:
                    pass
                for user_id, data in saved_users.items():
                    if data.get("oauth", {}).get("membership_id") == bungie_id:
                        discord_user = ctx.guild.get_member(int(user_id))
                        if discord_user:
                            discord_name = str(discord_user)
                            discord_id = discord_user.id

                user_info = [
                    discord_name,
                    f"'{discord_id}" if discord_id else None,
                    destiny_name,
                    f"'{destiny_id}" if destiny_id else None,
                    new_bungie_name,
                    f"'{bungie_id}" if bungie_id else None,
                    last_online,
                    f"'{steam_id}" if steam_id else None,
                    str(join_date),
                ]
                rows.append(user_info)
        if output_format == "csv":
            outfile = StringIO()
            employee_writer = csv.writer(
                outfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
            )
            employee_writer.writerow(headers)
            for row in rows:
                employee_writer.writerow(row)
            outfile.seek(0)
            file = text_to_file(outfile.getvalue(), filename="clan_roster.csv")
            await ctx.send(file=file)
        elif output_format == "md":
            data = tabulate(rows, headers=headers, tablefmt="github")
            file = text_to_file(data, filename="clan_roster.md")
            await ctx.send(file=file)
        else:
            await ctx.send(_("Displaying member roster for the servers clan."))
            data = tabulate(rows, headers=headers, tablefmt="pretty")
            for page in pagify(data, page_length=1990):
                await ctx.channel.send(box(page, lang="css"))

    @destiny.command(name="reset")
    async def destiny_reset_time(self, ctx: commands.Context):
        """
        Show exactly when Weekyl and Daily reset is
        """
        async with ctx.typing(ephemeral=False):
            today = datetime.datetime.now(datetime.timezone.utc)
            tuesday = today + datetime.timedelta(days=((1 - today.weekday()) % 7))
            weekly = datetime.datetime(
                year=tuesday.year,
                month=tuesday.month,
                day=tuesday.day,
                hour=17,
                tzinfo=datetime.timezone.utc,
            )
            reset_time = today + datetime.timedelta(hours=((17 - today.hour) % 24))
            daily = datetime.datetime(
                year=reset_time.year,
                month=reset_time.month,
                day=reset_time.day,
                hour=reset_time.hour,
                tzinfo=datetime.timezone.utc,
            )
            weekly_reset_str = int(weekly.timestamp())
            daily_reset_str = int(daily.timestamp())
            msg = _(
                "Weekly reset is <t:{weekly}:R> (<t:{weekly}>).\n"
                "Daily Reset is <t:{daily}:R> (<t:{daily}>)."
            ).format(weekly=weekly_reset_str, daily=daily_reset_str)
        await ctx.send(msg)

    @destiny.command(name="news")
    @commands.bot_has_permissions(embed_links=True)
    async def destiny_news(self, ctx: commands.Context) -> None:
        """
        Get the latest news articles from Bungie.net
        """
        async with ctx.typing(ephemeral=False):
            try:
                news = await self.api.get_news()
            except Destiny2APIError as e:
                return await self.send_error_msg(ctx, e)
            source = BungieNewsSource(news)
        await BaseMenu(source=source, cog=self).start(ctx=ctx)

    @destiny.command(name="tweets")
    @commands.bot_has_permissions(embed_links=True)
    async def destiny_tweets(
        self, ctx: commands.Context, account: Optional[BungieXAccount] = None
    ) -> None:
        """
        Get the latest news articles from Bungie.net
        """
        async with ctx.typing(ephemeral=False):
            try:
                if account is None:
                    all_tweets = []
                    for account in BungieXAccount:
                        all_tweets.extend(await self.api.bungie_tweets(account))
                    all_tweets.sort(key=lambda x: x.time, reverse=True)
                else:
                    all_tweets = await self.api.bungie_tweets(account)
            except Destiny2APIError as e:
                return await self.send_error_msg(ctx, e)
            source = BungieTweetsSource(all_tweets)
        await BaseMenu(source=source, cog=self).start(ctx=ctx)

    async def get_seal_icon(self, record: dict) -> Optional[str]:
        if record["parentNodeHashes"]:
            node_defs = await self.api.get_definition(
                "DestinyPresentationNodeDefinition", record["parentNodeHashes"]
            )
            for key, data in node_defs.items():
                dp = data["displayProperties"]
                if not dp["hasIcon"]:
                    continue
                if dp["iconSequences"]:
                    if len(dp["iconSequences"][0]["frames"]) == 3:
                        return dp["iconSequences"][0]["frames"][1]
                return dp["displayProperties"]["icon"]
        else:
            pres_node = await self.api.get_entities("DestinyPresentationNodeDefinition")
            node = None
            for key, data in pres_node.items():
                if "completionRecordHash" not in data:
                    continue
                if record["hash"] == data["completionRecordHash"]:
                    node = data["displayProperties"]
                    break
            if node and not node["hasIcon"]:
                return record["icon"]
            elif not node:
                return record["icon"]
            else:
                if node["iconSequences"]:
                    if len(node["iconSequences"][0]["frames"]) == 3:
                        return node["iconSequences"][0]["frames"][1]
                return node["icon"]

    async def get_character_description(self, char: dict) -> str:
        info = ""
        race = (await self.api.get_definition("DestinyRaceDefinition", [char["raceHash"]]))[
            str(char["raceHash"])
        ]
        gender = (await self.api.get_definition("DestinyGenderDefinition", [char["genderHash"]]))[
            str(char["genderHash"])
        ]
        char_class = (
            await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
        )[str(char["classHash"])]
        info += "{race} {gender} {char_class} ".format(
            race=race["displayProperties"]["name"],
            gender=gender["displayProperties"]["name"],
            char_class=char_class["displayProperties"]["name"],
        )
        return info

    async def get_engram_tracker(self, user: discord.abc.User, char_id: str, chars: dict) -> str:
        engram_tracker = await self.api.get_definition(
            "DestinyInventoryItemDefinition", [1624697519]
        )
        eg = engram_tracker["1624697519"]
        return await self.api.replace_string(
            user, eg["displayProperties"]["description"], char_id, chars
        )

    async def make_character_embed(
        self, user: discord.abc.User, char_id: str, chars: dict, player_currency: str
    ) -> discord.Embed:
        char = chars["characters"]["data"][char_id]
        info = await self.get_character_description(char)
        titles = ""
        title_name = ""
        embed = discord.Embed(title=info)
        if "titleRecordHash" in char:
            # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
            char_title = (
                await self.api.get_definition("DestinyRecordDefinition", [char["titleRecordHash"]])
            )[str(char["titleRecordHash"])]
            icon_url = await self.get_seal_icon(char_title)
            title_info = "**{title_name}**\n{title_desc}\n"
            try:
                gilded = ""
                is_gilded, count = await self.api.check_gilded_title(chars, char_title)
                if is_gilded:
                    gilded = _("Gilded ")
                title_name = (
                    f"{gilded}"
                    + char_title["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                    + f"{count}"
                )
                title_desc = char_title["displayProperties"]["description"]
                titles += title_info.format(title_name=title_name, title_desc=title_desc)
                if icon_url is not None:
                    embed.set_thumbnail(url=IMAGE_URL.join(URL(icon_url)))
            except KeyError:
                pass
        bnet_display_name = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayName"]
        bnet_code = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayNameCode"]
        bnet_name = f"{bnet_display_name}#{bnet_code}"
        embed.set_author(name=bnet_name, icon_url=user.display_avatar)
        # if "emblemPath" in char:
        # embed.set_thumbnail(url=IMAGE_URL.join(URL(char["emblemPath"]))
        if "emblemBackgroundPath" in char:
            embed.set_image(url=IMAGE_URL.join(URL(char["emblemBackgroundPath"])))
        if titles:
            # embed.add_field(name=_("Titles"), value=titles)
            embed.set_author(name=f"{bnet_name} ({title_name})", icon_url=user.display_avatar)
        # log.debug(data)
        stats_str = ""
        if chars["profileCommendations"]:
            commendations = await self.get_commendation_scores(
                chars["profileCommendations"]["data"]
            )
            commendation_score = chars["profileCommendations"]["data"]["totalScore"]
            stats_str += _("Commendations: {score}\n{commendations}\n").format(
                score=commendation_score, commendations=commendations
            )
        time_played = humanize_timedelta(seconds=int(char["minutesPlayedTotal"]) * 60)
        last_played = datetime.datetime.strptime(
            char["dateLastPlayed"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=datetime.timezone.utc)
        for stat_hash, value in char["stats"].items():
            stat_info = (await self.api.get_definition("DestinyStatDefinition", [stat_hash]))[
                str(stat_hash)
            ]
            stat_name = stat_info["displayProperties"]["name"]
            prog = "█" * int(value / 10)
            empty = "░" * int((100 - value) / 10)
            bar = f"{prog}{empty}"
            if stat_hash == "1935470627":
                artifact_bonus = chars["profileProgression"]["data"]["seasonalArtifact"][
                    "powerBonus"
                ]
                bar = _("Artifact Bonus: {bonus}").format(bonus=artifact_bonus)
            stats_str += f"{stat_name}: **{value}** \n{bar}\n"
        stats_str += _("Time Played Total: **{time}**\n").format(time=time_played)
        stats_str += _("Last Played: **{time}**\n").format(
            time=discord.utils.format_dt(last_played, "R")
        )
        active_score = humanize_number(chars["profileRecords"]["data"]["activeScore"])
        legacy_score = humanize_number(chars["profileRecords"]["data"]["legacyScore"])
        lifetime_score = humanize_number(chars["profileRecords"]["data"]["lifetimeScore"])
        triumph_str = _(
            "Active Score: **{active}**\n"
            "Legacy Score: **{legacy}**\n"
            "Lifetime Score: **{lifetime}**\n"
        ).format(active=active_score, legacy=legacy_score, lifetime=lifetime_score)
        embed.add_field(name=_("Triumphs"), value=triumph_str)
        embed.description = stats_str
        embed = await self.api.get_char_colour(embed, char)
        if titles:
            embed.add_field(name=_("Titles"), value=titles)
        # embed.add_field(name=_("Current Currencies"), value=player_currency, inline=False)
        embed.add_field(
            name=_("Engram Tracker"), value=await self.get_engram_tracker(user, char_id, chars)
        )
        return embed

    @destiny.command()
    async def postmaster(self, ctx: commands.Context):
        """
        View and pull from the postmaster
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(
                    ctx.author,
                    components=DestinyComponents(
                        DestinyComponentType.characters, DestinyComponentType.character_inventories
                    ),
                )
                await self.api.save(chars)
            except Destiny2APIError as e:
                log.exception(e)
                await self.send_error_msg(ctx, e)
                return
            # Postmaster bucket 215593132
            postmasters = chars["characters"]["data"]
            for char_id, items in chars["characterInventories"]["data"].items():
                char = chars["characters"]["data"][char_id]
                info = await self.get_character_description(char)
                embed = discord.Embed(title=_("Postmaster"))
                embed.set_author(name=info)
                msg = ""
                postmaster_items = [
                    i for i in items["items"] if "bucketHash" in i and i["bucketHash"] == 215593132
                ]
                pm = await self.api.get_definition(
                    "DestinyInventoryItemDefinition",
                    list(set(i["itemHash"] for i in postmaster_items)),
                )
                postmasters[char_id].update(
                    {"items": postmaster_items, "data": pm, "embed": embed}
                )
            source = PostmasterPages(postmasters)
            await BaseMenu(source, self).start(ctx)

    @destiny.command(name="commendations", aliases=["com"])
    async def commendations(self, ctx: commands.Context):
        """
        Show your commendation scores
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            try:
                components = DestinyComponents(DestinyComponentType.social_commendations)
                chars = await self.api.get_characters(ctx.author, components=components)
                await self.api.save(chars, "character.json")
            except Destiny2APIError as e:
                log.error(e, exc_info=True)
                await self.send_error_msg(ctx, e)
                return
            embed = await self.make_commendations_embed(chars)
        await ctx.send(embed=embed)

    async def make_commendations_embed(self, chars: dict) -> discord.Embed:
        bnet_display_name = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayName"]
        bnet_code = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayNameCode"]
        bnet_name = f"{bnet_display_name}#{bnet_code}"
        profile_commendations = chars["profileCommendations"]["data"]
        commendation_nodes = await self.api.get_entities("DestinySocialCommendationNodeDefinition")
        commendations = await self.api.get_entities("DestinySocialCommendationDefinition")
        bar = await self.get_commendation_scores(chars["profileCommendations"]["data"])
        given, received = profile_commendations["scoreDetailValues"]
        total_score = profile_commendations["totalScore"]
        description = _(
            "Score: **{total_score}**\n{bar}\nGiven: {given} - Received: {received}"
        ).format(total_score=total_score, bar=bar, given=given, received=received)
        embed = discord.Embed(
            title=_("{name} Commendations").format(name=bnet_name), description=description
        )

        scores = profile_commendations["commendationNodeScoresByHash"]
        scores_total = sum(v for k, v in scores.items() if k != "1062358355")
        emojis = {
            "154475713": "🟩",  # Ally
            "1341823550": "🟥",  # Fun
            "4180748446": "🟧",  # Mastery
            "1390663518": "🟦",  # Leadership
        }
        data = {}
        for commendation_hash, number in profile_commendations["commendationScoresByHash"].items():
            commendation = commendations.get(commendation_hash, {})
            parent_hash = str(commendation.get("parentCommendationNodeHash"))
            parent = commendation_nodes.get(parent_hash)
            if parent is None:
                continue
            parent_name = parent["displayProperties"]["name"]
            if parent_name not in data:
                data[parent_name] = {"hash": parent_hash, "commendations": {}}
            commendation_name = commendation["displayProperties"]["name"]
            data[parent_name]["commendations"][commendation_name] = {
                "number": number,
                "hash": commendation_hash,
            }
        for name, info in data.items():
            msg = ""
            emoji = emojis.get(info["hash"])
            score_value = profile_commendations["commendationNodeScoresByHash"].get(info["hash"])
            percent = f"{score_value/scores_total:.0%}"
            em_name = f"{emoji} {name} - {percent}"
            total = 0
            for com_name, details in info["commendations"].items():
                number = details["number"]
                total += number
                msg += f"{com_name}: {number}\n"
            full_msg = _("Total: {total}\n{each}").format(total=total, each=msg)
            embed.add_field(name=em_name, value=full_msg, inline=False)
        return embed

    async def get_commendation_scores(self, data: dict) -> str:
        emojis = {
            "154475713": "🟩",  # Ally
            "1341823550": "🟥",  # Fun
            "4180748446": "🟧",  # Mastery
            "1390663518": "🟦",  # Leadership
        }
        scores = data["commendationNodeScoresByHash"]
        total = sum(v for k, v in scores.items() if k != "1062358355")
        ret = ""

        for k, v in scores.items():
            if k == "1062358355":
                continue
            ret += emojis[k] * int((v / total) * 16)
        return ret

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def user(self, ctx: commands.Context, user: discord.Member = commands.Author) -> None:
        """
        Display a menu of your basic character's info
        `[user]` A member on the server who has setup their account on this bot.
        """
        if not await self.api.has_oauth(ctx, user):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(user)
                await self.api.save(chars, "character.json")
            except Destiny2APIError as e:
                log.error(e, exc_info=True)
                await self.send_error_msg(ctx, e)
                return
            embeds = []
            currency_datas = await self.api.get_definition(
                "DestinyInventoryItemLiteDefinition",
                [v["itemHash"] for v in chars["profileCurrencies"]["data"]["items"]],
            )
            player_currency = ""
            for item in chars["profileCurrencies"]["data"]["items"]:
                quantity = humanize_number(item["quantity"])
                name = currency_datas[str(item["itemHash"])]["displayProperties"]["name"]
                player_currency += f"{name}: **{quantity}**\n"
            for char_id, char in chars["characters"]["data"].items():
                embed = await self.make_character_embed(user, char_id, chars, player_currency)
                embeds.append(embed)
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @search.command()
    @commands.bot_has_permissions(embed_links=True)
    async def lore(self, ctx: commands.Context, entry: str = None) -> None:
        """
        Find Destiny Lore
        """
        async with ctx.typing(ephemeral=False):
            try:
                data = await self.api.get_entities("DestinyLoreDefinition")
            except Exception:
                msg = _("The manifest needs to be downloaded for this to work.")
                await ctx.send(msg)
                return
            lore = []
            for entry_hash, entries in data.items():
                em = discord.Embed(title=entries["displayProperties"]["name"])
                description = entries["displayProperties"]["description"]
                if len(description) < 2048:
                    em.description = entries["displayProperties"]["description"]
                elif len(description) > 2048 and len(description) < 6000:
                    em.description = description[:2048]
                    new_desc = description[:2048]
                    parts = [new_desc[i : i + 1024] for i in range(0, len(new_desc), 1024)]
                    for i in parts:
                        em.add_field(name=_("Continued"), value=i)

                if entries["displayProperties"]["hasIcon"]:
                    icon = entries["displayProperties"]["icon"]
                    em.set_thumbnail(url=IMAGE_URL.join(URL(icon)))
                lore.append(em)
            if entry:
                for t in lore:
                    if entry.lower() in str(t.title).lower():
                        print(t.title)
                        lore.insert(0, lore.pop(lore.index(t)))
        await BaseMenu(
            source=BasePages(
                pages=lore,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @lore.autocomplete("entry")
    async def parse_search_lore(self, interaction: discord.Interaction, current: str):
        possible_options: dict = await self.api.get_entities("DestinyLoreDefinition")
        choices = []
        for data in possible_options.values():
            name = data["displayProperties"]["name"]
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        log.trace("parse_search_lore choices: %s", len(choices))
        return choices[:25]

    @destiny.command(aliases=["whereisxûr"])
    @commands.bot_has_permissions(embed_links=True)
    async def whereisxur(self, ctx: commands.Context) -> None:
        """
        Display Xûr's current location
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(ctx.author)

                # await self.save(chars, "characters.json")
            except Destiny2APIError as e:
                # log.debug(e)
                await self.send_error_msg(ctx, e)
                return
            char_id = list(chars["characters"]["data"].keys())[0]
            try:
                xur = await self.api.get_vendor(ctx.author, char_id, "2190858386")
                xur_def = (
                    await self.api.get_definition("DestinyVendorDefinition", ["2190858386"])
                )["2190858386"]
            except Destiny2APIError:
                log.error("I can't seem to see Xûr at the moment")
                today = datetime.datetime.now(tz=datetime.timezone.utc)
                friday = today.replace(hour=17, minute=0, second=0) + datetime.timedelta(
                    (4 - today.weekday()) % 7
                )
                msg = _("Xûr's not around, come back {next_xur}.").format(
                    next_xur=discord.utils.format_dt(friday, "R")
                )
                await ctx.send(msg)
                return
            try:
                loc_index = xur["vendor"]["data"]["vendorLocationIndex"]
                loc = xur_def["locations"][loc_index].get("destinationHash")
                location_data = (
                    await self.api.get_definition("DestinyDestinationDefinition", [loc])
                ).get(str(loc), None)
                location_name = location_data.get("displayProperties", {}).get("name", "")
            except Exception:
                log.exception("Cannot get xur's location")
                location_name = _("Unknown")
        msg = _("Xûr's current location is {location}.").format(location=location_name)
        await ctx.send(msg)

    @destiny.command(name="xûr", aliases=["xur"])
    @commands.bot_has_permissions(embed_links=True)
    async def xur(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display a menu of Xûr's current wares

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "2190858386", character)

    async def vendor_menus(
        self,
        ctx: commands.Context,
        vendor_id: str,
        character: Optional[str] = None,
    ):
        async with ctx.typing(ephemeral=False):
            if character is None:
                try:
                    chars = await self.api.get_characters(ctx.author)
                    char_id: str = list(chars["characters"]["data"].keys())[0]

                    await self.api.save(chars, "characters.json")
                except Destiny2APIError as e:
                    # log.debug(e)
                    await self.send_error_msg(ctx, e)
                    return
            else:
                char_id: str = character
            try:
                vendor = await self.api.get_vendor(ctx.author, char_id, vendor_id)
                vendor_def = (
                    await self.api.get_definition("DestinyVendorDefinition", [vendor_id])
                )[vendor_id]
                await self.api.save(vendor, "vendor.json")
                await self.api.save(vendor_def, "vendor_def.json")
            except Destiny2APIError:
                if vendor_id == "2190858386":
                    log.error("I can't seem to see Xûr at the moment")
                    today = datetime.datetime.now(tz=datetime.timezone.utc)
                    friday = today.replace(hour=17, minute=0, second=0) + datetime.timedelta(
                        (4 - today.weekday()) % 7
                    )
                    next_xur = discord.utils.format_dt(friday, style="R")
                    msg = _("Xûr's not around, come back {next_xur}.").format(next_xur=next_xur)
                    await ctx.send(msg)
                else:
                    await ctx.send(_("I can't seem to find that vendors inventory."))
                return
            try:
                loc_index = vendor["vendor"]["data"]["vendorLocationIndex"]
                loc = vendor_def["locations"][loc_index].get("destinationHash")
                location_data = (
                    await self.api.get_definition("DestinyDestinationDefinition", [loc])
                ).get(str(loc), None)
                location = location_data.get("displayProperties", {}).get("name", "")
            except Exception:
                log.exception("Cannot get vendors location")
                location = _("Unknown")
            date = datetime.datetime.strptime(
                vendor["vendor"]["data"]["nextRefreshDate"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            date_str = discord.utils.format_dt(date, style="R")
            # items = [v["itemHash"] for k, v in xur["sales"]["data"].items()]
            embeds: List[discord.Embed] = []
            # data = await self.get_definition("DestinyInventoryItemDefinition", items)
            description = vendor_def["displayProperties"]["description"]
            name = vendor_def["displayProperties"]["name"]
            embed = discord.Embed(
                title=_("{name}'s current wares").format(name=name),
                colour=discord.Colour.red(),
                description=f"{location}\n{description}\n"
                + _("Next Refresh {date}").format(date=date_str),
            )
            if "largeTransparentIcon" in vendor_def["displayProperties"]:
                embed.set_thumbnail(
                    url=IMAGE_URL.join(
                        URL(vendor_def["displayProperties"]["largeTransparentIcon"])
                    )
                )
            # embed.set_author(name=_("Xûr's current wares"))
            # location = xur_def["locations"][0]["destinationHash"]
            # log.debug(await self.get_definition("DestinyDestinationDefinition", [location]))
            all_hashes = [i["itemHash"] for i in vendor["sales"]["data"].values()]
            all_items = await self.api.get_definition("DestinyInventoryItemDefinition", all_hashes)
            item_costs = [
                c["itemHash"] for k, i in vendor["sales"]["data"].items() for c in i["costs"]
            ]
            item_cost_defs = await self.api.get_definition(
                "DestinyInventoryItemLiteDefinition", item_costs
            )
            stat_hashes = []
            perk_hashes = []
            for item_index in vendor["sales"]["data"]:
                if item_index in vendor["itemComponents"]["stats"]["data"]:
                    for stat_hash in vendor["itemComponents"]["stats"]["data"][item_index][
                        "stats"
                    ]:
                        stat_hashes.append(stat_hash)
                if item_index in vendor["itemComponents"]["reusablePlugs"]["data"]:
                    for __, plugs in vendor["itemComponents"]["reusablePlugs"]["data"][item_index][
                        "plugs"
                    ].items():
                        for plug in plugs:
                            perk_hashes.append(plug["plugItemHash"])
            all_perks = await self.api.get_definition(
                "DestinyInventoryItemDefinition", perk_hashes
            )
            all_stats = await self.api.get_definition("DestinyStatDefinition", stat_hashes)
            main_page = {}
            for index, item_base in vendor["sales"]["data"].items():
                item = all_items[str(item_base["itemHash"])]
                perks = ""
                item_type = DestinyItemType(item["itemType"])
                item_hash = item_base["itemHash"]
                url = f"https://www.light.gg/db/items/{item_hash}"
                item_embed = discord.Embed(title=item["displayProperties"]["name"], url=url)
                item_embed.set_thumbnail(
                    url=IMAGE_URL.join(URL(item["displayProperties"]["icon"]))
                )
                if "screenshot" in item:
                    item_embed.set_image(url=IMAGE_URL.join(URL(item["screenshot"])))
                for perk_index in vendor["itemComponents"]["reusablePlugs"]["data"].get(
                    index, {"plugs": []}
                )["plugs"]:
                    for perk_hash in vendor["itemComponents"]["reusablePlugs"]["data"][index][
                        "plugs"
                    ][perk_index]:
                        perk = all_perks.get(str(perk_hash["plugItemHash"]), None)
                        if perk is None:
                            continue
                        properties = perk["displayProperties"]
                        if (
                            properties["name"] == "Empty Mod Socket"
                            or properties["name"] == "Default Ornament"
                            or properties["name"] == "Change Energy Type"
                            or properties["name"] == "Empty Catalyst Socket"
                            or properties["name"] == "Upgrade Armor"
                            or properties["name"] == "Default Shader"
                            or properties["name"] == "Tier 2 Weapon"
                        ):
                            continue
                        if "name" in properties and "description" in properties:
                            if not properties["name"]:
                                continue
                            # await self.save(perk, properties["name"] + ".json")
                            perks += "- **{0}**\n".format(properties["name"])
                stats_str = ""
                if "equippingBlock" in item:
                    slot_hash = item["equippingBlock"]["equipmentSlotTypeHash"]
                    if slot_hash in [1585787867, 20886954, 14239492, 3551918588, 3448274439]:
                        total = 0
                        for stat_hash, stat_data in vendor["itemComponents"]["stats"]["data"][
                            index
                        ]["stats"].items():
                            stat_info = all_stats[str(stat_hash)]
                            stat_name = stat_info["displayProperties"]["name"]
                            stat_value = stat_data["value"]
                            # prog = "█" * int(stat_value / 6)
                            # empty = "░" * int((42 - stat_value) / 6)
                            # bar = f"\n{prog}{empty} "
                            bar = " "
                            stats_str += f"{stat_name}:{bar}**{stat_value}**\n"
                            total += stat_value
                        stats_str += _("Total: **{total}**\n").format(total=total)
                tier_type = item["itemTypeAndTierDisplayName"]
                tier_type_url = ""
                if tier_type:
                    tier_type_url = f"[{tier_type}]({url})\n"
                refresh_str = ""
                if "overrideNextRefreshDate" in item_base:
                    date = datetime.datetime.strptime(
                        item_base["overrideNextRefreshDate"], "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc)
                    refresh_str = _("**Refreshes {refresh_time}**").format(
                        refresh_time=discord.utils.format_dt(date, "R")
                    )
                try:
                    cost_str = ""
                    if item_base["costs"]:
                        cost_str += _("Cost: ")
                    for cost in item_base["costs"]:
                        cost_def = item_cost_defs[str(cost["itemHash"])]
                        mat_name = cost_def["displayProperties"]["name"]
                        qty = cost["quantity"]
                        cost_str += f"{qty} {mat_name}\n"
                except IndexError:
                    cost_str = ""
                item_description = item["displayProperties"]["description"] + "\n"
                msg = f"{tier_type_url}{item_description}{stats_str}{perks}{cost_str}{refresh_str}"
                msg = await self.api.replace_string(ctx.author, msg)
                item_embed.description = msg[:4096]
                if item_type.value not in main_page:
                    main_page[item_type.value] = {}
                main_page[item_type.value][
                    "**__" + item["displayProperties"]["name"] + "__**\n"
                ] = msg

                embeds.insert(0, item_embed)
            for _item_type in sorted(main_page):
                for name, msg in main_page[_item_type].items():
                    if not msg:
                        continue
                    embed.insert_field_at(0, name=name, value=msg)
            embeds.insert(0, embed)
            # await ctx.send(embed=embed)
            # await ctx.tick()
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            timeout=180,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @destiny.group(name="vendor")
    async def vendor(self, ctx: commands.Context) -> None:
        """
        Commands for looking up various vendor information
        """
        pass

    @vendor.command()
    @commands.bot_has_permissions(embed_links=True)
    async def eververse(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display items currently available on the Eververse in a menu.

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "3361454721", character)

    @vendor.command()
    @commands.bot_has_permissions(embed_links=True)
    async def rahool(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display Rahool's wares.

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "2255782930", character)

    @vendor.command(name="banshee-44", aliases=["banshee"])
    @commands.bot_has_permissions(embed_links=True)
    async def banshee(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display Banshee-44's wares.

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "672118013", character)

    @vendor.command(name="ada-1", aliases=["ada"])
    @commands.bot_has_permissions(embed_links=True)
    async def ada_1_inventory(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display Ada-1's wares

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "350061650", character)

    @vendor.command(name="saint-14", aliases=["saint"])
    @commands.bot_has_permissions(embed_links=True)
    async def saint_14_inventory(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display Saint-14's wares

        `[character_class]` Which class you want to see the inventory for.
        """
        if not await self.api.has_oauth(ctx):
            return
        await self.vendor_menus(ctx, "765357505", character)

    @vendor.command(name="search")
    @commands.bot_has_permissions(embed_links=True)
    async def vendor_search(
        self,
        ctx: commands.Context,
        vendor: str,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display any vendors wares.

        `<vendor>` - The vendor whose inventory you want to see.
        """
        if not await self.api.has_oauth(ctx):
            return
        if not vendor.isdigit():
            possible_options = await self.api.search_definition("DestinyVendorDefinition", vendor)
            vendor = list(possible_options.keys())[0]
        await self.vendor_menus(ctx, vendor, character)

    @vendor_search.autocomplete("vendor")
    async def find_vendor(self, interaction: discord.Interaction, current: str):
        possible_options = await self.api.search_definition("DestinyVendorDefinition", current)
        choices = []
        for key, choice in possible_options.items():
            name = choice["displayProperties"]["name"]
            if not name:
                continue
            if not choice["enabled"]:
                continue
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=key))
        return choices[:25]

    @destiny.group(name="random")
    async def destiny_random(self, ctx: commands.Context):
        """Get Random Items"""
        pass

    async def get_random_item(self, weapons_or_class: DestinyRandomConverter, tier_type: int):
        data = await self.api.get_entities("DestinyInventoryItemDefinition")
        pool = []
        for key, value in data.items():
            if value["inventory"]["tierType"] != tier_type:
                continue
            if weapons_or_class.value == 3 and value["itemType"] != 3:
                continue
            if weapons_or_class.value in (0, 1, 2):
                if value["itemType"] != 2:
                    continue
                if value["classType"] != weapons_or_class.value:
                    continue
            pool.append(key)
        return data[random.choice(pool)]

    @destiny_random.command(name="exotic")
    async def random_exotic(
        self,
        ctx: commands.Context,
        weapons_or_class: DestinyRandomConverter,
    ):
        """
        Get a random Exotic Weapon or choose a specific Class
        to get a random armour piece
        """
        async with ctx.typing(ephemeral=False):
            item = await self.get_random_item(weapons_or_class, 6)
            em = discord.Embed(title=item["displayProperties"]["name"], colour=0xF1C40F)
            if "flavorText" in item:
                em.description = item["flavorText"]
            if item["displayProperties"]["hasIcon"]:
                em.set_thumbnail(url=IMAGE_URL.join(URL(item["displayProperties"]["icon"])))
            if "screenshot" in item:
                em.set_image(url=IMAGE_URL.join(URL(item["screenshot"])))
        await ctx.send(embed=em)

    @destiny.command(name="nightfall", aliases=["nf"])
    async def d2_nightfall(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ):
        """
        Get information about this weeks Nightfall activity
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            embeds = []
            try:
                milestones = await self.api.get_milestones(user)
                chars = await self.api.get_characters(user)

                await self.api.save(milestones, "milestones.json")
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            # nightfalls = milestones["1942283261"]

            activities = {nf["activityHash"]: nf for nf in milestones["2029743966"]["activities"]}
            nf_hashes = {}
            for char_id, av in chars["characterActivities"]["data"].items():
                if character and character != char_id:
                    continue
                for act in av["availableActivities"]:
                    if act["activityHash"] in activities:
                        nf_hashes[act["activityHash"]] = act

            for nf_id, nf in nf_hashes.items():
                embed = await self.make_activity_embed(ctx, nf_id, nf, chars)
                if embed is not None:
                    embeds.append(embed)

                # embed.add_field(name=name, value=mod_string[:1024])
            # embed.title = nf_desc

        await BaseMenu(
            source=BasePages(
                pages=embeds,
                use_author=True,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @destiny.command(name="activities")
    async def d2_activities(
        self,
        ctx: commands.Context,
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ):
        """
        Get information about available activities
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            embeds = []
            try:
                milestones = await self.api.get_milestones(user)
                chars = await self.api.get_characters(user)

                await self.api.save(milestones, "milestones.json")
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            for char_id, av in chars["characterActivities"]["data"].items():
                if character and character != char_id:
                    continue
                for act in av["availableActivities"]:
                    embed = await self.make_activity_embed(ctx, act["activityHash"], act, chars)
                    if embed is not None:
                        embeds.append(embed)

                # embed.add_field(name=name, value=mod_string[:1024])
            # embed.title = nf_desc

        await BaseMenu(
            source=BasePages(
                pages=embeds,
                use_author=True,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    async def check_character_completion(self, activity_hash: int, chars: dict) -> str:
        msg = ""
        class_info = await self.api.get_entities("DestinyClassDefinition")
        emojis = {
            True: "\N{WHITE HEAVY CHECK MARK}",
            False: "\N{CROSS MARK}",
        }
        reset = ""
        ms_group = {}
        for char_id, data in chars["characterProgressions"]["data"].items():
            class_name = (
                class_info[str(chars["characters"]["data"][char_id]["classHash"])]
                .get("displayProperties", {})
                .get("name", "")
            )
            done = ""
            ms_data = await self.api.get_entities("DestinyMilestoneDefinition")
            for ms_hash, ms in data["milestones"].items():
                for activity in ms.get("activities", []):
                    if activity["activityHash"] != activity_hash:
                        continue
                    ms_name = (
                        ms_data.get(str(ms_hash), {}).get("displayProperties", {}).get("name")
                    )
                    if ms_hash not in ms_group:
                        ms_group[ms_hash] = {"name": ms_name, "msg": ""}
                    if "endDate" in ms:
                        reset_dt = datetime.datetime.strptime(
                            ms["endDate"], "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=datetime.timezone.utc)
                        reset = discord.utils.format_dt(reset_dt, "R")
                    if "phases" in activity:
                        done = "-".join(emojis[phase["complete"]] for phase in activity["phases"])
                        ms_group[ms_hash]["msg"] += f"- {class_name}\n{done}\n"
                    elif "challenges" in activity:
                        done = "-".join(
                            emojis[challenge["objective"]["complete"]]
                            for challenge in activity["challenges"]
                        )
                        # is_complete = activity["challenges"][0]["objective"]["complete"]
                        # done = emojis[is_complete]
                        ms_group[ms_hash]["msg"] += f"- {class_name} - {done}\n"
                    else:
                        ms_group[ms_hash]["msg"] += f"- {class_name} - \N{WHITE HEAVY CHECK MARK}"

                    # done = emojis[activity["isCompleted"]]
        msg = "\n".join(f"{k['name']}\n{k['msg']}" for k in ms_group.values())
        if reset:
            msg += _("Resets {reset}\n").format(reset=reset)
        return msg

    async def make_activity_embed(
        self, ctx: commands.Context, activity_hash: int, activity_data: dict, chars: dict
    ) -> Optional[discord.Embed]:
        activity = await self.api.get_definition("DestinyActivityDefinition", [activity_hash])
        activity = activity[str(activity_hash)]
        mod_hashes = activity_data.get("modifierHashes", [])
        mods = None
        if mod_hashes:
            mods = await self.api.get_definition("DestinyActivityModifierDefinition", mod_hashes)
        ssdp = activity.get("selectionScreenDisplayProperties", {}).get("description", "") + "\n"
        mod_string = ""
        if ssdp:
            mod_string += ssdp
        if "recommendedLight" in activity_data:
            recommended_power = activity_data["recommendedLight"]
            mod_string += _("Recommended Power Level: {power}\n").format(power=recommended_power)
        embed = discord.Embed(
            colour=await self.bot.get_embed_colour(ctx),
        )
        name = activity["displayProperties"]["name"]
        embed.title = activity["displayProperties"]["description"]
        if activity["displayProperties"]["hasIcon"]:
            embed.set_author(
                name=name,
                icon_url=IMAGE_URL.join(URL(activity["displayProperties"]["icon"])),
            )
        else:
            embed.set_author(name=name)
        if "pgcrImage" in activity:
            embed.set_image(url=IMAGE_URL.join(URL(activity["pgcrImage"])))
        if mods:
            for mod in mods.values():
                mod_name = mod["displayProperties"]["name"]
                if not mod_name:
                    continue
                if not mod["displayInActivitySelection"] and mod["displayInNavMode"]:
                    continue
                mod_desc = re.sub(r"\W?\[[^\[\]]+\]", "", mod["displayProperties"]["description"])
                mod_desc = await self.api.replace_string(ctx.author, mod_desc)
                mod_desc = re.sub(r"\n\n", "\n", mod_desc)
                mod_desc = re.sub(r"\n", "\n - ", mod_desc)
                # mod_icon = IMAGE_URL + mod.get("displayProperties", {}).get("icon", '')

                mod_string += f"- {mod_name}\n - {mod_desc}\n"
                # mod_string += f"> {mod_name}\n {mod_desc}\n\n"
        if activity["rewards"]:
            reward_hashes = set()
            for reward_type in activity["rewards"]:
                for reward in reward_type["rewardItems"]:
                    reward_hashes.add(reward["itemHash"])
            rewards = await self.api.get_definition(
                "DestinyInventoryItemLiteDefinition", list(reward_hashes)
            )
            msg = ""
            for data in rewards.values():
                msg += data["displayProperties"]["name"] + "\n"
            msg = await self.api.replace_string(ctx.author, msg)
            embed.add_field(name=_("Rewards"), value=msg)
        completion = await self.check_character_completion(activity_hash, chars)
        if completion:
            embed.add_field(name=_("Completion"), value=completion)
        embed.description = mod_string
        return embed

    # @destiny.command(name="dungeons")
    async def dungeons(self, ctx: commands.Context):
        """
        Show your current Dungeon completion state
        """
        if not await self.api.has_oauth(ctx):
            return
        raid_milestones = {
            "1742973996",  # Shattered Throne
            "422102671",  # Pit of Heresy
            "478604913",  # Prophecy
            "1092691445",  # Grasp of Avarice
            "3618845105",  # Duality
            "526718853",  # Spire of the Watcher
            "390471874",  # Ghosts of the Deep
            "3921784328",  # Warlord's Ruin
        }
        async with ctx.typing(ephemeral=False):
            ms_defs = await self.api.get_definition(
                "DestinyMilestoneDefinition", list(raid_milestones)
            )
            try:
                chars = await self.api.get_characters(ctx.author)
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            em = discord.Embed()
            em.set_author(name=_("Dungeon Completion State"))
            act_hashes = [
                r["activityHash"] for act in ms_defs.values() for r in act.get("activities", [])
            ]
            activities = await self.api.get_definition("DestinyActivityDefinition", act_hashes)
            embeds = []
            for raid in ms_defs.values():
                msg = ""
                raid_name = raid.get("displayProperties", {}).get("name")
                for act in raid.get("activities", []):
                    raid_hash = act["activityHash"]
                    completion = await self.check_character_completion(raid_hash, chars)
                    if not completion:
                        continue
                    current_act = act
                    for char_id, data in chars["characterProgressions"]["data"].items():
                        ms = data["milestones"].get(str(raid["hash"]))
                        if not ms:
                            continue
                        for actual_act in ms.get("activities", []):
                            if act["activityHash"] == actual_act["activityHash"]:
                                current_act = actual_act
                                break
                    embeds.append(
                        await self.make_activity_embed(ctx, raid_hash, current_act, chars)
                    )
                    activity_name = (
                        activities.get(str(raid_hash), {}).get("displayProperties", {}).get("name")
                    )
                    activity_description = (
                        activities.get(str(raid_hash), {})
                        .get("displayProperties", {})
                        .get("description")
                    )
                    if activities.get(str(raid_hash), {}).get("tier") == -1:
                        activity_description = activity_name.split(":")[-1]
                    msg += f"**{activity_description}**\n{completion}"
                em.add_field(name=raid_name, value=msg)
                icon = raid.get("displayProperties", {}).get("icon")
                if icon:
                    em.set_thumbnail(url=IMAGE_URL.join(URL(icon)))
            embeds.insert(0, em)
        await BaseMenu(
            source=BasePages(
                pages=embeds,
                use_author=True,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @destiny.command(name="raids")
    async def raids(self, ctx: commands.Context):
        """
        Show your current raid completion state
        """
        if not await self.api.has_oauth(ctx):
            return
        raid_milestones = {
            "3181387331",  # Last Wish
            "2712317338",  # Garden of Salvation
            "541780856",  # Deep Stone Crypt
            "1888320892",  # Vault of Glass
            "2136320298",  # Vow of the Disciple
            "292102995",  # King's Fall
            "3699252268",  # Root of Nightmares
            "540415767",  # Crota's End
        }
        async with ctx.typing(ephemeral=False):
            ms_defs = await self.api.get_definition(
                "DestinyMilestoneDefinition", list(raid_milestones)
            )
            try:
                chars = await self.api.get_characters(ctx.author)
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            em = discord.Embed()
            em.set_author(name=_("Raid Completion State"))
            act_hashes = [
                r["activityHash"] for act in ms_defs.values() for r in act.get("activities", [])
            ]
            activities = await self.api.get_definition("DestinyActivityDefinition", act_hashes)
            embeds = []
            for raid in ms_defs.values():
                msg = ""
                raid_name = raid.get("displayProperties", {}).get("name")
                for act in raid.get("activities", []):
                    raid_hash = act["activityHash"]
                    completion = await self.check_character_completion(raid_hash, chars)
                    if not completion:
                        continue
                    current_act = act
                    for char_id, data in chars["characterProgressions"]["data"].items():
                        ms = data["milestones"].get(str(raid["hash"]))
                        for actual_act in ms.get("activities", []):
                            if act["activityHash"] == actual_act["activityHash"]:
                                current_act = actual_act
                                break
                    embeds.append(
                        await self.make_activity_embed(ctx, raid_hash, current_act, chars)
                    )
                    activity_name = (
                        activities.get(str(raid_hash), {}).get("displayProperties", {}).get("name")
                    )
                    activity_description = (
                        activities.get(str(raid_hash), {})
                        .get("displayProperties", {})
                        .get("description")
                    )
                    if activities.get(str(raid_hash), {}).get("tier") == -1:
                        activity_description = activity_name.split(":")[-1]
                    msg += f"**{activity_description}**\n{completion}"
                em.add_field(name=raid_name, value=msg)
                icon = raid.get("displayProperties", {}).get("icon")
                if icon:
                    em.set_thumbnail(url=IMAGE_URL.join(URL(icon)))
            embeds.insert(0, em)
        await BaseMenu(
            source=BasePages(
                pages=embeds,
                use_author=True,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @destiny.command(name="dares")
    async def d2_dares(self, ctx: commands.Context):
        """
        Get information about this weeks Nightfall activity
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(user)
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            acts = None
            dares_hash = 1030714181
            activity = await self.api.get_definition("DestinyActivityDefinition", [dares_hash])
            activity = activity[str(dares_hash)]
            for char_id, av in chars["characterActivities"]["data"].items():
                for act in av["availableActivities"]:
                    if act["activityHash"] == dares_hash:
                        acts = act
            if acts is None:
                await ctx.send(_("I could not find any Dares of Eternity information."))
                return
            embed = await self.make_activity_embed(ctx, dares_hash, acts, chars)
        await ctx.send(embed=embed)

    @destiny.command(name="craftable")
    async def d2_craftables(self, ctx: commands.Context):
        """
        Show which weapons you're missing deepsight resonance for crafting
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx):
            return
        embeds = []
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(user)

                await self.api.save(chars, "character.json")
            except Destiny2APIError as e:
                log.error(e, exc_info=True)
                await self.send_error_msg(ctx, e)
                return
            bnet_display_name = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayName"]
            bnet_code = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayNameCode"]
            bnet_name = f"{bnet_display_name}#{bnet_code}"
            await self.api.save(chars, "characters.json")
            craftables = chars["profileRecords"]["data"]
            hashes = []
            for record_hash, data in craftables["records"].items():
                if data["state"] != 4:
                    continue
                if not data.get("objectives", []):
                    continue
                objective = data["objectives"][0]
                if not objective["complete"]:
                    hashes.append(record_hash)
            weapon_info = await self.api.get_definition("DestinyRecordDefinition", hashes)
            entity = await self.api.get_entities("DestinyPresentationNodeDefinition")
            presentation_node_hashes = set()
            weapon_slots = {
                127506319,  # Primary Weapon Patterns
                3289524180,  # Special Weapon Patterns
                1464475380,  # Heavy Weapon Patterns
            }
            weapon_types = {}
            for k, v in entity.items():
                if not any(i in v.get("parentNodeHashes", []) for i in weapon_slots):
                    continue
                presentation_node_hashes.add(int(k))
                weapon_types[int(k)] = {
                    "name": v.get("displayProperties", {}).get("name"),
                    "value": "",
                }
            log.trace("Presentation Node %s", presentation_node_hashes)
            for r_hash, i in weapon_info.items():
                if not any(h in i.get("parentNodeHashes", []) for h in presentation_node_hashes):
                    continue
                for h in i.get("parentNodeHashes", []):
                    if h not in weapon_types:
                        continue
                    state = craftables["records"][str(r_hash)]
                    objective = state.get("objectives", [])
                    if not objective:
                        continue
                    progress = objective[0]["progress"]
                    completion = objective[0]["completionValue"]
                    state_str = f"{progress}/{completion}"
                    weapon_types[h]["value"] += f"{state_str} - {i['displayProperties']['name']}\n"

            em = discord.Embed(
                title=_("Missing Craftable Weapons"),
                colour=await self.bot.get_embed_colour(ctx),
            )

            for r_hash, field in weapon_types.items():
                if len(em.fields) > 20 or len(em) >= 4000:
                    embeds.append(em)
                    em = discord.Embed(
                        title=_("Missing Craftable Weapons"),
                        colour=await self.bot.get_embed_colour(ctx),
                    )
                if field["value"] and len(field["value"]) < 1024:
                    em.add_field(name=field["name"], value=field["value"])
                elif len(field["value"]) > 1024:
                    for page in pagify(field["value"], page_length=1024):
                        if len(em.fields) > 20 or len(em) >= 4000:
                            embeds.append(em)
                            em = discord.Embed(
                                title=_("Missing Craftable Weapons"),
                                colour=await self.bot.get_embed_colour(ctx),
                            )
                        em.add_field(name=field["name"], value=page)
            embeds.append(em)
        if not embeds:
            await ctx.send("You have all craftable weapons available! :)")
            return

        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    async def make_loadout_embeds(self, chars: dict) -> Dict[int, discord.Embed]:
        icons = await self.api.get_entities("DestinyLoadoutIconDefinition")
        names = await self.api.get_entities("DestinyLoadoutNameDefinition")
        bnet_display_name = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayName"]
        bnet_code = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayNameCode"]
        bnet_name = f"{bnet_display_name}#{bnet_code}"
        membership_type = chars["profile"]["data"]["userInfo"]["membershipType"]
        ret = {"membership_type": membership_type}
        for char_id, loadouts in chars["characterLoadouts"]["data"].items():
            ret[char_id] = {"embeds": [], "char_info": ""}
            char = chars["characters"]["data"][char_id]
            race = (await self.api.get_definition("DestinyRaceDefinition", [char["raceHash"]]))[
                str(char["raceHash"])
            ]
            gender = (
                await self.api.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            )[str(char["genderHash"])]
            char_class = (
                await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
            )[str(char["classHash"])]
            info = "{race} {gender} {char_class} ".format(
                race=race["displayProperties"]["name"],
                gender=gender["displayProperties"]["name"],
                char_class=char_class["displayProperties"]["name"],
            )
            ret[char_id]["char_info"] = info
            for loadout in loadouts["loadouts"]:
                name = names.get(str(loadout["nameHash"]))
                icon = icons.get(str(loadout["iconHash"]))
                icon_url = IMAGE_URL.join(URL(icon["iconImagePath"])) if icon else None
                loadout_name = name["name"] if name else _("Empty Loadout")
                colour_hash = loadout["colorHash"]
                colour = LOADOUT_COLOURS.get(str(colour_hash))
                embed = discord.Embed(title=loadout_name, description=info, colour=colour)
                embed.set_author(
                    name=_("{name} Loadouts").format(name=bnet_name), icon_url=icon_url
                )
                if icon_url:
                    embed.set_thumbnail(url=icon_url)
                items = {
                    i["itemInstanceId"]: {"perk_hashes": i["plugItemHashes"], "item_info": {}}
                    for i in loadout["items"]
                }
                for item in chars["characterInventories"]["data"][char_id]["items"]:
                    if item.get("itemInstanceId", None) in items:
                        items[item["itemInstanceId"]]["item_info"] = item
                for item in chars["characterEquipment"]["data"][char_id]["items"]:
                    if item.get("itemInstanceId", None) in items:
                        items[item["itemInstanceId"]]["item_info"] = item
                # all_perks = set()
                all_items = set()
                for i in items.values():
                    item_hash = i["item_info"].get("itemHash", None)
                    if item_hash:
                        all_items.add(item_hash)
                    for p in i["perk_hashes"]:
                        all_items.add(p)
                inventory = await self.api.get_definition(
                    "DestinyInventoryItemDefinition", list(all_items)
                )
                for data in items.values():
                    item_hash = data["item_info"].get("itemHash", None)
                    if not item_hash:
                        continue
                    item = inventory.get(str(item_hash), {})
                    if not item:
                        continue
                    item_name = item.get("displayProperties", {}).get("name", None)
                    item_type = item.get("itemTypeDisplayName", "test")
                    msg = ""
                    for plug in data["perk_hashes"]:
                        plug_info = inventory.get(str(plug), None)
                        if plug_info is None:
                            continue
                        mod_name = plug_info["displayProperties"]["name"]
                        msg += f"{mod_name}\n"
                    embed.add_field(name=item_type, value=f"{item_name}\n{msg}")
                ret[char_id]["embeds"].append(embed)
        return ret

    @destiny.group(aliases=["loadouts"])
    @commands.bot_has_permissions(embed_links=True)
    async def loadout(self, ctx: commands.Context) -> None:
        """
        Commands for interacting with your loadouts
        """
        pass

    @loadout.command(name="equip")
    async def loadout_equip(
        self,
        ctx: commands.Context,
        character: discord.app_commands.Transform[str, DestinyCharacter],
        loadout: int,
    ):
        """
        Equip a loadout on a specific character

        `<character>` The character you want to select a loadout for
        `<loadout>` The loadout you want to equip
        """
        if not await self.api.has_oauth(ctx):
            return
        loadout -= 1
        async with ctx.typing(ephemeral=False):
            try:
                components = DestinyComponents(
                    DestinyComponentType.characters, DestinyComponentType.character_loadouts
                )
                chars = None
                if ctx.author.id in self._loadout_temp:
                    chars = self._loadout_temp[ctx.author.id]
                    if datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.strptime(
                        chars["responseMintedTimestamp"], "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).replace(tzinfo=datetime.timezone.utc) > datetime.timedelta(minutes=5):
                        chars = None
                if chars is None:
                    try:
                        chars = await self.api.get_characters(ctx.author, components)
                        await self.api.save(chars, "character.json")
                    except Destiny2APIError as e:
                        log.error(e, exc_info=True)
                        await self.send_error_msg(ctx, e)
                        return
                    self._loadout_temp[ctx.author.id] = chars
                character_id = character
                membership_type = chars["characters"]["data"][character_id]["membershipType"]
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            try:
                await self.api.equip_loadout(ctx.author, loadout, character_id, membership_type)
            except Destiny2APIError as e:
                if ctx.author.id in self._loadout_temp:
                    del self._loadout_temp[ctx.author.id]
                await ctx.send(f"There was an error equipping that loadout: {e}")
                return
            loadout_names = await self.api.get_entities("DestinyLoadoutNameDefinition")
            loadout_name_hash = chars["characterLoadouts"]["data"][character_id]["loadouts"][
                loadout
            ]["nameHash"]
            loadout_name = loadout_names.get(str(loadout_name_hash), {"name": _("Empty Loadout")})[
                "name"
            ]
        if ctx.author.id in self._loadout_temp:
            del self._loadout_temp[ctx.author.id]
        await ctx.send(f"Equipped loadout {loadout+1}. {loadout_name}")

    @loadout_equip.autocomplete("loadout")
    async def find_loadout(self, interaction: discord.Interaction, current: str):
        loadout_names = await self.api.get_entities("DestinyLoadoutNameDefinition")
        components = DestinyComponents(
            DestinyComponentType.characters, DestinyComponentType.character_loadouts
        )
        chars = None
        if interaction.user.id in self._loadout_temp:
            chars = self._loadout_temp[interaction.user.id]
            if datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.strptime(
                chars["responseMintedTimestamp"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=datetime.timezone.utc) > datetime.timedelta(minutes=5):
                chars = None
        if chars is None:
            try:
                chars = await self.api.get_characters(interaction.user, components)
            except Destiny2APIError:
                return [
                    app_commands.Choice(
                        name=_("I could not find any loadout information"), value=-1
                    )
                ]
            self._loadout_temp[interaction.user.id] = chars
        character_id = interaction.namespace.character
        # log.info(f"{character_id=}")
        choices = []
        for index, loadout in enumerate(
            chars["characterLoadouts"]["data"][str(character_id)]["loadouts"]
        ):
            name = loadout_names.get(str(loadout["nameHash"]), {}).get("name", _("Empty Loadout"))
            full_name = f"{index+1}. {name}"
            if current.lower() in full_name.lower():
                choices.append(app_commands.Choice(name=full_name, value=index + 1))
        return choices[:25]

    @loadout.command(name="view")
    async def loadout_view(self, ctx: commands.Context) -> None:
        """
        Display a menu of each character's equipped weapons and their info

        `[full=False]` Display full information about weapons equipped.
        `[user]` A member on the server who has setup their account on this bot.
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx, user):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(user)

            except Destiny2APIError as e:
                # log.debug(e)
                await self.send_error_msg(ctx, e)
                return
            embeds = await self.make_loadout_embeds(chars)
        await BaseMenu(
            source=LoadoutPages(
                loadout_info=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @loadout.command(name="equipped")
    async def loadout_equipped(self, ctx: commands.Context, full: Optional[bool] = False):
        """
        Display a menu of each character's equipped weapons and their info

        `[full=False]` Display full information about weapons equipped.
        `[user]` A member on the server who has setup their account on this bot.
        """
        user = ctx.author
        if not await self.api.has_oauth(ctx, user):
            return
        async with ctx.typing(ephemeral=False):
            try:
                chars = await self.api.get_characters(user)

            except Destiny2APIError as e:
                # log.debug(e)
                await self.send_error_msg(ctx, e)
                return
            embeds = []
            bnet_display_name = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayName"]
            bnet_code = chars["profile"]["data"]["userInfo"]["bungieGlobalDisplayNameCode"]
            bnet_name = f"{bnet_display_name}#{bnet_code}"
            for char_id, char in chars["characters"]["data"].items():
                info = ""
                race = (
                    await self.api.get_definition("DestinyRaceDefinition", [char["raceHash"]])
                )[str(char["raceHash"])]
                gender = (
                    await self.api.get_definition("DestinyGenderDefinition", [char["genderHash"]])
                )[str(char["genderHash"])]
                char_class = (
                    await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
                )[str(char["classHash"])]
                info += "{race} {gender} {char_class} ".format(
                    race=race["displayProperties"]["name"],
                    gender=gender["displayProperties"]["name"],
                    char_class=char_class["displayProperties"]["name"],
                )
                titles = ""
                title_name = ""
                if "titleRecordHash" in char:
                    # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
                    char_title = (
                        await self.get_definition(
                            "DestinyRecordDefinition", [char["titleRecordHash"]]
                        )
                    )[str(char["titleRecordHash"])]
                    title_info = "**{title_name}**\n{title_desc}\n"
                    try:
                        gilded = ""
                        is_gilded, count = await self.api.check_gilded_title(chars, char_title)
                        if is_gilded:
                            gilded = _("Gilded ")
                        title_name = (
                            f"{gilded}"
                            + char_title["titleInfo"]["titlesByGenderHash"][
                                str(char["genderHash"])
                            ]
                            + f"{count}"
                        )
                        title_desc = char_title["displayProperties"]["description"]
                        titles += title_info.format(title_name=title_name, title_desc=title_desc)
                    except KeyError:
                        pass
                embed = discord.Embed(title=info)
                embed.set_author(name=bnet_name, icon_url=user.display_avatar)
                if "emblemPath" in char:
                    embed.set_thumbnail(url=IMAGE_URL.join(URL(char["emblemPath"])))
                if titles:
                    # embed.add_field(name=_("Titles"), value=titles)
                    embed.set_author(
                        name=f"{bnet_name} ({title_name})", icon_url=user.display_avatar
                    )
                char_items = chars["characterEquipment"]["data"][char_id]["items"]
                item_list = [i["itemHash"] for i in char_items]
                # log.debug(item_list)
                items = await self.api.get_definition("DestinyInventoryItemDefinition", item_list)
                # log.debug(items)
                weapons = ""
                for item_hash, data in items.items():
                    # log.debug(data)
                    instance_id = None
                    for item in char_items:
                        # log.debug(item)
                        if data["hash"] == item["itemHash"]:
                            instance_id = item["itemInstanceId"]
                    item_instance = chars["itemComponents"]["instances"]["data"][instance_id]
                    if not item_instance["isEquipped"]:
                        continue
                    name = data["displayProperties"]["name"]
                    if data["equippable"] and data["itemType"] == 3:
                        desc = data["displayProperties"]["description"]
                        item_type = data["itemTypeAndTierDisplayName"]
                        try:
                            light = item_instance["primaryStat"]["value"]
                        except KeyError:
                            light = ""
                        perk_list = chars["itemComponents"]["perks"]["data"][instance_id]["perks"]
                        perk_hashes = [p["perkHash"] for p in perk_list]
                        perk_data = await self.api.get_definition(
                            "DestinySandboxPerkDefinition", perk_hashes
                        )
                        perks = ""
                        for perk_hash, perk in perk_data.items():
                            properties = perk["displayProperties"]
                            if "name" in properties and "description" in properties:
                                if full:
                                    perks += "**{0}** - {1}\n".format(
                                        properties["name"], properties["description"]
                                    )
                                else:
                                    perks += "- **{0}**\n".format(properties["name"])

                        weapons += f"{name}: **{light}** {item_type}\n"
                    elif data["equippable"] and data["itemType"] == 2:
                        mod_list = chars["itemComponents"]["sockets"]["data"][instance_id][
                            "sockets"
                        ]
                        mod_hashes = [p["plugHash"] for p in mod_list if "plugHash" in p]
                        mod_data = await self.api.get_definition(
                            "DestinyInventoryItemDefinition", mod_hashes
                        )
                        mods = ""
                        for mod_hash, mod in mod_data.items():
                            properties = mod["displayProperties"]
                            if "name" in properties:
                                mods += properties["name"] + "\n"
                        field = f"{name}\n{mods}"
                        embed.add_field(name=data["itemTypeDisplayName"], value=field)
                        pass
                if weapons:
                    embed.add_field(name=_("Weapons"), value=weapons)
                    # embed.add_field(name=name, value=value, inline=True)
                # log.debug(data)
                stats_str = ""
                for stat_hash, value in char["stats"].items():
                    stat_info = (
                        await self.api.get_definition("DestinyStatDefinition", [stat_hash])
                    )[str(stat_hash)]
                    stat_name = stat_info["displayProperties"]["name"]
                    prog = "█" * int(value / 10)
                    empty = "░" * int((100 - value) / 10)
                    bar = f"{prog}{empty}"
                    if stat_hash == "1935470627":
                        artifact_bonus = chars["profileProgression"]["data"]["seasonalArtifact"][
                            "powerBonus"
                        ]
                        bar = _("Artifact Bonus: {bonus}").format(bonus=artifact_bonus)
                    stats_str += f"{stat_name}: **{value}** \n{bar}\n"
                embed.description = stats_str
                embed = await self.api.get_char_colour(embed, char)

                embeds.append(embed)
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @destiny.command()
    @commands.bot_has_permissions(
        embed_links=True,
    )
    async def history(
        self,
        ctx: commands.Context,
        activity: discord.app_commands.Transform[DestinyActivityModeType, DestinyActivity],
        character: Optional[discord.app_commands.Transform[str, DestinyCharacter]] = None,
    ) -> None:
        """
        Display a menu of each character's last 5 activities

        `<activity>` The activity type to display stats on available types include:
        all, story, strike, raid, allpvp, patrol, allpve, control, clash,
        crimsondoubles, nightfall, heroicnightfall, allstrikes, ironbanner, allmayhem,
        supremacy, privatematchesall, survival, countdown, trialsofthenine, social,
        trialscountdown, trialssurvival, ironbannercontrol, ironbannerclash,
        ironbannersupremacy, scorednightfall, scoredheroicnightfall, rumble, alldoubles,
        doubles, privatematchesclash, privatematchescontrol, privatematchessupremacy,
        privatematchescountdown, privatematchessurvival, privatematchesmayhem,
        privatematchesrumble, heroicadventure, showdown, lockdown, scorched,
        scorchedteam, gambit, allpvecompetitive, breakthrough, blackarmoryrun,
        salvage, ironbannersalvage, pvpcompetitive, pvpquickplay, clashquickplay,
        clashcompetitive, controlquickplay, controlcompetitive, gambitprime,
        reckoning, menagerie, vexoffensive, nightmarehunt, elimination, momentum,
        dungeon, sundial, trialsofosiris
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            user = ctx.author
            try:
                chars = await self.api.get_characters(user)

            except Destiny2APIError as e:
                # log.debug(e)
                await self.send_error_msg(ctx, e)
                return
            RAID = {
                "assists": _("Assists"),
                "kills": _("Kills"),
                "deaths": _("Deaths"),
                "opponentsDefeated": _("Opponents Defeated"),
                "efficiency": _("Efficiency"),
                "killsDeathsRatio": _("KDR"),
                "killsDeathsAssists": _("KDA"),
                "score": _("Score"),
                "activityDurationSeconds": _("Duration"),
                "playerCount": _("Player Count"),
                "teamScore": _("Team Score"),
                "completed": _("Completed"),
            }
            embeds = []
            for char_id, char in chars["characters"]["data"].items():
                if character and char_id != character:
                    continue
                # log.debug(char)
                char_info = ""
                char_class = (
                    await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
                )[str(char["classHash"])]
                char_info += "{user} - {char_class} ".format(
                    user=user.display_name,
                    char_class=char_class["displayProperties"]["name"],
                )
                try:
                    data = await self.api.get_activity_history(user, char_id, activity)
                except Exception:
                    log.error(
                        "Something went wrong I couldn't get info on character %s for activity %s",
                        char_id,
                        activity,
                    )
                    continue
                if not data:
                    continue

                for activities in data["activities"]:
                    activity_hash = str(activities["activityDetails"]["directorActivityHash"])
                    activity_data = (
                        await self.api.get_definition("DestinyActivityDefinition", [activity_hash])
                    )[str(activity_hash)]
                    embed = discord.Embed(
                        title=activity_data["displayProperties"]["name"] + f"- {char_info}",
                        description=activity_data["displayProperties"]["description"],
                    )

                    date = datetime.datetime.strptime(
                        activities["period"], "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc)
                    embed.timestamp = date
                    if activity_data["displayProperties"]["hasIcon"]:
                        embed.set_thumbnail(
                            url=IMAGE_URL.join(URL(activity_data["displayProperties"]["icon"]))
                        )
                    if activity_data.get("pgcrImage", None) is not None:
                        embed.set_image(url=IMAGE_URL.join(URL(activity_data["pgcrImage"])))
                    embed.set_author(name=char_info, icon_url=user.display_avatar)
                    for attr, name in RAID.items():
                        if activities["values"][attr]["basic"]["value"] < 0:
                            continue
                        embed.add_field(
                            name=name,
                            value=str(activities["values"][attr]["basic"]["displayValue"]),
                        )
                    embed = await self.api.get_char_colour(embed, char)

                    embeds.append(embed)
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @staticmethod
    async def get_extra_attrs(stat_type: str, attrs: dict) -> dict:
        """Helper function to receive the total attributes we care about"""
        EXTRA_ATTRS = {}
        if stat_type == "allPvECompetitive":
            EXTRA_ATTRS = {
                "winLossRatio": _("Win Loss Ratio"),
                "invasions": _("Invasions"),
                "invasionKills": _("Invasion Kills"),
                "invasionDeaths": _("Invasion Deaths"),
                "invaderDeaths": _("Invader Deaths"),
                "invaderKills": _("Invader Kills"),
                "primevalKills": _("Primeval Kills"),
                "blockerKills": _("Blocker Kills"),
                "mobKills": _("Mob Kills"),
                "highValueKills": _("High Value Targets Killed"),
                "motesPickedUp": _("Motes Picked Up"),
                "motesDeposited": _("Motes Deposited"),
                "motesDenied": _("Motes Denied"),
                "motesLost": _("Motes Lost"),
            }
        if stat_type == "allPvP":
            EXTRA_ATTRS = {"winLossRatio": _("Win Loss Ratio")}
        for k, v in EXTRA_ATTRS.items():
            attrs[k] = v
        return attrs

    async def build_character_stats(
        self, user: discord.Member, chars: dict, stat_type: str
    ) -> List[discord.Embed]:
        embeds: List[discord.Embed] = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            aggregate = {}
            acts = {}
            try:
                data = await self.api.get_historical_stats(user, char_id, 0)
                if stat_type == "raid":
                    aggregate = await self.api.get_aggregate_activity_history(user, char_id)
                    agg_hashes = [a["activityHash"] for a in aggregate["activities"]]
                    acts = await self.api.get_definition("DestinyActivityDefinition", agg_hashes)
            except Exception:
                log.error("Something went wrong I couldn't get info on character %s", char_id)
                continue
            if not data:
                continue
            try:
                if stat_type != "allPvECompetitive":
                    embed = await self.build_stat_embed_char_basic(
                        user, char, data, stat_type, aggregate, acts
                    )
                    embeds.append(embed)
                else:
                    data = data[stat_type]["allTime"]
                    embed = await self.build_stat_embed_char_gambit(user, char, data, stat_type)
                    embeds.append(embed)
            except Exception:
                log.error(
                    "User %s had an issue generating stats for character %s",
                    user.id,
                    char_id,
                    exc_info=True,
                )
                continue
        return embeds

    async def build_stat_embed_char_basic(
        self,
        user: discord.Member,
        char: dict,
        data: dict,
        stat_type: str,
        aggregate: dict,
        acts: dict,
    ) -> discord.Embed:
        char_info = ""
        race = (await self.api.get_definition("DestinyRaceDefinition", [char["raceHash"]]))[
            str(char["raceHash"])
        ]
        gender = (await self.api.get_definition("DestinyGenderDefinition", [char["genderHash"]]))[
            str(char["genderHash"])
        ]
        char_class = (
            await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
        )[str(char["classHash"])]
        char_info += "{race} {gender} {char_class} ".format(
            race=race["displayProperties"]["name"],
            gender=gender["displayProperties"]["name"],
            char_class=char_class["displayProperties"]["name"],
        )
        ATTRS = {
            "opponentsDefeated": _("Opponents Defeated"),
            "efficiency": _("Efficiency"),
            "bestSingleGameKills": _("Best Single Game Kills"),
            "bestSingleGameScore": _("Best Single Game Score"),
            "precisionKills": _("Precision Kills"),
            "longestKillSpree": _("Longest Killing Spree"),
            "longestSingleLife": _("Longest Single Life"),
            "totalActivityDurationSeconds": _("Total time playing"),
            "averageLifespan": _("Average Life Span"),
            "weaponBestType": _("Best Weapon Type"),
        }
        embed = discord.Embed(title=stat_type.title() + f" - {char_info}")
        raid_names = set()
        if stat_type == "raid":
            for agg in aggregate["activities"]:
                if agg["values"]["activityCompletions"]["basic"]["value"] > 0:
                    raid = acts.get(str(agg["activityHash"]), {})
                    if not raid:
                        continue
                    if raid["activityTypeHash"] != 2043403989:
                        continue
                    raid_names.add(raid["displayProperties"]["name"])
        if raid_names:
            description = "\n".join(n for n in raid_names)
            embed.description = _("__**Raids Completed:**__\n") + description
        embed.set_author(name=f"{user.display_name} - {char_info}", icon_url=user.display_avatar)
        kills = data[stat_type]["allTime"]["kills"]["basic"]["displayValue"]
        deaths = data[stat_type]["allTime"]["deaths"]["basic"]["displayValue"]
        assists = data[stat_type]["allTime"]["assists"]["basic"]["displayValue"]
        kda = f"{kills} | {deaths} | {assists}"
        embed.add_field(name=_("Kills | Deaths | Assists"), value=kda)
        if "emblemPath" in char:
            embed.set_thumbnail(url=IMAGE_URL.join(URL(char["emblemPath"])))
        for stat, values in data[stat_type]["allTime"].items():
            if values["basic"]["value"] < 0 or stat not in ATTRS:
                continue
            embed.add_field(name=ATTRS[stat], value=str(values["basic"]["displayValue"]))
        if "killsDeathsRatio" in data[stat_type] and "killsDeathsAssists" in data[stat_type]:
            kdr = data[stat_type]["killsDeathsRatio"]
            kda = data[stat_type]["killsDeathsAssists"]
            if kdr or kda:
                embed.add_field(name=_("KDR/KDA"), value=f"{kdr}/{kda}")
        if (
            "resurrectionsPerformed" in data[stat_type]
            and "resurrectionsReceived" in data[stat_type]
        ):
            res = data[stat_type]["resurrectionsPerformed"]
            resur = data[stat_type]["resurrectionsReceived"]
            if res or resur:
                embed.add_field(name=_("Resurrections/Received"), value=f"{res}/{resur}")
        return await self.api.get_char_colour(embed, char)

    async def build_stat_embed_char_gambit(
        self, user: discord.Member, char: dict, data: dict, stat_type: str
    ) -> discord.Embed:
        char_info = ""
        race = (await self.api.get_definition("DestinyRaceDefinition", [char["raceHash"]]))[
            str(char["raceHash"])
        ]
        gender = (await self.api.get_definition("DestinyGenderDefinition", [char["genderHash"]]))[
            str(char["genderHash"])
        ]
        char_class = (
            await self.api.get_definition("DestinyClassDefinition", [char["classHash"]])
        )[str(char["classHash"])]
        char_info += "{race} {gender} {char_class} ".format(
            race=race["displayProperties"]["name"],
            gender=gender["displayProperties"]["name"],
            char_class=char_class["displayProperties"]["name"],
        )
        ATTRS = {
            "opponentsDefeated": _("Opponents Defeated"),
            "efficiency": _("Efficiency"),
            "bestSingleGameKills": _("Best Single Game Kills"),
            "bestSingleGameScore": _("Best Single Game Score"),
            "precisionKills": _("Precision Kills"),
            "longestKillSpree": _("Longest Killing Spree"),
            "longestSingleLife": _("Longest Single Life"),
            "totalActivityDurationSeconds": _("Total time playing"),
            "averageLifespan": _("Average Life Span"),
            "weaponBestType": _("Best Weapon Type"),
            "winLossRatio": _("Win Loss Ratio"),
        }
        embed = discord.Embed(title=_("Gambit") + f" - {char_info}")
        embed.set_author(name=f"{user.display_name} - {char_info}", icon_url=user.display_avatar)
        kills = data["kills"]["basic"]["displayValue"]
        deaths = data["deaths"]["basic"]["displayValue"]
        assists = data["assists"]["basic"]["displayValue"]
        kda = f"{kills} | {deaths} | {assists}"
        embed.add_field(name=_("Kills | Deaths | Assists"), value=kda)
        small_blocker = data["smallBlockersSent"]["basic"]["displayValue"]
        med_blocker = data["mediumBlockersSent"]["basic"]["displayValue"]
        large_blocker = data["largeBlockersSent"]["basic"]["displayValue"]
        blockers = f"S {small_blocker}, M {med_blocker}, L {large_blocker}"
        embed.add_field(name=_("Blockers"), value=blockers)
        invasions = _("Invasions: {invasions}").format(
            invasions=data["invasions"]["basic"]["displayValue"]
        )
        invasion_kills = _("Kills: {kills}\nDeaths: {deaths}").format(
            kills=data["invasionKills"]["basic"]["displayValue"],
            deaths=data["invasionDeaths"]["basic"]["displayValue"],
        )
        embed.add_field(name=invasions, value=invasion_kills)
        invaders = _("Killed: {killed}\nKilled By: {by}").format(
            killed=data["invaderKills"]["basic"]["displayValue"],
            by=data["invaderDeaths"]["basic"]["displayValue"],
        )
        embed.add_field(name=_("Invaders"), value=invaders)
        motes_dep = data["motesDeposited"]["basic"]["value"]
        try:
            lost = 1 - (motes_dep / data["motesPickedUp"]["basic"]["value"])
            motes_lost = "{:.2%}".format(lost)
        except ZeroDivisionError:
            motes_lost = "0%"
        motes = _("{motes:,} ({lost} Lost)").format(motes=motes_dep, lost=motes_lost)
        embed.add_field(name=_("Motes Deposited"), value=motes)
        motes_denied = data["motesDenied"]["basic"]["value"]
        embed.add_field(name=_("Motes Denied"), value="{:,}".format(motes_denied))
        mob_kills = data["mobKills"]["basic"]["value"]
        primeval_kills = data["primevalKills"]["basic"]["value"]
        high_kills = data["highValueKills"]["basic"]["value"]
        kills_msg = _("Primevals: {prime:,}\nHigh Value Targets: {high:,}\nMobs: {mobs:,}").format(
            prime=primeval_kills, high=high_kills, mobs=mob_kills
        )
        embed.add_field(name=_("Kill Stats"), value=kills_msg)
        if "killsDeathsRatio" in data and "killsDeathsAssists" in data:
            kdr = data["killsDeathsRatio"]["basic"]["displayValue"]
            kda = data["killsDeathsAssists"]["basic"]["displayValue"]
            if kdr or kda:
                embed.add_field(name=_("KDR/KDA"), value=f"{kdr}/{kda}")
        if "resurrectionsPerformed" in data and "resurrectionsReceived" in data:
            res = data["resurrectionsPerformed"]["basic"]["displayValue"]
            resur = data["resurrectionsReceived"]["basic"]["displayValue"]
            if res or resur:
                embed.add_field(name=_("Resurrections/Received"), value=f"{res}/{resur}")
        if "emblemPath" in char:
            embed.set_thumbnail(url=IMAGE_URL.join(URL(char["emblemPath"])))
        for stat, values in data.items():
            if values["basic"]["value"] < 0 or stat not in ATTRS:
                continue
            embed.add_field(name=ATTRS[stat], value=str(values["basic"]["displayValue"]))

        return await self.api.get_char_colour(embed, char)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    @discord.app_commands.choices(
        stat_type=[
            discord.app_commands.Choice(name="allPvP", value="allPvP"),
            discord.app_commands.Choice(name="patrol", value="patrol"),
            discord.app_commands.Choice(name="raid", value="raid"),
            discord.app_commands.Choice(name="story", value="story"),
            discord.app_commands.Choice(name="allStrikes", value="allStrikes"),
            discord.app_commands.Choice(name="allPvE", value="allPvE"),
            discord.app_commands.Choice(name="allPvECompetitive", value="allPvECompetitive"),
        ]
    )
    async def stats(self, ctx: commands.Context, stat_type: StatsPage) -> None:
        """
        Display each character's stats for a specific activity
        `<stat_type>` The type of stats to display, available options are:
        `raid`, `pvp`, `pve`, patrol, story, gambit, and strikes
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            user = ctx.author
            try:
                chars = await self.api.get_characters(user)

            except Destiny2APIError as e:
                # log.debug(e)
                await self.send_error_msg(ctx, e)
                return
            # base stats should be available for all stat types
            embeds = await self.build_character_stats(user, chars, stat_type)

            if not embeds:
                msg = _("No stats could be found for that activity and character.")
                await ctx.send(msg)
                return
        await BaseMenu(
            source=BasePages(
                pages=embeds,
            ),
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    # @destiny.command()
    # @commands.bot_has_permissions(embed_links=True)
    async def weapons_test(self, ctx: commands.Context) -> None:
        """
        Get statistics about your top used weapons
        """
        if not await self.api.has_oauth(ctx):
            return
        async with ctx.typing(ephemeral=False):
            user = ctx.author
            try:
                chars = await self.api.get_characters(
                    user, components=DestinyComponents(DestinyComponentType.characters)
                )
                char_id = list(chars["characters"]["data"].keys())[0]
                weapons = await self.api.get_weapon_history(user, char_id)
            except Destiny2APIError as e:
                await self.send_error_msg(ctx, e)
                return
            weapon_hashes = [w["referenceId"] for w in weapons["weapons"]]
            weapon_def = await self.api.get_definition(
                "DestinyInventoryItemDefinition", weapon_hashes
            )
            msg = ""
            for we in weapon_def.values():
                msg += we["displayProperties"]["name"] + "\n"
        await ctx.send_interactive(list(pagify(msg)))

    @destiny.group(with_app_command=False)
    @commands.is_owner()
    async def manifest(self, ctx: commands.Context) -> None:
        """
        Destiny manifest commands

        The manifest is useful at improving lookup speed of items and other
        various functions of the cog.
        """
        pass

    @manifest.command(name="auto", with_app_command=False)
    @commands.is_owner()
    async def manifest_auto(self, ctx: commands.Context, auto: bool):
        """
        Setup the manifest to automatically download when an update is available.
        """
        await self.config.manifest_auto.set(auto)
        if auto:
            await ctx.send(_("I will automatically download manifest updates."))
        else:
            await ctx.send(_("I will **not** automatically download manifest updates."))

    @manifest.command(name="channel", with_app_command=False)
    @commands.is_owner()
    async def manifest_channel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Set a channel that will post when the manifest needs to be updated.
        """
        if channel is None:
            await self.config.manifest_channel.clear()
            await self.config.manifest_guild.clear()
            await ctx.send(_("I will not notify any channels about updated manifest versions."))
        else:
            await self.config.manifest_guild.set(channel.guild.id)
            await self.config.manifest_channel.set(channel.id)
            await ctx.send(
                _("I will notify {channel} when there is a manifest update.").format(
                    channel=channel.mention
                )
            )

    @manifest.command(name="cache", with_app_command=False)
    @commands.is_owner()
    async def manifest_cache_setup(self, ctx: commands.Context, enable: DestinyManifestCacheStyle):
        """
        Enable caching of the Destiny Manifest to improve response times

        `<enable>` Must be either `disable`, `lazy`, or `enable`.
            - `disable` disables caching of the Manifest meaning every command will load the
            manifest from disk.
            - `lazy` will cache the data after it has been looked at once, this is recommended.
            - `enable` will pre-emptively cache the data on cog load forcing all data
            to be in the cache. This can lead to excess unnecessary data being used.

        ⚠️Warning⚠️ - Enabling this can lead to higher than expected memory usage
        """
        await self.config.cache_manifest.set(enable.value)
        if enable.value == 1:
            msg = _("The manifest will cache itself after being used once.")
        elif enable.value == 2:
            msg = _("The manifest will cache itself whenever the cog is loaded.")
        else:
            msg = _("The manifest will not be cached.")
            self._manifest = {}
        await ctx.send(msg)

    @manifest.command(name="check", with_app_command=False)
    @commands.is_owner()
    async def manifest_download(self, ctx: commands.Context, d1: bool = False) -> None:
        """
        Check if the current manifest is up-to-date and optionally download
        the newest one.
        """
        if not d1:
            async with ctx.typing(ephemeral=False):
                error_str = _(
                    "You need to set your API authentication tokens with `[p]destiny token` first."
                )
                try:
                    manifest_data = await self.api.get_manifest_data()
                except Exception:
                    await ctx.send(error_str)
                    return
                if manifest_data is None:
                    return

                version = await self.config.manifest_version()
                if not version:
                    version = _("Not Downloaded")
                msg = _("Current manifest version is {version}.").format(version=version)
                redownload = _("re-download the")
                if manifest_data["version"] != version:
                    msg += _("\n\nThere is an update available to version {version}").format(
                        version=manifest_data["version"]
                    )
                    redownload = _("download the **new**")
            await ctx.send(msg)
            pred = await YesNoView().start(
                ctx,
                _("Would you like to {redownload} manifest?").format(redownload=redownload),
            )
            if pred:
                async with ctx.typing(ephemeral=False):
                    try:
                        version = await self.api.get_manifest()
                        response = _("Manifest Version {version} was downloaded.").format(
                            version=version
                        )
                    except Exception:
                        log.exception("Error getting destiny manifest")
                        response = _("There was an issue downloading the manifest.")
                await ctx.send(response)
            else:
                await ctx.send(_("I will not download the manifest."))
        else:
            try:
                version = await self.api.get_manifest(d1)
            except Exception:
                log.exception("Error getting D1 manifest")
                await ctx.send(_("There was an issue downloading the manifest."))
                return

    @destiny.command(with_app_command=False)
    @commands.is_owner()
    async def token(self, ctx: commands.Context) -> None:
        """
        Set the API tokens for Destiny 2's API

        Required information is found at:
        https://www.bungie.net/en/Application
        select **Create New App**
        Choose **Confidential** OAuth Client type
        Select the scope you would like the bot to have access to
        Set the redirect URL to https://localhost/
        NOTE: It is strongly recommended to use this command in DM
        """
        message = _(
            "1. Go to https://www.bungie.net/en/Application \n"
            "2. select **Create New App**\n"
            "3. Choose **Confidential** OAuth Client type\n"
            "4. Select the scope you would like the bot to have access to\n"
            "5. Set the redirect URL to https://localhost/\n"
            "6. Use `{prefix}set api bungie api_key YOUR_API_KEY client_id "
            "YOUR_CLIENT_ID client_secret YOUR_CLIENT_SECRET`\n"
            "NOTE: It is strongly recommended to use this command in DM."
        ).format(prefix=ctx.prefix)
        keys = {"api_key": "", "client_id": "", "client_secret": ""}
        view = SetApiView("bungie", keys)
        if await ctx.embed_requested():
            em = discord.Embed(description=message, colour=await ctx.bot.get_embed_colour(ctx))
            msg = await ctx.send(embed=em, view=view)
        else:
            msg = await ctx.send(message, view=view)
        await view.wait()
        await msg.edit(view=None)
