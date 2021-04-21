import asyncio
import functools
import logging
from html import unescape
from typing import Any, List, Optional, Dict

import discord
import tweepy
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import bounded_gather
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape

from .tweet_entry import TweetEntry

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


class TweetListener(tweepy.StreamListener):
    def __init__(self, api: tweepy.API, bot: Red):
        super().__init__(api=api)
        self.bot = bot

    def on_status(self, status: tweepy.Status) -> None:
        self.bot.dispatch("tweet_status", status)

    def on_error(self, status_code: int) -> None:
        msg = _("A tweet stream error has occured! ") + str(status_code)
        log.error(msg)
        self.bot.dispatch("tweet_error", msg)

    def on_disconnect(self, notice: Any) -> None:
        msg = _("Twitter has sent a disconnect code")
        log.info(msg)
        self.bot.dispatch("tweet_error", msg)

    def on_warning(self, notice: Any) -> None:
        msg = _("Twitter has sent a disconnection warning")
        log.warn(msg)
        self.bot.dispatch("tweet_error", msg)


class TweetsAPI:
    """
    Here is all the logic for handling autotweets
    """

    config: Config
    bot: Red
    accounts: Dict[str, TweetEntry]
    run_stream: bool
    twitter_loop: Optional[tweepy.Stream]

    async def start_stream(self) -> None:
        await self.bot.wait_until_red_ready()
        api = None
        base_sleep = 300
        count = 1
        tokens = await self.bot.get_shared_api_tokens("twitter")
        while self.run_stream:
            if not tokens:
                # Don't run the loop until tokens are set
                await asyncio.sleep(base_sleep)
                continue
            tweet_list = list(self.accounts.keys())
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

    async def _start_stream(self, tweet_list: List[str], api: tweepy.API) -> None:
        try:
            stream_start = TweetListener(api, self.bot)
            self.mystream = tweepy.Stream(api.auth, stream_start, daemon=True)
            fake_task = functools.partial(self.mystream.filter, follow=tweet_list, is_async=True)
            task = self.bot.loop.run_in_executor(None, fake_task)
            try:
                await asyncio.wait_for(task, timeout=5)
            except asyncio.TimeoutError:
                log.info("Timeout opening tweet stream.")
                pass
        except Exception:
            log.error("Error starting stream", exc_info=True)

    async def authenticate(self) -> tweepy.API:
        """Authenticate with Twitter's API"""
        keys = await self.bot.get_shared_api_tokens("twitter")
        consumer = keys.get("consumer_key")
        consumer_secret = keys.get("consumer_secret")
        access_token = keys.get("access_token")
        access_secret = keys.get("access_secret")
        auth = tweepy.OAuthHandler(consumer, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        return tweepy.API(
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
        help_msg = _(
            "\n See here for more information "
            "<https://developer.twitter.com/en/support/twitter-api/error-troubleshooting>"
        )
        if "420" in error:
            help_msg += _(
                "You're being rate limited. Maybe you should unload the cog for a while..."
            )
            log.critical(str(error) + help_msg)
        guild_id = await self.config.error_guild()
        channel_id = await self.config.error_channel()

        if guild_id is None and channel_id is not None:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            guild_id = channel.guild.id
            await self.config.error_guild.set(channel.guild.id)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        if not channel.permissions_for(guild.me).send_messages:
            return
        await channel.send(str(error) + help_msg)

    async def build_tweet_embed(self, status: tweepy.Status) -> discord.Embed:
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
                log.debug("Error grabbing in reply to tweet.", exc_info=True)

        em.description = escape(unescape(text), formatting=True)

        return em

    @commands.Cog.listener()
    async def on_tweet_status(self, status: tweepy.Status) -> None:
        """Posts the tweets to the channel"""
        username = status.user.screen_name
        user_id = status.user.id

        if str(user_id) not in self.accounts:
            return
        em = await self.build_tweet_embed(status)
        # channel_list = account.channel
        tasks = []
        channels = self.accounts[str(user_id)].channels.copy()
        for channel_id, data in channels.items():
            if data.guild is None:
                channel_send = self.bot.get_channel(int(channel_id))
                if channel_send is None:
                    await self.del_account(channel_id, user_id, username)
                    continue
                self.accounts[str(user_id)].channels[str(channel_id)].guild = channel_send.guild.id
                await self.save_accounts()
            else:
                guild = self.bot.get_guild(data.guild)
                if not guild:
                    await self.del_account(channel_id, user_id, username)
                    continue
                channel_send = guild.get_channel(int(channel_id))
            if channel_send is None:
                await self.del_account(channel_id, user_id, username)
                continue
            chan_perms = channel_send.permissions_for(channel_send.guild.me)
            if not chan_perms.send_messages and not chan_perms.manage_webhooks:
                # remove channels we don't have permission to send in
                await self.del_account(channel_id, user_id, username)
                continue
            if hasattr(status, "retweeted_status") and not data.retweets:
                continue
            if status.in_reply_to_screen_name and not data.replies:
                continue
            tasks.append(self.post_tweet_status(channel_send, em, status, data.embeds))
        await bounded_gather(*tasks, return_exceptions=True)

    async def post_tweet_status(
        self,
        channel_send: discord.TextChannel,
        em: discord.Embed,
        status: tweepy.Status,
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
            log.exception(
                f"Could not post a tweet in {repr(channel_send)} for account {status.user.screen_name}"
            )
