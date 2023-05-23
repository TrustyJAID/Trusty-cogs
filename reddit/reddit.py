import asyncio
from typing import Mapping, Optional

import aiohttp
import apraw
import discord
from apraw.models import Submission, Subreddit
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import bounded_gather

from .helpers import SubredditConverter, make_embed_from_submission
from .menus import BaseMenu, RedditMenu

log = getLogger("red.Trusty-cogs.reddit")
_ = Translator("Reddit", __file__)


@cog_i18n(_)
class Reddit(commands.Cog):
    """
    A cog to get information from the Reddit API
    """

    __version__ = "1.2.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.login = None
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.subreddits = {}
        self._streams = {}
        default = {"subreddits": {}}
        self.config.register_global(**default)
        self._ready: asyncio.Event = asyncio.Event()
        self.stream_loop.start()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs) -> None:
        """
        Nothing to delete
        """
        return

    @tasks.loop(seconds=300)
    async def stream_loop(self):
        if self.login:
            for sub, data in self.subreddits.items():
                if sub not in self._streams:
                    subreddit = await self.login.subreddit(data["name"])
                    self._streams[sub] = asyncio.create_task(self._run_subreddit_stream(subreddit))
                elif sub in self._streams and self._streams[sub].done():
                    subreddit = await self.login.subreddit(data["name"])
                    self._streams[sub] = asyncio.create_task(self._run_subreddit_stream(subreddit))

    @stream_loop.before_loop
    async def before_stream_loop(self):
        await self.bot.wait_until_red_ready()
        await self._ready.wait()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name == "reddit":
            try:
                await self.login.close()
                log.debug("Closed the reddit login.")
            except Exception:
                log.exception("Error closing the login.")
            for name, stream in self._streams.items():
                try:
                    stream.cancel()
                except Exception:
                    log.debug("Error closing stream in %s", name)
            await self.initialize()
            self.stream_loop.restart()

    async def cog_load(self) -> None:
        keys = await self.bot.get_shared_api_tokens("reddit")
        if not keys:
            return
        try:
            self.login = apraw.Reddit(
                client_id=keys["client_id"],
                client_secret=keys["client_secret"],
                password=keys["password"],
                username=keys["username"],
                user_agent=f"Trusty-cogs/{self.__version__} on {self.bot.user}",
            )
            log.debug("Logged into Reddit.")
            self.subreddits = await self.config.subreddits()
            self._ready.set()
        except KeyError:
            log.error(
                "You have not provided all the correct information I need to login to reddit."
            )
        except Exception:
            log.exception("Error logging into Reddit.")

    async def _run_subreddit_stream(self, subreddit: Subreddit) -> None:
        """
        A function to run the infinite loop of the subreddit stream and dispatch
        new posts as an event.
        """
        try:
            stream = subreddit.new.stream(skip_existing=True, max_wait=300)
            async for submission in stream:
                self.bot.dispatch("reddit_post", subreddit, submission)
        except aiohttp.ContentTypeError:
            log.debug("Stream recieved incorrect data type.")
            # attempt to create the stream again.
            self._streams[subreddit.id] = asyncio.create_task(
                self._run_subreddit_stream(subreddit)
            )
        except Exception:
            log.exception("Error in streams task.")
            return None

    @commands.Cog.listener()
    async def on_reddit_post(self, subreddit: Subreddit, submission: Submission) -> None:
        if subreddit.id not in self.subreddits:
            try:
                self._streams[subreddit.id].cancel()
            except Exception:
                log.exception("Error closing stream.")
            del self._streams[subreddit.id]
        else:
            tasks = []
            for channel_id in self.subreddits[subreddit.id]["channels"]:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    continue
                if channel.guild.me.is_timed_out():
                    continue
                chan_perms = channel.permissions_for(channel.guild.me)
                if not chan_perms.send_messages and not chan_perms.manage_webhooks:
                    continue
                use_embed = channel.permissions_for(channel.guild.me).embed_links
                contents = await make_embed_from_submission(channel, subreddit, submission)
                if not contents:
                    continue
                contents["subreddit"] = subreddit
                contents["submission"] = submission
                tasks.append(self.post_new_submissions(channel, contents, use_embed))
            await bounded_gather(*tasks, return_exceptions=True)

    async def post_new_submissions(
        self, channel: discord.TextChannel, contents: dict, use_embed: bool
    ) -> None:
        """
        A coroutine to handle multiple tasks at once
        """
        post_url = contents["content"]
        em = contents["embed"]
        subreddit = contents["subreddit"]
        try:
            if channel.permissions_for(channel.guild.me).embed_links:
                if use_embed:
                    await channel.send(post_url, embed=em)
                else:
                    await channel.send(post_url)
            elif channel.permissions_for(channel.guild.me).manage_webhooks:
                webhook = None
                for hook in await channel.webhooks():
                    if hook.name == channel.guild.me.name:
                        webhook = hook
                if webhook is None:
                    webhook = await channel.create_webhook(name=channel.guild.me.name)
                avatar = subreddit.community_icon
                if use_embed:
                    await webhook.send(
                        post_url,
                        username=subreddit.display_name_prefixed,
                        avatar_url=avatar,
                        embed=em,
                    )
                else:
                    await webhook.send(
                        post_url, username=subreddit.display_name_prefixed, avatar_url=avatar
                    )
            else:
                await channel.send(post_url)
        except Exception:
            msg = "{0} from <#{1}>({1})".format(post_url, channel.id)
            log.exception(msg)

    async def cog_unload(self) -> None:
        if self.login:
            try:
                await self.login.close()
                log.debug("Closed the reddit login.")
            except Exception:
                log.exception("Error closing the login.")
        for name, stream in self._streams.items():
            try:
                stream.cancel()
            except Exception:
                log.debug("Error closing stream in %s", name)

    @commands.group()
    async def redditset(self, ctx: commands.Context) -> None:
        """
        Commands for setting up the reddit cog
        """

    @redditset.command(name="post")
    @checks.mod_or_permissions(manage_channels=True)
    async def autopost_new_submissions(
        self,
        ctx: commands.Context,
        subreddit: SubredditConverter,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Setup a channel for automatically posting new subreddit submissions

        `<subreddit>` is the name of the subreddit you want to get updates on.
        `<channel>` is the channel where you want new subreddit posts to be put.
        """

        if channel is None:
            channel = ctx.channel
        if subreddit.id not in self.subreddits:
            self.subreddits[subreddit.id] = {
                "name": subreddit.display_name,
                "channels": [channel.id],
            }
            self._streams[subreddit.id] = asyncio.create_task(
                self._run_subreddit_stream(subreddit)
            )
            await self.config.subreddits.set_raw(subreddit.id, value=self.subreddits[subreddit.id])
        else:
            if channel.id not in self.subreddits[subreddit.id]["channels"]:
                self.subreddits[subreddit.id]["channels"].append(channel.id)
                subs = await self.config.subreddits()
                subs[subreddit.id]["channels"].append(channel.id)
                await self.config.subreddits.set(subs)
            else:
                return await ctx.send(
                    _("{sub} is already posting in {channel}.").format(
                        sub=subreddit.display_name_prefixed, channel=channel.mention
                    )
                )
        await ctx.send(
            ("I will now post new submissions to {sub} in {channel}").format(
                sub=subreddit.display_name_prefixed, channel=channel.mention
            )
        )

    @redditset.command(name="remove")
    @checks.mod_or_permissions(manage_channels=True)
    async def remove_autopost_new_submissions(
        self,
        ctx: commands.Context,
        subreddit: SubredditConverter,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Remove a channel from automatically posting new subreddit submissions

        `<subreddit>` is the name of the subreddit you want to get updates on.
        `<channel>` is the channel where you want new subreddit posts to be put.
        """
        if channel is None:
            channel = ctx.channel
        if subreddit.id not in self.subreddits:
            return await ctx.send(
                f"{subreddit.display_name_prefixed} is not posting in {channel.mention}."
            )
        else:
            if channel.id in self.subreddits[subreddit.id]["channels"]:
                self.subreddits[subreddit.id]["channels"].remove(channel.id)
                subs = await self.config.subreddits()
                subs[subreddit.id]["channels"].remove(channel.id)
                if len(subs[subreddit.id]["channels"]) == 0:
                    del subs[subreddit.id]
                    del self.subreddits[subreddit.id]
                    try:
                        self._streams[subreddit.id].cancel()
                        del self._streams[subreddit.id]
                    except Exception:
                        log.exception("Error closing stream")
                await self.config.subreddits.set(subs)
            else:
                return await ctx.send(
                    _("{sub} is not posting in {channel}.").format(
                        sub=subreddit.display_name_prefixed, channel=channel.mention
                    )
                )
        await ctx.send(
            ("I will stop posting new submissions to {sub} in {channel}").format(
                sub=subreddit.display_name_prefixed, channel=channel.mention
            )
        )

    @redditset.command()
    @commands.is_owner()
    async def creds(self, ctx: commands.Context) -> None:
        """
        How to setup login information for reddit.
        """
        msg = _(
            "1. Go to https://www.reddit.com/prefs/apps and select create another app...\n"
            "2. Give the app a name and description, specify that it's a script\n"
            "3. In the developed apps section under the apps name you provided before below `personal use script` "
            "copy that into `<client_id>` Use `https://127.0.0.1` or `https://localhost` for the redirect url.\n"
            "4. In the app box where it says `secret` copy the code after into `<client_secret>` if you don't see this click the edit button\n"
            "5. Fill out the rest of the following command with your accounts username and password\n"
            "NOTE: If you have 2FA enabled on your account this will not work, I'd recommend creating a new reddit "
            "account specifically for the bot if that's the case.\n"
            "`{prefix}set api reddit username <username> password <password> client_id <client_id> client_secret <client_secret>`"
        ).format(prefix=ctx.clean_prefix)
        await ctx.maybe_send_embed(msg)

    @commands.group()
    async def reddit(self, ctx: commands.Context) -> None:
        """reddit"""

    @reddit.command(name="hot")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def reddit_hot(self, ctx: commands.Context, subreddit: SubredditConverter) -> None:
        """
        Show 25 hotest posts on the desired subreddit
        """
        await ctx.typing()
        submissions = subreddit.hot()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="new")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def reddit_new(self, ctx: commands.Context, subreddit: SubredditConverter) -> None:
        """
        Show 25 newest posts on the desired subreddit
        """
        await ctx.typing()
        submissions = subreddit.new()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="top")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def reddit_top(self, ctx: commands.Context, subreddit: SubredditConverter) -> None:
        """
        Show 25 newest posts on the desired subreddit
        """
        await ctx.typing()
        submissions = subreddit.top()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="rising")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def reddit_rising(self, ctx: commands.Context, subreddit: SubredditConverter) -> None:
        """
        Show 25 newest posts on the desired subreddit
        """
        await ctx.typing()
        submissions = subreddit.rising()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="random")
    async def reddit_random(self, ctx: commands.Context, subreddit: SubredditConverter) -> None:
        """
        Pull a radom submission from the desired subreddit
        """
        await ctx.typing()
        submission = await subreddit.random()
        if submission.over_18 and not ctx.channel.is_nsfw():
            for i in range(0, 10):
                submission = await subreddit.random()
                if not submission.over_18:
                    break
        if submission.over_18 and not ctx.channel.is_nsfw():
            await ctx.send(
                _(
                    "I tried to pull a random submission but couldn't find "
                    "one not designated NSFW I can display in this channel."
                )
            )
            return
        data = await make_embed_from_submission(ctx.channel, subreddit, submission)
        if data:
            if ctx.channel.permissions_for(ctx.me).embed_links:
                await ctx.send(data["content"], embed=data["embed"])
            else:
                await ctx.send(data["content"])
        else:
            await ctx.send(_("I could not find a suitable random post on that subreddit."))
