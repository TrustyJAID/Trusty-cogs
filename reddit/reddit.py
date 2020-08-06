import discord
import logging
import apraw
import asyncio
import aiohttp

from typing import Optional

from apraw.models import Submission, Subreddit

from redbot.core import commands, checks, Config


from .menus import RedditMenu, BaseMenu
from .helpers import BASE_URL, make_embed_from_submission

log = logging.getLogger("red.Trusty-cogs.reddit")


class Reddit(commands.Cog):
    """
        A cog to get information from the Reddit API
    """

    __version__ = "1.0.2"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.login = None
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.subreddits = {}
        self._streams = {}
        default = {"subreddits": {}}
        self.config.register_global(**default)

    async def initialize(self):
        await self.bot.wait_until_red_ready()
        keys = await self.bot.get_shared_api_tokens("reddit")
        if not keys:
            return
        try:
            self.login = apraw.Reddit(
                client_id=keys["client_id"],
                client_secret=keys["client_secret"],
                password=keys["password"],
                username=keys["username"],
                user_agent=f"TrustyCogs/{self.__version__} on {self.bot.user}",
            )
            log.debug("Logged into Reddit.")
        except Exception:
            log.exception("Error logging into Reddit.")
        if self.login:
            self.subreddits = await self.config.subreddits()
            for sub, data in self.subreddits.items():
                if sub not in self._streams:
                    subreddit = await self.login.subreddit(data["name"])
                    self._streams[sub] = self.bot.loop.create_task(
                        self._run_subreddit_stream(subreddit)
                    )

    async def _run_subreddit_stream(self, subreddit: Subreddit):
        """
            A function to run the infinite loop of the subreddit stream and dispatch
            new posts as an event.
        """
        try:
            async for submission in subreddit.new.stream(skip_existing=True):
                self.bot.dispatch("reddit_post", subreddit, submission)
        except aiohttp.ContentTypeError:
            log.exception("Stream recieved incorrect data type.")
            self._streams[subreddit.id] = self.bot.loop.create_task(
                self._run_subreddit_stream(subreddit)
            )
        except Exception:
            log.exception("Error in streams task.")
            return None

    @commands.Cog.listener()
    async def on_reddit_post(self, subreddit: Subreddit, submission: Submission):
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
                chan_perms = channel.permissions_for(channel.guild.me)
                if not chan_perms.send_messages and not chan_perms.manage_webhooks:
                    continue
                use_embed = True  # channel.id not in self.regular_embed_channels
                contents = await make_embed_from_submission(channel, subreddit, submission)
                contents["subreddit"] = subreddit
                contents["submission"] = submission
                tasks.append(self.post_new_submissions(channel, contents, use_embed))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def post_new_submissions(
        self, channel: discord.TextChannel, contents: dict, use_embed: bool
    ):
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

    def cog_unload(self):
        try:
            self.bot.loop.create_task(self.login.close())
            log.debug("Closed the reddit login.")
        except Exception:
            log.exception("Error closing the login.")
        for name, stream in self._streams.items():
            try:
                stream.cancel()
            except Exception:
                log.debug(f"Error closing stream in {name}")

    @commands.group()
    async def redditset(self, ctx: commands.Context):
        """
            Commands for setting up the reddit cog
        """

    @redditset.command(name="post")
    @checks.mod_or_permissions(manage_channels=True)
    async def autopost_new_submissions(
        self, ctx: commands.Context, subreddit: str, channel: Optional[discord.TextChannel] = None
    ):
        """
            Setup a channel for automatically posting new subreddit submissions

            `<subreddit>` is the name of the subreddit you want to get updates on.
            `<channel>` is the channel where you want new subreddit posts to be put.
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        if not channel:
            channel = ctx.channel
        sub = await self.login.subreddit(subreddit)
        if sub.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        if sub.id not in self.subreddits:
            self.subreddits[sub.id] = {"name": sub.display_name, "channels": [channel.id]}
            self._streams[sub.id] = self.bot.loop.create_task(self._run_subreddit_stream(sub))
            await self.config.subreddits.set_raw(sub.id, value=self.subreddits[sub.id])
        else:
            if channel.id not in self.subreddits[sub.id]["channels"]:
                self.subreddits[sub.id]["channels"].append(channel.id)
                subs = await self.config.subreddits()
                subs[sub.id]["channels"].append(channel.id)
                await self.config.subreddits.set(subs)
            else:
                return await ctx.send(
                    f"{sub.display_name_prefixed} is already posting in {channel.menion}."
                )
        await ctx.send(
            f"I will now post new submissions to {sub.display_name_prefixed} in {channel.mention}."
        )

    @redditset.command(name="remove")
    @checks.mod_or_permissions(manage_channels=True)
    async def remove_autopost_new_submissions(
        self, ctx: commands.Context, subreddit: str, channel: Optional[discord.TextChannel] = None
    ):
        """
            Remove a channel from automatically posting new subreddit submissions

            `<subreddit>` is the name of the subreddit you want to get updates on.
            `<channel>` is the channel where you want new subreddit posts to be put.
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        if not channel:
            channel = ctx.channel
        sub = await self.login.subreddit(subreddit)
        if sub.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        if sub.id not in self.subreddits:
            return await ctx.send(
                f"{sub.display_name_prefixed} is not posting in {channel.mention}."
            )
        else:
            if channel.id in self.subreddits[sub.id]["channels"]:
                self.subreddits[sub.id]["channels"].remove(channel.id)
                subs = await self.config.subreddits()
                subs[sub.id]["channels"].remove(channel.id)
                if len(subs[sub.id]["channels"]) == 0:
                    del subs[sub.id]
                    del self.subreddits[sub.id]
                    try:
                        self._streams[sub.id].cancel()
                        del self._streams[sub.id]
                    except Exception:
                        log.exception("Error closing stream")
                await self.config.subreddits.set(subs)
            else:
                return await ctx.send(
                    f"{sub.display_name_prefixed} is not posting in {channel.menion}."
                )
        await ctx.send(
            f"I will stop posting new submissions to {sub.display_name_prefixed} in {channel.mention}."
        )

    @redditset.command()
    @commands.is_owner()
    async def creds(self, ctx: commands.Context):
        """
            How to setup login information for reddit.
        """
        msg = (
            "1. Go to https://www.reddit.com/prefs/apps and select create another app...\n"
            "2. Give the app a name and description, specify that it's a script\n"
            "3. In the developed apps section under the apps name you provided before below `personal use script` "
            "copy that into `<client_id>`\n"
            "4. In the app box where it says `secret` copy the code after into `<client_secret>` if you don't see this click the edit button\n"
            "5. Fill out the rest of the following command with your accounts username and password\n"
            "NOTE: If you have 2FA enabled on your account this will not work, I'd recommend creating a new reddit "
            "account specifically for the bot if that's the case.\n"
            f"`{ctx.clean_prefix}set api reddit username <username> password <password> client_id <client_id> client_secret <client_secret>`"
        )
        await ctx.maybe_send_embed(msg)

    @commands.group()
    async def reddit(self, ctx: commands.Context):
        """reddit"""

    @reddit.command(name="hot")
    async def reddit_hot(self, ctx: commands.Context, subreddit: str):
        """
            Show 25 hotest posts on the desired subreddit
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        subreddit = await self.login.subreddit(subreddit)
        if subreddit.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        submissions = subreddit.hot()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="new")
    async def reddit_new(self, ctx: commands.Context, subreddit: str):
        """
            Show 25 newest posts on the desired subreddit
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        subreddit = await self.login.subreddit(subreddit)
        if subreddit.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        submissions = subreddit.new()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="top")
    async def reddit_top(self, ctx: commands.Context, subreddit: str):
        """
            Show 25 newest posts on the desired subreddit
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        subreddit = await self.login.subreddit(subreddit)
        if subreddit.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        submissions = subreddit.top()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="rising")
    async def reddit_rising(self, ctx: commands.Context, subreddit: str):
        """
            Show 25 newest posts on the desired subreddit
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        subreddit = await self.login.subreddit(subreddit)
        if subreddit.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        submissions = subreddit.rising()
        await BaseMenu(
            source=RedditMenu(subreddit=subreddit, submissions=submissions),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

    @reddit.command(name="random")
    async def reddit_random(self, ctx: commands.Context, subreddit: str):
        """
            Show 25 newest posts on the desired subreddit
        """
        if not self.login:
            return await ctx.send(
                "The bot owner has not added credentials to utilize this cog.\n"
                "Have them see `{ctx.clean_prefix}redditset creds` for more information"
            )
        subreddit = await self.login.subreddit(subreddit)
        if subreddit.over18 and not ctx.channel.is_nsfw():
            return await ctx.send("I cannot post contents from this sub in non NSFW channels.")
        submission = await subreddit.random()
        if submission.over_18 and not ctx.channel.is_nsfw():
            for i in range(0, 10):
                submission = await subreddit.random()
                if not submission.over18:
                    break
        data = await make_embed_from_submission(ctx.channel, subreddit, submission)
        if data:
            if ctx.channel.permissions_for(ctx.me).embed_links:
                await ctx.send(data["content"], embed=data["embed"])
            else:
                await ctx.send(data["content"])
        else:
            await ctx.send("I could not find a suitable random post on that subreddit.")
