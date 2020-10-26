import asyncio
import functools
import logging
from datetime import datetime
from html import unescape
from io import BytesIO
from typing import Any, List, Optional, Tuple

import discord
import tweepy as tw
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.utils import bounded_gather
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import escape, humanize_list, pagify

from .tweet_entry import TweetEntry

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


class TweetListener(tw.StreamListener):
    def __init__(self, api, bot):
        super().__init__(api=api)
        self.bot = bot

    def on_status(self, status):
        self.bot.dispatch("tweet_status", status)
        if self.bot.is_closed():
            return False
        else:
            return True

    def on_error(self, status_code):
        msg = _("A tweet stream error has occured! ") + str(status_code)
        log.error(msg)
        self.bot.dispatch("tweet_error", msg)
        if status_code in [420, 504, 503, 502, 500, 400, 401, 403, 404]:
            return False

    def on_disconnect(self, notice):
        msg = _("Twitter has sent a disconnect code")
        log.info(msg)
        self.bot.dispatch("tweet_error", msg)
        return False

    def on_warning(self, notice):
        msg = _("Twitter has sent a disconnection warning")
        log.warn(msg)
        self.bot.dispatch("tweet_error", msg)
        return True


@cog_i18n(_)
class Tweets(commands.Cog):
    """
    Cog for displaying info from Twitter's API
    """

    __author__ = ["Palm__", "TrustyJAID"]
    __version__ = "2.6.6"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 133926854, force_registration=True)
        default_global = {
            "api": {
                "consumer_key": "",
                "consumer_secret": "",
                "access_token": "",
                "access_secret": "",
            },
            "accounts": {},
            "error_channel": None,
            "version": "0.0.0",
        }
        self.config.register_global(**default_global)
        self.config.register_channel(custom_embeds=True)
        self.mystream = None
        self.run_stream = True
        self.twitter_loop = None
        self.accounts = {}
        self.regular_embed_channels = []

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def initialize(self):
        data = await self.config.accounts()
        if await self.config.version() < "2.6.0":
            for name, account in data.items():
                if "retweets" not in account:
                    account["retweets"] = True
                self.accounts[account["twitter_id"]] = account
            await self.config.accounts.set(self.accounts)
            await self.config.version.set("2.6.0")
        else:
            self.accounts = await self.config.accounts()
        embed_channels = await self.config.all_channels()
        for c_id, settings in embed_channels.items():
            if not settings["custom_embeds"]:
                self.regular_embed_channels.append(c_id)
        self.twitter_loop = asyncio.create_task(self.start_stream())

    ###################################################################
    # Here is all the logic for handling tweets and tweet creation

    async def start_stream(self) -> None:
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        api = None
        base_sleep = 300
        count = 1
        while self.run_stream:
            if not await self.config.api.consumer_key():
                # Don't run the loop until tokens are set
                await asyncio.sleep(base_sleep)
                continue
            tweet_list = list(self.accounts)
            if not tweet_list:
                await asyncio.sleep(base_sleep)
                continue
            if not api:
                api = await self.authenticate()
            if self.mystream is None:
                await self._start_stream(tweet_list, api)
            elif self.mystream and not getattr(self.mystream, "running"):
                count += 1
                await self._start_stream(tweet_list, api)
            log.debug(f"tweets waiting {base_sleep * count} seconds.")
            await asyncio.sleep(base_sleep * count)

    async def _start_stream(self, tweet_list: list, api: tw.API) -> None:
        try:
            stream_start = TweetListener(api, self.bot)
            self.mystream = tw.Stream(api.auth, stream_start, daemon=True)
            fake_task = functools.partial(self.mystream.filter, follow=tweet_list, is_async=True)
            task = self.bot.loop.run_in_executor(None, fake_task)
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                log.info("Timeout opening tweet stream.")
                pass
        except Exception:
            log.error("Error starting stream", exc_info=True)

    async def authenticate(self) -> tw.API:
        """Authenticate with Twitter's API"""
        auth = tw.OAuthHandler(
            await self.config.api.consumer_key(), await self.config.api.consumer_secret()
        )
        auth.set_access_token(
            await self.config.api.access_token(), await self.config.api.access_secret()
        )
        return tw.API(
            auth,
            wait_on_rate_limit=True,
            wait_on_rate_limit_notify=True,
            retry_count=10,
            retry_delay=5,
            retry_errors=[500, 502, 503, 504],
        )

    async def autotweet_restart(self) -> None:
        if self.mystream is not None:
            self.mystream.disconnect()
        self.twitter_loop.cancel()
        self.twitter_loop = self.bot.loop.create_task(self.start_stream())

    @commands.Cog.listener()
    async def on_tweet_error(self, error: str) -> None:
        """Posts tweet stream errors to a specified channel"""
        if await self.config.error_channel() is not None:
            channel = self.bot.get_channel(await self.config.error_channel())
            help_msg = _(
                "\n See here for more information "
                "<https://developer.twitter.com/en/docs/basics/response-codes.html>"
            )
            await channel.send(str(error) + help_msg)
            if "420" in error:
                msg = _(
                    "You're being rate limited. Maybe you should unload the cog for a while..."
                )
                log.critical(msg)
                await channel.send(msg)
        return

    async def build_tweet_embed(self, status: tw.Status) -> discord.Embed:
        username = status.user.screen_name
        post_url = "https://twitter.com/{}/status/{}".format(status.user.screen_name, status.id)
        em = discord.Embed(
            colour=discord.Colour(value=int(status.user.profile_link_color, 16)),
            url=post_url,
            timestamp=status.created_at,
        )
        em.set_footer(text=f"@{username}")
        if hasattr(status, "retweeted_status"):
            em.set_author(
                name=f"{status.user.name} Retweeted {status.retweeted_status.user.name}",
                url=post_url,
                icon_url=status.user.profile_image_url,
            )
            status = status.retweeted_status
            em.set_footer(text=f"@{username} RT @{status.user.screen_name}")
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    img = status.extended_tweet["entities"]["media"][0]["media_url_https"]
                    em.set_image(url=img)
            else:
                text = status.text
        else:
            em.set_author(
                name=status.user.name, url=post_url, icon_url=status.user.profile_image_url
            )
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    img = status.extended_tweet["entities"]["media"][0]["media_url_https"]
                    em.set_image(url=img)
            else:
                text = status.text
        if status.in_reply_to_screen_name:
            api = await self.authenticate()
            try:
                reply = api.statuses_lookup(id_=[status.in_reply_to_status_id])[0]
                # log.debug(reply)
                in_reply_to = _("In reply to {name} (@{screen_name})").format(
                    name=reply.user.name, screen_name=reply.user.screen_name
                )
                reply_text = unescape(reply.text)
                if hasattr(reply, "extended_tweet"):
                    reply_text = unescape(reply.extended_tweet["full_text"])
                if hasattr(reply, "extended_entities") and not em.image:
                    em.set_image(url=reply.extended_entities["media"][0]["media_url_https"])
                em.add_field(name=in_reply_to, value=reply_text)
            except IndexError:
                log.debug(_("Error grabbing in reply to tweet."), exc_info=True)

        em.description = escape(unescape(text), formatting=True)

        return em

    @commands.Cog.listener()
    async def on_tweet_status(self, status: tw.Status) -> None:
        """Posts the tweets to the channel"""
        username = status.user.screen_name
        user_id = status.user.id

        if str(user_id) not in self.accounts:
            return
        if status.in_reply_to_screen_name and not self.accounts[str(user_id)]["replies"]:
            return
        if hasattr(status, "retweeted_status") and not self.accounts[str(user_id)]["retweets"]:
            return
        em = await self.build_tweet_embed(status)
        # channel_list = account.channel
        tasks = []
        for channel in self.accounts[str(user_id)]["channel"]:
            channel_send = self.bot.get_channel(int(channel))
            if channel_send is None:
                await self.del_account(channel, user_id, username)
                continue
            chan_perms = channel_send.permissions_for(channel_send.guild.me)
            if not chan_perms.send_messages and not chan_perms.manage_webhooks:
                # remove channels we don't have permission to send in
                await self.del_account(channel, user_id, username)
                continue
            use_embed = channel_send.id not in self.regular_embed_channels
            tasks.append(self.post_tweet_status(channel_send, em, status, use_embed))
        await bounded_gather(*tasks, return_exceptions=True)

    async def post_tweet_status(
        self,
        channel_send: discord.TextChannel,
        em: discord.Embed,
        status: tw.Status,
        use_custom_embed: bool = True,
    ):
        username = status.user.screen_name
        post_url = f"https://twitter.com/{status.user.screen_name}/status/{status.id}"
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, channel_send.guild):
                return
        try:
            if channel_send.permissions_for(channel_send.guild.me).embed_links:
                if use_custom_embed:
                    await channel_send.send(post_url, embed=em)
                else:
                    await channel_send.send(post_url)
            elif channel_send.permissions_for(channel_send.guild.me).manage_webhooks:
                webhook = None
                for hook in await channel_send.webhooks():
                    if hook.name == channel_send.guild.me.name:
                        webhook = hook
                if webhook is None:
                    webhook = await channel_send.create_webhook(name=channel_send.guild.me.name)
                avatar = status.user.profile_image_url
                if use_custom_embed:
                    await webhook.send(post_url, username=username, avatar_url=avatar, embed=em)
                else:
                    await webhook.send(post_url, username=username, avatar_url=avatar)
            else:
                await channel_send.send(post_url)
        except Exception:
            msg = "{0} from <#{1}>({1})".format(post_url, channel_send.id)
            log.error(msg, exc_info=True)

    async def tweet_menu(
        self,
        ctx: commands.Context,
        post_list: list,
        message: Optional[discord.Message] = None,
        page: int = 0,
        timeout: int = 30,
    ) -> None:
        """menu control logic for this taken from
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        s = post_list[page]
        em = None
        if ctx.channel.permissions_for(ctx.me).embed_links:
            if ctx.channel.id not in self.regular_embed_channels:
                em = await self.build_tweet_embed(s)
            else:
                em = None

        post_url = "https://twitter.com/{}/status/{}".format(s.user.screen_name, s.id)
        if not message:
            message = await ctx.send(post_url, embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(content=post_url, embed=em)
        check = (
            lambda react, user: user == ctx.message.author
            and react.emoji in ["➡", "⬅", "❌"]
            and react.message.id == message.id
        )
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", ctx.me)
            await message.remove_reaction("❌", ctx.me)
            await message.remove_reaction("➡", ctx.me)
            return None
        else:
            if react.emoji == "➡":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("➡", ctx.message.author)
                return await self.tweet_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.tweet_menu(
                    ctx, post_list, message=message, page=next_page, timeout=timeout
                )
            else:
                return await message.delete()

    ###################################################################
    # here are all the commands for getting twitter info

    @commands.group(name="tweets", aliases=["twitter"])
    async def _tweets(self, ctx: commands.Context):
        """Gets various information from Twitter's API"""
        pass

    @_tweets.command(name="send")
    @checks.is_owner()
    async def send_tweet(self, ctx: commands.Context, *, message: str) -> None:
        """
        Allows the owner to send tweets through discord

        Upload an image to send an image with it as well.
        """
        try:
            api = await self.authenticate()
            if ctx.message.attachments != []:
                temp = BytesIO()
                filename = ctx.message.attachments[0].filename
                await ctx.message.attachments[0].save(temp)
                api.update_with_media(filename, status=message, file=temp)
            else:
                api.update_status(message)
        except Exception:
            log.error("Error sending tweet", exc_info=True)
            await ctx.send(_("An error has occured, check the console for more details."))
            return
        await ctx.send(_("Tweet sent!"))

    async def get_colour(self, channel: discord.TextChannel) -> discord.Colour:
        try:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()
        except AttributeError:
            return await self.bot.get_embed_colour(channel)

    @_tweets.command(name="trends")
    async def trends(self, ctx: commands.Context, *, location: str = "United States") -> None:
        """
        Gets twitter trends for a given location

        You can provide a location and it will try to get
        different trend information from that location
        default is `United States`
        """
        api = await self.authenticate()
        try:
            fake_task = functools.partial(api.trends_available)
            task = self.bot.loop.run_in_executor(None, fake_task)
            location_list = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timed out getting twitter trends."))
        country_id = None
        location_names = []
        for locations in location_list:
            location_names.append(locations["name"])
            if location.lower() in locations["name"].lower():
                country_id = locations
        if country_id is None:
            await ctx.send("{} Is not a correct location!".format(location))
            return
        try:
            fake_task = functools.partial(api.trends_place, country_id["woeid"])
            task = self.bot.loop.run_in_executor(None, fake_task)
            trends = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timed out getting twitter trends."))
        em = discord.Embed(colour=await self.get_colour(ctx.channel), title=country_id["name"])
        msg = ""
        trends = trends[0]["trends"]
        for trend in trends:
            # trend = trends[0]["trends"][i]
            if trend["tweet_volume"] is not None:
                msg += "{}. [{}]({}) Volume: {}\n".format(
                    trends.index(trend) + 1, trend["name"], trend["url"], trend["tweet_volume"]
                )
            else:
                msg += "{}. [{}]({})\n".format(
                    trends.index(trend) + 1, trend["name"], trend["url"]
                )
        count = 0
        for page in pagify(msg[:5980], shorten_by=1024):
            if count == 0:
                em.description = page
            else:
                em.add_field(name=_("Trends (continued)"), value=page)
            count += 1
        em.timestamp = datetime.utcnow()
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(embed=em)
        else:
            await ctx.send("```\n{}```".format(msg[:1990]))

    async def get_twitter_user(self, username: str) -> tw.User:
        try:
            api = await self.authenticate()
            fake_task = functools.partial(api.get_user, username)
            task = self.bot.loop.run_in_executor(None, fake_task)
            user = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            raise
        except tw.error.TweepError:
            raise
        return user

    @_tweets.command(name="getuser")
    async def get_user(self, ctx: commands.context, username: str) -> None:
        """Get info about the specified user"""
        try:
            user = await self.get_twitter_user(username)
        except asyncio.TimeoutError:
            await ctx.send(_("Looking up the user timed out."))
            return
        except tw.error.TweepError:
            await ctx.send(_("{username} could not be found.").format(username=username))
            return
        profile_url = "https://twitter.com/" + user.screen_name
        description = str(user.description)
        for url in user.entities["description"]["urls"]:
            if str(url["url"]) in description:
                description = description.replace(url["url"], str(url["expanded_url"]))
        emb = discord.Embed(
            colour=discord.Colour(value=int(user.profile_link_color, 16)),
            url=profile_url,
            description=str(description),
            timestamp=user.created_at,
        )
        emb.set_author(name=user.name, url=profile_url, icon_url=user.profile_image_url)
        emb.set_thumbnail(url=user.profile_image_url)
        emb.add_field(name="Followers", value=user.followers_count)
        emb.add_field(name="Friends", value=user.friends_count)
        if user.verified:
            emb.add_field(name="Verified", value="Yes")
        footer = "Created at "
        emb.set_footer(text=footer)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send("<" + profile_url + ">", embed=emb)
        else:
            await ctx.send(profile_url)

    def _get_twitter_statuses(
        self, api: tw.API, username: str, count: int, replies: bool
    ) -> List[tw.Status]:
        cnt = count
        if count and count > 25:
            cnt = 25
        msg_list = []
        try:
            for status in tw.Cursor(api.user_timeline, id=username).items(cnt):
                if status.in_reply_to_screen_name is not None and not replies:
                    continue
                msg_list.append(status)
        except tw.TweepError:
            raise
        return msg_list

    @_tweets.command(name="gettweets")
    @checks.bot_has_permissions(add_reactions=True)
    async def get_tweets(
        self, ctx: commands.context, username: str, count: Optional[int] = 10, replies: bool = True
    ) -> None:
        """
        Display a users tweets as a scrollable message

        defaults to 10 tweets
        """
        msg_list = []
        api = await self.authenticate()
        try:
            fake_task = functools.partial(
                self._get_twitter_statuses,
                api=api,
                username=username,
                count=count,
                replies=replies,
            )
            task = self.bot.loop.run_in_executor(None, fake_task)
            msg_list = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            msg = _("Timedout getting tweet list")
            await ctx.send(msg)
        except tw.TweepError as e:
            msg = _("Whoops! Something went wrong here. The error code is ") + f"{e} {username}"
            await ctx.send(msg)
            return
        if len(msg_list) > 0:
            await self.tweet_menu(ctx, msg_list, page=0, timeout=30)
        else:
            await ctx.send(_("No tweets available to display!"))

    @commands.group(name="autotweet")
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def _autotweet(self, ctx: commands.context) -> None:
        """Command for setting accounts and channels for posting"""
        pass

    @_autotweet.command(name="error")
    @checks.is_owner()
    async def _error(
        self, ctx: commands.context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set an error channel for tweet stream error updates"""
        if not channel:
            save_channel = ctx.channel.id
        else:
            save_channel = channel.id
        await self.config.error_channel.set(save_channel)
        await ctx.send("Twitter error channel set to {}".format(save_channel))

    @_autotweet.command(name="cleanup")
    @checks.is_owner()
    async def tweets_cleanup(self, ctx: commands.context) -> None:
        """Searches for unavailable channels and removes posting in those channels"""
        to_delete = []
        for user_id, account in self.accounts.items():
            for channel in account["channel"]:
                chn = self.bot.get_channel(channel)
                if chn is None or not chn.permissions_for(ctx.me).send_messages:
                    log.debug("Removing channel {}".format(channel))
                    self.accounts[user_id]["channel"].remove(channel)
            if len(self.accounts[user_id]["channel"]) == 0:
                log.debug("Removing account {}".format(account["twitter_name"]))
                to_delete.append(user_id)
        for u_id in to_delete:
            del self.accounts[u_id]
        await self.config.accounts.set(self.accounts)

    @_autotweet.command(name="embeds")
    async def set_custom_embeds(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """
        Set a channel to use custom embeds for tweets or discords automatic ones.

        (default is enabled for custom embeds)
        """
        current = await self.config.channel(channel).custom_embeds()
        if current:
            await self.config.channel(channel).custom_embeds.set(not current)
            await ctx.send(
                _("Custom embeds have been disabled in {channel}").format(channel=channel.mention)
            )
            if channel.id not in self.regular_embed_channels:
                self.regular_embed_channels.append(channel.id)
        else:
            await self.config.channel(channel).clear()
            await ctx.send(
                _("Custom embeds have been enabled in {channel}").format(channel=channel.mention)
            )
            if channel.id in self.regular_embed_channels:
                self.regular_embed_channels.remove(channel.id)

    @_autotweet.command(name="restart")
    async def restart_stream(self, ctx: commands.context) -> None:
        """Restarts the twitter stream if any issues occur."""
        await ctx.channel.trigger_typing()
        await self.autotweet_restart()
        await ctx.send(_("Restarting the twitter stream."))

    @_autotweet.command(name="replies")
    async def _replies(self, ctx: commands.context, *usernames: str) -> None:
        """
        Toggle an accounts replies being posted

        This is checked on `autotweet` as well as `gettweets`
        """
        if len(usernames) == 0:
            return await ctx.send_help()
        added_replies = []
        removed_treplies = []
        for username in usernames:
            username = username.lower()
            edited_account = None
            for user_id, accounts in self.accounts.items():
                if accounts["twitter_name"].lower() == username:
                    edited_account = user_id
            if edited_account is None:
                continue
            else:
                # all_accounts.remove(edited_account)
                replies = self.accounts[edited_account]["replies"]
                self.accounts[edited_account]["replies"] = not replies
                if replies:
                    removed_treplies.append(username)
                else:
                    added_replies.append(username)
        await self.config.accounts.set(self.accounts)
        msg = ""
        if added_replies:
            msg += _("Now posting replies from {replies}\n").format(
                replies=humanize_list(added_replies)
            )
        if removed_treplies:
            msg += _("No longer posting replies from {replies}\n").format(
                replies=humanize_list(removed_treplies)
            )
        await ctx.send(msg)

    @_autotweet.command(name="retweets")
    async def _retweets(self, ctx: commands.context, *usernames: str) -> None:
        """
        Toggle an accounts retweets being posted

        This is checked on `autotweet` as well as `gettweets`
        """
        if len(usernames) == 0:
            return await ctx.send_help()
        added_retweets = []
        removed_retweets = []
        for username in usernames:
            username = username.lower()
            edited_account = None
            for user_id, accounts in self.accounts.items():
                if accounts["twitter_name"].lower() == username:
                    edited_account = user_id
            if edited_account is None:
                await ctx.send(_("I am not following ") + username)
                return
            else:
                # all_accounts.remove(edited_account)
                retweets = self.accounts[edited_account]["retweets"]
                self.accounts[edited_account]["retweets"] = not retweets
                if retweets:
                    removed_retweets.append(username)
                else:
                    added_retweets.append(username)
        await self.config.accounts.set(self.accounts)
        msg = ""
        if added_retweets:
            msg += _("Now posting retweets from {retweets}.").format(
                retweets=humanize_list(added_retweets)
            )
        if removed_retweets:
            msg += _("No longer posting retweets from {retweets}").format(
                retweets=humanize_list(removed_retweets)
            )
        await ctx.send(msg)

    async def is_followed_account(self, twitter_id) -> Tuple[bool, Any]:
        followed_accounts = await self.config.accounts()

        for account in followed_accounts:
            if account["twitter_id"] == twitter_id:
                return True, account
        return False, None

    @_autotweet.command(name="add")
    async def _add(
        self, ctx: commands.context, username: str, channel: discord.TextChannel = None
    ) -> None:
        """
        Adds a twitter username to the specified channel

        `username` needs to be the @handle for the twitter username
        `channel` has to be a valid server channel, defaults to the current channel
        """
        user_id = None
        screen_name = None
        try:
            user = await self.get_twitter_user(username)
            user_id = user.id
            screen_name = user.screen_name
        except asyncio.TimeoutError:
            msg = _("Looking up user timed out")
            await ctx.send(msg)
            return
        except tw.TweepError as e:
            msg = _("Whoops! Something went wrong here. The error code is ") + f"{e} {username}"
            log.error(msg, exc_info=True)
            await ctx.send(_("That username does not exist."))
            return
        if user_id is None or screen_name is None:
            return await ctx.send(_("That username does not exist."))
        if channel is None:
            channel = ctx.message.channel
        own_perms = channel.permissions_for(ctx.guild.me)
        if not own_perms.send_messages:
            await ctx.send(_("I don't have permission to post in ") + channel.mention)
            return
        if not own_perms.embed_links and not own_perms.manage_webhooks:
            msg = (
                _("I do not have embed links permission in ")
                + f"{channel.mention}, "
                + _("I recommend enabling that for pretty twitter posts!")
            )
            await ctx.send(msg)
        in_list = str(user_id) in self.accounts
        added = await self.add_account(channel, user_id, screen_name)
        if added:
            await ctx.send(username + _(" added to ") + channel.mention)
            if not in_list:
                msg = (
                    _("Now do ")
                    + f"`{ctx.prefix}autotweet restart`"
                    + _(" when you've finished adding all accounts!")
                )
                await ctx.send(msg)
        else:
            msg = _("I am already posting ") + username + _(" in ") + channel.mention
            await ctx.send(msg)

    @_autotweet.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def _list(self, ctx: commands.context) -> None:
        """Lists the autotweet accounts on the guild"""
        account_list = ""
        guild = ctx.message.guild

        # accounts = [x for x in await self.config.accounts()]
        embed = discord.Embed(
            title="Twitter accounts posting in {}".format(guild.name),
            colour=await self.get_colour(ctx.channel),
            # description=account_list[:-2],
            timestamp=ctx.message.created_at,
        )
        embed.set_author(name=guild.name, icon_url=guild.icon_url)
        account_list = ""
        for channel in guild.text_channels:
            channel_accounts = []
            for user_id, account in self.accounts.items():
                if channel.id in account["channel"]:
                    channel_accounts.append(account["twitter_name"])
            if channel_accounts:
                account_list += f"{channel.mention}\n"
                account_list += humanize_list(channel_accounts) + "\n"
        pages = list(pagify(account_list, page_length=1024))
        embed.description = "".join(pages[:2])
        for page in pages[2:]:
            embed.add_field(name=_("Autotweet list continued"), value=page)
        await ctx.send(embed=embed)

    async def add_account(
        self, channel: discord.TextChannel, user_id: int, screen_name: str
    ) -> bool:
        """
        Adds a twitter account to the specified channel.
        Returns False if it is already in the channel.
        """
        # followed_accounts = await self.config.accounts()

        # is_followed, twitter_account = await self.is_followed_account(user_id)
        if str(user_id) in self.accounts:
            if channel.id in self.accounts[str(user_id)]["channel"]:
                return False
            else:
                self.accounts[str(user_id)]["channel"].append(channel.id)
                await self.config.accounts.set(self.accounts)
                # await self.config.accounts.set(followed_accounts)
        else:
            twitter_account = TweetEntry(user_id, screen_name, [channel.id], 0)
            self.accounts[str(user_id)] = twitter_account.to_json()
            await self.config.accounts.set(self.accounts)
        return True

    def get_tweet_list(self, api: tw.API, owner: str, list_name: str) -> List[int]:
        cursor = -1
        list_members: list = []
        for member in tw.Cursor(
            api.list_members, owner_screen_name=owner, slug=list_name, cursor=cursor
        ).items():
            list_members.append(member)
        return list_members

    @_autotweet.command(name="addlist")
    async def add_list(
        self,
        ctx: commands.context,
        owner: str,
        list_name: str,
        channel: discord.TextChannel = None,
    ) -> None:
        """
        Add an entire twitter list to a specified channel.

        The list must be public or the bot owner must own it.
        `owner` is the owner of the list's @handle
        `list_name` is the name of the list
        `channel` is the channel where the tweets will be posted
        """
        api = await self.authenticate()
        try:
            fake_task = functools.partial(
                self.get_tweet_list, api=api, owner=owner, list_name=list_name
            )
            task = ctx.bot.loop.run_in_executor(None, fake_task)
            list_members = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            msg = _("Adding that tweet list took too long.")
            log.error(msg, exc_info=True)
            return await ctx.send(msg)
        except Exception:
            log.error("Error adding list", exc_info=True)
            msg = _("That `owner` and `list_name` " "don't appear to be available")
            return await ctx.send(msg)
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send(_("I don't have permission to post in ") + channel.mention)
            return
        if not channel.permissions_for(ctx.guild.me).embed_links:
            msg = (
                _("I do not have embed links permission in ")
                + f"{channel.mention}, "
                + _("I recommend enabling that for pretty twitter posts!")
            )
            await ctx.send(msg)
        added_accounts = []
        missed_accounts = []
        for member in list_members:
            added = await self.add_account(channel, member.id, member.name)
            if added:
                added_accounts.append(member.name)
            else:
                missed_accounts.append(member.name)
        if len(added_accounts) != 0:
            msg = ", ".join(member for member in added_accounts)
            msg_send = _("Added the following accounts to ") + "{}: {}".format(
                channel.mention, msg
            )
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)
            msg = (
                _("Now do ")
                + f"`{ctx.prefix}autotweet restart`"
                + _(" when you've finished adding all accounts!")
            )
            await ctx.send(msg)
        if len(missed_accounts) != 0:
            msg = ", ".join(member for member in missed_accounts)
            msg_send = _("The following accounts could not be added to ") + "{}: {}".format(
                channel.mention, msg
            )
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    @_autotweet.command(name="remlist")
    async def rem_list(
        self,
        ctx: commands.context,
        owner: str,
        list_name: str,
        channel: discord.TextChannel = None,
    ) -> None:
        """
        Remove an entire twitter list from a specified channel.

        The list must be public or the bot owner must own it.
        `owner` is the owner of the list's @handle
        `list_name` is the name of the list
        `channel` is the channel where the tweets will be posted
        """
        api = await self.authenticate()
        try:
            fake_task = functools.partial(
                self.get_tweet_list, api=api, owner=owner, list_name=list_name
            )
            task = ctx.bot.loop.run_in_executor(None, fake_task)
            list_members = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            msg = _("Adding that tweet list took too long.")
            log.error(msg, exc_info=True)
            return await ctx.send(msg)
        except Exception:
            log.exception("Error finding twitter list")
            msg = _("That `owner` and `list_name` " "don't appear to be available")
            await ctx.send(msg)
            return
        if channel is None:
            channel = ctx.message.channel
        removed_accounts = []
        missed_accounts = []
        for member in list_members:
            removed = await self.del_account(channel.id, member.id, member.name)
            if removed:
                removed_accounts.append(member.name)
            else:
                missed_accounts.append(member.name)
        if len(removed_accounts) != 0:
            msg = ", ".join(member for member in removed_accounts)
            msg_send = _("Removed the following accounts from ") + "{}: {}".format(
                channel.mention, msg
            )
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)
        if len(missed_accounts) != 0:
            msg = ", ".join(member for member in missed_accounts)
            msg_send = (
                _("The following accounts weren't added to ")
                + channel.mention
                + _(" or there was another error: ")
                + msg
            )
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    async def del_account(self, channel_id: int, user_id: int, screen_name: str = "") -> bool:
        # account_ids = [x["twitter_id"] for x in await self.config.accounts()]
        if str(user_id) not in self.accounts:
            return False
        # account_list = [x for x in await self.config.accounts()]
        # twitter_account = [x for x in account_list if user_id == x["twitter_id"]][0]
        if channel_id in self.accounts[str(user_id)]["channel"]:
            self.accounts[str(user_id)]["channel"].remove(channel_id)
            # await self.config.accounts.set(account_list)
            if len(self.accounts[str(user_id)]["channel"]) < 1:
                del self.accounts[str(user_id)]
        else:
            return False
        await self.config.accounts.set(self.accounts)
        return True

    @_autotweet.command(name="del", aliases=["delete", "rem", "remove"])
    async def _del(
        self, ctx, username: str, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """
        Removes a twitter username to the specified channel

        `username` must be the users @handle
        `channel` is the channel where the username is currently being posted
        """
        username = username.lower()
        api = await self.authenticate()
        if channel is None:
            channel = ctx.message.channel
        try:
            for status in tw.Cursor(api.user_timeline, id=username).items(1):
                user_id: int = status.user.id
                screen_name: str = status.user.screen_name
        except tw.TweepError as e:
            msg = _("Whoops! Something went wrong here. The error code is ") + f"{e} {username}"
            log.error(msg, exc_info=True)
            await ctx.send(_("Something went wrong here! Try again"))
            return
        removed = await self.del_account(channel.id, user_id, screen_name)
        if removed:
            await ctx.send(username + _(" has been removed from ") + channel.mention)
        else:
            await ctx.send(username + _(" doesn't seem to be posting in ") + channel.mention)

    @commands.group(name="tweetset")
    @checks.admin_or_permissions(manage_guild=True)
    async def _tweetset(self, ctx: commands.Context) -> None:
        """Command for setting required access information for the API.

        1. Visit https://apps.twitter.com and apply for a developer account.
        2. Once your account is approved setup an application and fillout the form
        3. Do `[p]tweetset creds consumer_key consumer_secret access_token access_secret`
        to the bot in a private channel (DM's preferred).
        """
        pass

    @_tweetset.command(name="creds")
    @checks.is_owner()
    async def set_creds(
        self, ctx, consumer_key: str, consumer_secret: str, access_token: str, access_secret: str
    ) -> None:
        """[p]tweetset """
        api = {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
            "access_token": access_token,
            "access_secret": access_secret,
        }
        await self.config.api.set(api)
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        await ctx.send(_("Access credentials have been set!"))

    def cog_unload(self):
        log.debug("Unloading tweets...")
        self.twitter_loop.cancel()
        log.debug("Twitter restart loop canceled.")
        self.run_stream = False
        if self.mystream is not None:
            log.debug("Twitter stream is running, trying to stop.")
            self.mystream.disconnect()
            self.mystream = None
            log.debug("Twitter stream disconnected.")
        log.debug("Tweets unloaded.")
