import asyncio
import functools
import logging
from html import unescape
from typing import Any, Dict, List, Optional

import discord
import tweepy
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils import bounded_gather
from redbot.core.utils.chat_formatting import escape
from tweepy.asynchronous import AsyncStream

from .tweet_entry import TweetEntry

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


class MissingTokenError(Exception):

    async def send_error(self, ctx: commands.Context):
        await ctx.send(
            _(
                "You need to set your API tokens. See `{prefix}tweetset creds` for information on how."
            ).format(prefix=ctx.clean_prefix)
        )


class TweetListener(AsyncStream):
    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        bot: Red,
    ):
        super().__init__(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        self.bot = bot

    async def on_status(self, status: tweepy.models.Status) -> None:
        self.bot.dispatch("tweet_status", status)

    async def on_error(self, status_code: int) -> None:
        msg = _("A tweet stream error has occured! ") + str(status_code)
        log.error(msg)
        self.bot.dispatch("tweet_error", msg)

    async def on_disconnect_message(self, message: Any) -> None:
        msg = _("Twitter has sent a disconnect message {message}").format(message=message)
        log.info(msg)
        self.bot.dispatch("tweet_error", msg)

    async def on_warning(self, notice: Any) -> None:
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
            # if not api:
            # api = await self.authenticate()
            if self.mystream is None:
                await self._start_stream(tweet_list, api)
            elif self.mystream and (self.stream_task.cancelled() or self.stream_task.done()):
                count += 1
                await self._start_stream(tweet_list, api)
            log.debug(f"tweets waiting {base_sleep * count} seconds.")
            await asyncio.sleep(base_sleep * count)

    async def _start_stream(self, tweet_list: List[str], api: tweepy.API) -> None:
        keys = await self.bot.get_shared_api_tokens("twitter")
        consumer = keys.get("consumer_key")
        consumer_secret = keys.get("consumer_secret")
        access_token = keys.get("access_token")
        access_secret = keys.get("access_secret")
        try:
            self.mystream = TweetListener(
                consumer, consumer_secret, access_token, access_secret, self.bot
            )
            self.stream_task = self.mystream.filter(follow=tweet_list)
        except Exception:
            log.error("Error starting stream", exc_info=True)

    async def authenticate(self) -> tweepy.API:
        """Authenticate with Twitter's API"""
        keys = await self.bot.get_shared_api_tokens("twitter")
        consumer = keys.get("consumer_key")
        consumer_secret = keys.get("consumer_secret")
        access_token = keys.get("access_token")
        access_secret = keys.get("access_secret")
        keys = [consumer, consumer_secret, access_token, access_secret]
        if any([k is None for k in keys]):
            raise MissingTokenError()
        auth = tweepy.OAuthHandler(consumer, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        return tweepy.API(
            auth,
            wait_on_rate_limit=True,
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

    async def replace_short_url(self, status: tweepy.models.Status) -> str:
        """
        Replaces the content of a status with the full URL of the link.
        """
        og_text = status.text
        if hasattr(status, "entities"):
            entity_media = status.entities.get("media", [])
            for media in entity_media:
                media_url = media.get("url")
                full_url = media.get("expanded_url")
                if media_url and full_url:
                    og_text = og_text.replace(media_url, full_url)
            entity_urls = status.entities.get("urls", [])
            for url in entity_urls:
                media_url = url.get("url")
                full_url = url.get("expanded_url")
                if media_url and full_url:
                    og_text = og_text.replace(media_url, full_url)
        if hasattr(status, "extended_entities"):
            extended_media = status.extended_entities.get("media", [])
            for media in extended_media:
                media_url = media.get("url")
                full_url = media.get("expanded_url")
                if media_url and full_url:
                    og_text = og_text.replace(media_url, full_url)
        return og_text

    async def build_tweet_embed(self, status: tweepy.models.Status) -> discord.Embed:
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
                text = await self.replace_short_url(status)
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
                text = await self.replace_short_url(status)
        if status.in_reply_to_screen_name:
            api = await self.authenticate()
            try:
                reply = api.lookup_statuses(id=[status.in_reply_to_status_id])[0]
                # log.debug(reply)
                in_reply_to = _("In reply to {name} (@{screen_name})").format(
                    name=reply.user.name, screen_name=reply.user.screen_name
                )
                reply_text = unescape(await self.replace_short_url(reply))
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
    async def on_tweet_status(self, status: tweepy.models.Status) -> None:
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
            if channel_send.guild.me.is_timed_out():
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
        status: tweepy.models.Status,
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
