import asyncio
import logging

import discord
import tweepy
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number

from .menus import BaseMenu, TweetListPages, TweetPages, TweetsMenu
from .tweets_api import USER_FIELDS, MissingTokenError, TweetsAPI

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


@cog_i18n(_)
class Tweets(TweetsAPI, commands.Cog):
    """
    Cog for displaying info from Twitter's API
    """

    __author__ = ["Palm__", "TrustyJAID"]
    __version__ = "3.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 133926854, force_registration=True)
        default_global = {
            "error_channel": None,
            "error_guild": None,
            "schema_version": 0,
        }
        self.config.register_global(**default_global)
        self.config.register_channel(
            followed_accounts={}, followed_str={}, followed_rules={}, guild_id=None
        )
        self.mystream = None
        self.run_stream = True
        self.twitter_loop = None
        self.stream_task = None
        self.accounts = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self) -> None:
        try:
            self.bot.remove_dev_env_value("tweets")
        except Exception:
            pass
        log.debug("Unloading tweets...")
        if self.twitter_loop:
            self.twitter_loop.cancel()
        log.debug("Twitter restart loop canceled.")
        self.run_stream = False
        if self.mystream is not None:
            log.debug("Twitter stream is running, trying to stop.")
            self.mystream.disconnect()
            self.mystream = None
            log.debug("Twitter stream disconnected.")
        log.debug("Tweets unloaded.")

    async def red_delete_data_for_user(self, **kwargs) -> None:
        """
        Nothing to delete
        """
        return

    async def cog_load(self) -> None:
        if self.bot.owner_ids and 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("tweets", lambda x: self)
            except Exception:
                pass
        self.twitter_loop = asyncio.create_task(self.start_stream())

    @commands.group(name="tweets", aliases=["twitter"])
    async def _tweets(self, ctx: commands.Context):
        """Gets various information from Twitter's API"""
        pass

    @_tweets.group(name="stream")
    async def tweets_stream(self, ctx: commands.Context):
        """Controls for the twitter stream"""
        pass

    @_tweets.command(name="send")
    @checks.is_owner()
    async def send_tweet(self, ctx: commands.Context, *, message: str) -> None:
        """
        Allows the owner to send tweets through discord
        """
        try:
            api = await self.authenticate()
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        try:
            api.create_tweet(text=message)
        except Exception:
            log.error("Error sending tweet", exc_info=True)
            await ctx.send(_("An error has occured, check the console for more details."))
            return
        await ctx.send(_("Tweet sent!"))

    async def get_twitter_user(self, username: str) -> tweepy.User:
        try:
            api = await self.authenticate()
            user = await api.get_user(
                username=username,
                user_fields=USER_FIELDS,
            )
        except asyncio.TimeoutError:
            raise
        except tweepy.errors.TweepyException:
            raise
        return user

    @_tweets.command(name="getuser")
    async def get_user(self, ctx: commands.context, username: str) -> None:
        """Get info about the specified user"""
        try:
            resp = await self.get_twitter_user(username)
            user = resp.data
        except asyncio.TimeoutError:
            await ctx.send(_("Looking up the user timed out."))
            return
        except tweepy.errors.TweepyException:
            await ctx.send(_("{username} could not be found.").format(username=username))
            return
        log.info(dir(user))
        profile_url = "https://twitter.com/" + user.username
        description = str(user.description)
        for url in user.entities["description"]["urls"]:
            if str(url["url"]) in description:
                description = description.replace(url["url"], str(url["expanded_url"]))
        emb = discord.Embed(
            url=profile_url,
            description=str(description),
            timestamp=user.created_at,
        )
        emb.set_author(name=user.name, url=profile_url, icon_url=user.profile_image_url)
        emb.set_thumbnail(url=user.profile_image_url)
        emb.add_field(
            name="Followers", value=humanize_number(user.public_metrics["followers_count"])
        )
        emb.add_field(
            name="Following", value=humanize_number(user.public_metrics["following_count"])
        )
        if user.verified:
            emb.add_field(name="Verified", value="Yes")
        footer = "Created at "
        emb.set_footer(text=footer)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send("<" + profile_url + ">", embed=emb)
        else:
            await ctx.send(profile_url)

    @_tweets.command(name="gettweets", aliases=["tweets", "status"])
    @checks.bot_has_permissions(add_reactions=True)
    async def get_tweets(self, ctx: commands.context, username: str) -> None:
        """
        Display a users tweets as a scrollable message
        """
        async with ctx.typing():
            try:
                api = await self.authenticate()
            except MissingTokenError as e:
                await e.send_error(ctx)
                return
        await TweetsMenu(source=TweetPages(api=api, username=username), cog=self).start(ctx=ctx)

    @tweets_stream.command(name="follow")
    @commands.mod_or_permissions(manage_channels=True)
    async def add_follow_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, username: str
    ):
        """
        Add a twitter username to follow in a channel.

        Note: This may not work if the username is not present in one of the stream rules.
        You can view existing rules with `[p]tweets stream rules`
        """
        resp = await self.get_twitter_user(username)
        if not resp.data:
            await ctx.send(
                _("I could not find a user named `{username}`.").format(username=username)
            )
            return
        user = resp.data
        async with self.config.channel(channel).followed_accounts() as accounts:
            if str(user.id) not in accounts:
                accounts[str(user.id)] = {}
        await self.config.channel(channel).guild_id.set(channel.guild.id)
        await ctx.send(
            _("Following tweets from {user} in {channel}.").format(
                user=user.username, channel=channel.mention
            )
        )

    @tweets_stream.command(name="followrule")
    @commands.mod_or_permissions(manage_channels=True)
    async def add_rule_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, rule_tag: str
    ):
        """
        Add all tweets from a specific stream rule to a channel.
        """
        async with self.config.channel(channel).followed_rules() as accounts:
            if str(rule_tag) not in accounts:
                accounts[rule_tag] = {}
        await self.config.channel(channel).guild_id.set(channel.guild.id)
        await ctx.send(
            _("Following tweets from {rule} in {channel}.").format(
                user=rule_tag, channel=channel.mention
            )
        )

    @tweets_stream.command(name="unfollowrule")
    @commands.mod_or_permissions(manage_channels=True)
    async def remove_rule_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, rule_tag: str
    ):
        """
        Remove all tweets from a specific stream rule to a channel.
        """
        async with self.config.channel(channel).followed_rules() as accounts:
            if str(rule_tag) in accounts:
                del accounts[rule_tag]
        await self.config.channel(channel).guild_id.set(channel.guild.id)
        await ctx.send(
            _("Unfollowing tweets from {rule} in {channel}.").format(
                user=rule_tag, channel=channel.mention
            )
        )

    @tweets_stream.command(name="unfollow")
    @commands.mod_or_permissions(manage_channels=True)
    async def remove_follow_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, username: str
    ):
        """
        Add a twitter username to follow in a channel.

        Note: This may not work if the username is not present in one of the stream rules.
        You can view existing rules with `[p]tweets stream rules`
        """
        resp = await self.get_twitter_user(username)
        if not resp.data:
            await ctx.send(
                _("I could not find a user named `{username}`.").format(username=username)
            )
            return
        user = resp.data
        await self.config.channel(channel).guild_id.set(channel.guild.id)
        async with self.config.channel(channel).followed_accounts() as accounts:
            if str(user.id) in accounts:
                del accounts[str(user.id)]
            else:
                await ctx.send(
                    _("Tweets from {user} are not being followed in {channel}").format(
                        user=user.username, channel=channel.mention
                    )
                )
                return
        await ctx.send(
            _("Unfollowing tweets from {user} in {channel}.").format(
                user=user.username, channel=channel.mention
            )
        )

    @tweets_stream.command(name="rules")
    async def stream_rules(self, ctx: commands.Context):
        """List the current stream rules"""
        response = await self.mystream.get_rules()
        if not response.data:
            await ctx.send(_("No rules have been created yet."))
            return
        embeds = []
        for rule in response.data:
            title = f"{rule.tag} ({rule.id})" if rule.tag else f"{rule.id}"
            embeds.append(discord.Embed(title=title, description=rule.value))
        await BaseMenu(source=TweetListPages(embeds)).start(ctx)

    @tweets_stream.command(name="addrule")
    @commands.is_owner()
    async def add_stream_rule(self, ctx: commands.Context, tag: str, *, rule: str):
        """Create a stream rule"""
        rule = tweepy.StreamRule(tag=tag, value=rule)
        resp = await self.mystream.add_rules(rule)
        if not resp.errors:
            await ctx.send(_("Rule created successfully."))
        else:
            error_msg = _("There was an issue with that rule.\n")
            for error in resp.errors:
                for detail in error.get("details", []):
                    error_msg += detail
            await ctx.send(error_msg)

    @tweets_stream.command(name="delrule", aliases=["deleterule", "remrule"])
    @commands.is_owner()
    async def delete_stream_rule(self, ctx: commands.Context, tag_or_id: str):
        """Delete a stream rule"""
        rules = await self.mystream.get_rules()
        response = ""
        for rule in rules.data:
            if rule.tag == tag_or_id:
                resp = await self.mystream.delete_rules(rule.id)
                tag = f"{rule.tag} ({rule.id})" if rule.tag else f"{rule.id}"
                if not resp.errors:
                    response += _("Rule {tag} deleted.\n").format(tag=tag)
                else:
                    error_msg = _("There was an issue with that rule.\n")
                    for error in resp.errors:
                        for detail in error.get("details", []):
                            error_msg += detail
                    response += error_msg
            if rule.id == tag_or_id:
                resp = await self.mystream.delete_rules(rule.id)
                tag = f"{rule.tag} ({rule.id})" if rule.tag else f"{rule.id}"
                if not resp.errors:
                    response += _("Rule {tag} deleted.\n").format(tag=tag)
                else:
                    error_msg = _("There was an issue with that rule.\n")
                    for error in resp.errors:
                        for detail in error.get("details", []):
                            error_msg += detail
                    response += error_msg
        await ctx.send(response)

    @_tweets.group(name="set")
    @checks.admin_or_permissions(manage_guild=True)
    async def _tweetset(self, ctx: commands.Context) -> None:
        """Command for setting required access information for the API.

        1. Visit https://apps.twitter.com and apply for a developer account.
        2. Once your account is approved Create a standalone app and copy the
        **API Key and API Secret**.
        3. On the standalone apps page select regenerate **Access Token and Secret**
        and copy those somewhere safe.
        4. Do `[p]set api twitter
        consumer_key YOUR_CONSUMER_KEY
        consumer_secret YOUR_CONSUMER_SECRET
        access_token YOUR_ACCESS_TOKEN
        access_secret YOUR_ACCESS_SECRET`
        """
        pass

    @_tweetset.command(name="creds")
    @checks.is_owner()
    async def set_creds(
        self,
        ctx: commands.Context,
    ) -> None:
        """How to get and set your twitter API tokens."""
        elevated = "[elevated access](https://developer.twitter.com/en/docs/twitter-api/getting-started/about-twitter-api#Access)"
        msg = _(
            "1. Visit https://apps.twitter.com and apply for a developer account.\n"
            "2. Once your account is approved Create a standalone app and copy the "
            "**API Key and API Secret**\n"
            "3. On the standalone apps page select regenerate **Access Token and Secret** "
            "and copy those somewhere safe.\n\n"
            "4. Do `[p]set api twitter "
            "bearer_token YOUR_BEARER_TOKEN "
            "consumer_key YOUR_CONSUMER_KEY "
            "consumer_secret YOUR_CONSUMER_SECRET "
            "access_token YOUR_ACCESS_TOKEN "
            "access_secret YOUR_ACCESS_SECRET`\n\n"
            "**Note:** You will require {elevated} to use everything in this cog."
        ).format(elevated=elevated)
        await ctx.maybe_send_embed(msg)
