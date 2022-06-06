import asyncio
import logging
from html import unescape
from typing import Any, Dict, List, Optional, Union

import discord
import tweepy
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils import bounded_gather
from redbot.core.utils.chat_formatting import escape
from tweepy.asynchronous import AsyncStreamingClient

from .tweet_entry import TweetEntry

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")

USER_FIELDS = [
    "created_at",
    "description",
    "entities",
    "public_metrics",
    "profile_image_url",
    "location",
    "pinned_tweet_id",
    "protected",
    "url",
    "verified",
]
TWEET_FIELDS = [
    "attachments",
    "author_id",
    "created_at",
    "entities",
    "in_reply_to_user_id",
    "lang",
    "public_metrics",
    "possibly_sensitive",
    "referenced_tweets",
]
EXPANSIONS = [
    "author_id",
    "referenced_tweets.id",
    "entities.mentions.username",
    "referenced_tweets.id.author_id",
    "attachments.media_keys",
]
MEDIA_FIELDS = [
    "duration_ms",
    "height",
    "media_key",
    "preview_image_url",
    "type",
    "url",
    "width",
    "alt_text",
]


class MissingTokenError(Exception):
    async def send_error(self, ctx: commands.Context):
        await ctx.send(
            _(
                "You need to set your API tokens. See `{prefix}tweetset creds` for information on how."
            ).format(prefix=ctx.clean_prefix)
        )


class TweetListener(AsyncStreamingClient):
    def __init__(
        self,
        bearer_token: str,
        bot: Red,
    ):
        super().__init__(
            bearer_token=bearer_token,
            wait_on_rate_limit=True,
        )
        self.bot = bot

    async def on_response(self, response: tweepy.StreamResponse) -> None:
        self.bot.dispatch("tweet", response)

    async def on_errors(self, errors: dict) -> None:
        msg = _("A tweet stream error has occured! ") + str(errors)
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
        base_sleep = 300
        count = 1
        while self.run_stream:
            tokens = await self.bot.get_shared_api_tokens("twitter")
            if not tokens:
                # Don't run the loop until tokens are set
                await asyncio.sleep(base_sleep)
                continue
            # if not api:
            # api = await self.authenticate()
            bearer_token = tokens.get("bearer_token", None)
            if bearer_token is None:
                await asyncio.sleep(base_sleep)
                continue
            self.mystream = TweetListener(bearer_token=bearer_token, bot=self.bot)
            if self.stream_task is None:
                await self._start_stream()
            if self.stream_task and (self.stream_task.cancelled() or self.stream_task.done()):
                count += 1
                await self._start_stream()
            log.debug(f"tweets waiting {base_sleep * count} seconds.")
            await asyncio.sleep(base_sleep * count)

    async def _start_stream(self) -> None:
        try:
            self.stream_task = self.mystream.filter(
                expansions=EXPANSIONS,
                media_fields=MEDIA_FIELDS,
                tweet_fields=TWEET_FIELDS,
                user_fields=USER_FIELDS,
            )
        except Exception:
            log.exception("Error starting stream")

    async def authenticate(self) -> tweepy.API:
        """Authenticate with Twitter's API"""
        keys = await self.bot.get_shared_api_tokens("twitter")
        bearer_token = keys.get("bearer_token")
        consumer = keys.get("consumer_key")
        consumer_secret = keys.get("consumer_secret")
        access_token = keys.get("access_token")
        access_secret = keys.get("access_secret")
        keys = [bearer_token, consumer, consumer_secret, access_token, access_secret]
        if any([k is None for k in keys]):
            raise MissingTokenError()
        # auth = tweepy.OAuthHandler(consumer, consumer_secret)
        # auth.set_access_token(access_token, access_secret)
        return tweepy.asynchronous.AsyncClient(
            bearer_token=bearer_token,
            consumer_key=consumer,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            wait_on_rate_limit=True,
        )

    async def autotweet_restart(self) -> None:
        if self.mystream is not None:
            self.mystream.disconnect()
        self.twitter_loop.cancel()
        self.twitter_loop = asyncio.create_task(self.start_stream())

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

    async def get_user(self, user_id: int, includes: Optional[dict]) -> tweepy.User:
        if includes:
            for user in includes.get("users", []):
                if user.id == user_id:
                    return user
        api = await self.authenticate()
        resp = await api.get_user(id=user_id, user_fields=USER_FIELDS)
        return resp.data

    async def get_tweet(self, tweet_id: int, includes: Optional[dict]) -> tweepy.Tweet:
        if includes:
            for tweet in includes.get("tweets", []):
                if tweet_id == tweet.id:
                    return tweet
        api = await self.authenticate()
        resp = await api.get_tweet(id=tweet_id, tweet_fields=TWEET_FIELDS)
        return resp.data

    async def get_media_url(
        self, media_key: str, includes: Optional[dict]
    ) -> Optional[tweepy.Media]:
        if includes:
            for media in includes.get("media", []):
                if media_key == media.media_key:
                    return media
        return None

    async def build_tweet_embed(
        self, response: tweepy.StreamResponse
    ) -> Dict[str, Union[List[discord.Embed], str]]:
        embeds = []
        tweet = response.data
        includes = response.includes

        user_id = tweet.author_id
        author = await self.get_user(user_id, includes)
        username = author.username
        post_url = "https://twitter.com/{}/status/{}".format(username, tweet.id)
        em = discord.Embed(
            url=post_url,
            timestamp=tweet.created_at,
        )
        em.set_footer(text=f"@{username}")
        em.set_author(name=author.name, url=post_url, icon_url=author.profile_image_url)
        text = tweet.text
        em.description = escape(unescape(text), formatting=True)
        if tweet.attachments:
            for media_key in tweet.attachments.get("media_keys", []):
                copy = em.copy()
                media = await self.get_media_url(media_key, includes)
                if media is None:
                    continue
                copy.set_image(url=media.url)
                embeds.append(copy)

        if not embeds:
            embeds.append(em)
        return {"embeds": embeds, "content": str(post_url)}

    @commands.Cog.listener()
    async def on_tweet(self, response: tweepy.StreamResponse) -> None:
        log.info(response)
        tweet = response.data
        user = await self.get_user(tweet.author_id, response.includes)
        to_send = await self.build_tweet_embed(response)
        all_channels = await self.config.all_channels()
        tasks = []
        for channel_id, data in all_channels.items():
            guild = self.bot.get_guild(data.get("guild_id", ""))
            if guild is None:
                continue
            channel = guild.get_channel(int(channel_id))
            if channel is None:
                continue
            if str(user.id) in data.get("followed_accounts", {}):
                tasks.append(
                    self.post_tweet_status(
                        channel, to_send["embeds"], to_send["content"], tweet, user
                    )
                )
                continue
            for rule in response.matching_rules:
                if rule.tag in data.get("followed_rules", {}):
                    tasks.append(
                        self.post_tweet_status(
                            channel, to_send["embeds"], to_send["content"], tweet, user
                        )
                    )
                    continue
            for phrase in data.get("followed_str", {}):
                if phrase in tweet.text:
                    tasks.append(
                        self.post_tweet_status(
                            channel, to_send["embeds"], to_send["content"], tweet, user
                        )
                    )
                    continue
        await bounded_gather(*tasks, return_exceptions=True)

    async def post_tweet_status(
        self,
        channel: discord.TextChannel,
        embeds: List[discord.Embed],
        content: str,
        tweet: tweepy.Tweet,
        user: tweepy.User,
    ):
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, channel.guild):
                return
        try:
            if channel.permissions_for(channel.guild.me).embed_links:
                await channel.send(content, embeds=embeds)
            elif channel.permissions_for(channel.guild.me).manage_webhooks:
                webhook = None
                for hook in await channel.webhooks():
                    if hook.name == channel.guild.me.name:
                        webhook = hook
                if webhook is None:
                    webhook = await channel.create_webhook(name=channel.guild.me.name)
                avatar = user.profile_image_url
                await webhook.send(
                    content, username=user.username, avatar_url=avatar, embeds=embeds
                )
            else:
                await channel.send(content)
        except Exception:
            log.exception(f"Could not post a tweet in {repr(channel)} for account {user}")
