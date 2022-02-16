import asyncio
import functools
import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import discord
import tweepy
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list, humanize_number, pagify

from .menus import BaseMenu, TweetListPages, TweetPages, TweetsMenu
from .tweet_entry import ChannelData, TweetEntry
from .tweets_api import MissingTokenError, TweetsAPI

_ = Translator("Tweets", __file__)

log = logging.getLogger("red.trusty-cogs.Tweets")


@cog_i18n(_)
class Tweets(TweetsAPI, commands.Cog):
    """
    Cog for displaying info from Twitter's API
    """

    __author__ = ["Palm__", "TrustyJAID"]
    __version__ = "2.8.2"

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
            "error_guild": None,
            "schema_version": 0,
        }
        self.config.register_global(**default_global)
        self.config.register_channel(custom_embeds=True)
        self.mystream = None
        self.run_stream = True
        self.twitter_loop = None
        self.accounts = {}
        self.bot.loop.create_task(self.initialize())

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    def cog_unload(self) -> None:
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

    async def initialize(self) -> None:
        if 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("tweets", lambda x: self)
            except Exception:
                pass
        data = await self.config.accounts()
        for name, account in data.items():
            self.accounts[name] = TweetEntry.from_json(account)
        schema_version = await self.config.schema_version()
        if schema_version == 0:
            try:
                await self._schema_0_to_1()
            except Exception:
                return
            schema_version += 1
            await self.config.schema_version.set(schema_version)
        self.twitter_loop = asyncio.create_task(self.start_stream())

    async def _schema_0_to_1(self) -> None:
        try:
            api_keys = await self.config.api()
            if any(v != "" for k, v in api_keys.items()):
                log.debug("Setting api keys to shared tokens")
                await self.bot.set_shared_api_tokens("twitter", **api_keys)
            await self.config.api.clear()
        except Exception:
            log.exception("Error setting api tokens")
            raise

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
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        try:

            if ctx.message.attachments != []:
                temp = BytesIO()
                filename = ctx.message.attachments[0].filename
                await ctx.message.attachments[0].save(temp)
                api.update_status_with_media(filename, status=message, file=temp)
            else:
                api.update_status(message)
        except Exception:
            log.error("Error sending tweet", exc_info=True)
            await ctx.send(_("An error has occured, check the console for more details."))
            return
        await ctx.send(_("Tweet sent!"))

    @_tweets.command(name="trends")
    async def trends(self, ctx: commands.Context, *, location: str = "United States") -> None:
        """
        Gets twitter trends for a given location

        You can provide a location and it will try to get
        different trend information from that location
        default is `United States`
        """
        try:
            api = await self.authenticate()
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        try:
            fake_task = functools.partial(api.available_trends)
            task = self.bot.loop.run_in_executor(None, fake_task)
            location_list = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            await ctx.send(_("Timed out getting twitter trends."))
            return
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
            fake_task = functools.partial(api.get_place_trends, country_id["woeid"])
            task = self.bot.loop.run_in_executor(None, fake_task)
            trends = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            await ctx.send(_("Timed out getting twitter trends."))
            return
        em = discord.Embed(
            colour=await self.bot.get_embed_colour(ctx.channel), title=country_id["name"]
        )
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

    async def get_twitter_user(self, username: str) -> tweepy.User:
        try:
            api = await self.authenticate()
            fake_task = functools.partial(api.get_user, screen_name=username)
            task = self.bot.loop.run_in_executor(None, fake_task)
            user = await asyncio.wait_for(task, timeout=10)
        except asyncio.TimeoutError:
            raise
        except tweepy.errors.TweepyException:
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
        except tweepy.errors.TweepyException:
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
        emb.add_field(name="Followers", value=humanize_number(user.followers_count))
        emb.add_field(name="Friends", value=humanize_number(user.friends_count))
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
        await TweetsMenu(
            source=TweetPages(api=api, username=username, loop=ctx.bot.loop), cog=self
        ).start(ctx=ctx)

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
        if channel is None:
            channel = ctx.channel
        await self.config.error_channel.set(channel.id)
        await self.config.error_guild.set(channel.guild.id)
        await ctx.send(_("Twitter error channel set to {channel}").format(channel=channel.mention))

    @_autotweet.command(name="cleanup")
    @checks.is_owner()
    async def tweets_cleanup(self, ctx: commands.context) -> None:
        """Searches for unavailable channels and removes posting in those channels"""
        to_delete = []
        for user_id, account in self.accounts.items():
            to_rem = []
            for channel_id in account.channels:
                chn = self.bot.get_channel(int(channel_id))
                if chn is None or not chn.permissions_for(ctx.me).send_messages:
                    # log.debug("Removing channel {}".format(channel_id))
                    to_rem.append(channel_id)
            for channel in to_rem:
                del self.accounts[user_id].channels[channel]
            if len(self.accounts[user_id].channels) == 0:
                log.info("Removing account %s from being followed", account.twitter_name)
                to_delete.append(user_id)
        for u_id in to_delete:
            del self.accounts[u_id]
        await self.save_accounts()

    @_autotweet.command(name="embeds")
    async def set_custom_embeds(
        self,
        ctx: commands.context,
        channel: discord.TextChannel,
        true_or_false: bool,
        *usernames: str,
    ) -> None:
        """
        Set whether to use custom embeds or just post the tweet url

        `<channel>` The channel the usernames are posting in
        `<true_or_false>` `true` if you want custom embeds to be used or `false` if not.
        `[usernames...]` The usernames you want to edit the replies setting for.
        This must be the users @handle with spaces signifying a different account.
        """
        if len(usernames) == 0:
            await ctx.send_help()
            return
        added_replies = []
        for username in usernames:
            username = username.lower()
            edited_account = None
            for user_id, accounts in self.accounts.items():
                if accounts.twitter_name.lower() == username:
                    edited_account = user_id
            if edited_account is None:
                continue
            else:
                # all_accounts.remove(edited_account)
                if str(channel.id) not in self.accounts[edited_account].channels:
                    await ctx.send(
                        _("{username} is not posting in {channel}").format(
                            username=username, channel=channel.mention
                        )
                    )
                    return
                self.accounts[edited_account].channels[str(channel.id)].embeds = true_or_false
                added_replies.append(username)

        await self.save_accounts()
        msg = ""
        if added_replies:
            msg += _(
                "Tweets in {channel} {verb} use custom embeds for the following accounts:\n {replies}"
            ).format(
                channel=channel.mention,
                verb=_("will") if true_or_false else _("will not"),
                replies=humanize_list(added_replies),
            )
        else:
            msg = _("No accouts were found in {channel}.").format(channel=channel.mention)
        await ctx.send(msg)

    @_autotweet.command(name="restart")
    async def restart_stream(self, ctx: commands.context) -> None:
        """Restarts the twitter stream if any issues occur."""
        await ctx.channel.trigger_typing()
        await self.autotweet_restart()
        await ctx.send(_("Restarting the twitter stream."))

    @_autotweet.command(name="replies")
    async def _replies(
        self,
        ctx: commands.context,
        channel: discord.TextChannel,
        true_or_false: bool,
        *usernames: str,
    ) -> None:
        """
        Set an accounts replies being posted

        `<channel>` The channel the usernames are posting in
        `<true_or_false>` `true` if you want replies to be displayed or `false` if not.
        `[usernames...]` The usernames you want to edit the replies setting for.
        This must be the users @handle with spaces signifying a different account.
        """
        if len(usernames) == 0:
            return await ctx.send_help()
        added_replies = []
        for username in usernames:
            username = username.lower()
            edited_account = None
            for user_id, accounts in self.accounts.items():
                if accounts.twitter_name.lower() == username:
                    edited_account = user_id
            if edited_account is None:
                continue
            else:
                # all_accounts.remove(edited_account)
                if str(channel.id) not in self.accounts[edited_account].channels:
                    await ctx.send(
                        _("{username} is not posting in {channel}").format(
                            username=username, channel=channel.mention
                        )
                    )
                    return
                self.accounts[edited_account].channels[str(channel.id)].replies = true_or_false
                added_replies.append(username)

        await self.save_accounts()
        msg = ""
        if added_replies:
            msg += _(
                "Tweets in {channel} {verb} show replies for the following accounts:\n {replies}"
            ).format(
                channel=channel.mention,
                verb=_("will") if true_or_false else _("will not"),
                replies=humanize_list(added_replies),
            )
        else:
            msg = _("No accounts were found in {channel}.").format(channel=channel.mention)
        await ctx.send(msg)

    @_autotweet.command(name="retweets")
    async def _retweets(
        self,
        ctx: commands.context,
        channel: discord.TextChannel,
        true_or_false: bool,
        *usernames: str,
    ) -> None:
        """
        Set an accounts retweets being posted

        `<channel>` The channel the usernames are posting in
        `<true_or_false>` `true` if you want retweets to be displayed or `false` if not.
        `[usernames...]` The usernames you want to edit the replies setting for.
        This must be the users @handle with spaces signifying a different account.
        """
        if len(usernames) == 0:
            await ctx.send_help()
            return
        added_replies = []
        for username in usernames:
            username = username.lower()
            edited_account = None
            for user_id, accounts in self.accounts.items():
                if accounts.twitter_name.lower() == username:
                    edited_account = user_id
            if edited_account is None:
                continue
            else:
                # all_accounts.remove(edited_account)
                if str(channel.id) not in self.accounts[edited_account].channels:
                    await ctx.send(
                        _("{username} is not posting in {channel}").format(
                            username=username, channel=channel.mention
                        )
                    )
                    return
                self.accounts[edited_account].channels[str(channel.id)].retweets = true_or_false
                added_replies.append(username)

        await self.save_accounts()
        msg = ""
        if added_replies:
            msg += _(
                "Tweets in {channel} {verb} show retweets for the following accounts:\n {replies}"
            ).format(
                channel=channel.mention,
                verb=_("will") if true_or_false else _("will not"),
                replies=humanize_list(added_replies),
            )
        else:
            msg = _("No accounts were found in {channel}.").format(channel=channel.mention)
        await ctx.send(msg)

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
        except tweepy.errors.TweepyException as e:
            msg = _("Whoops! Something went wrong here. The error code is ") + f"{e} {username}"
            log.error(msg, exc_info=True)
            await ctx.send(_("That username does not exist."))
            return
        if user_id is None or screen_name is None:
            await ctx.send(_("That username does not exist."))
            return
        if channel is None:
            channel = ctx.message.channel
        own_perms = channel.permissions_for(ctx.guild.me)
        if not own_perms.send_messages:
            await ctx.send(
                _("I don't have permission to post in {channel}.").format(channel=channel.mention)
            )
            return
        if not own_perms.embed_links and not own_perms.manage_webhooks:
            msg = _(
                "I do not have embed links permission in {channel}, "
                "I recommend enabling that for pretty twitter posts!"
            ).format(channel=channel.mention)

            await ctx.send(msg)
        in_list = str(user_id) in self.accounts
        added = await self.add_account(channel, user_id, screen_name)
        if added:
            await ctx.send(
                _("{username} added to {channel}.").format(
                    username=username, channel=channel.mention
                )
            )
            if not in_list:
                command = f"`{ctx.prefix}autotweet restart`"
                msg = _("Now do {command} when you've finished adding all accounts!").format(
                    command=command
                )

                await ctx.send(msg)
        else:
            msg = _("I am already posting {username} in {channel}.").format(
                username=username, channel=channel.mention
            )
            await ctx.send(msg)

    @_autotweet.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def _list(self, ctx: commands.context) -> None:
        """Lists the autotweet accounts on the guild"""
        guild = ctx.message.guild
        async with ctx.typing():
            account_list = {}
            async for user_id, account in AsyncIter(self.accounts.items(), steps=50):
                for channel_id, channel_data in account.channels.items():
                    if chan := guild.get_channel(int(channel_id)):
                        chan_info = f"{account.twitter_name} - {channel_data}\n"
                        if chan not in account_list:
                            account_list[chan] = [chan_info]
                        else:
                            account_list[chan].append(chan_info)
            account_str = ""
            for chan, accounts in account_list.items():
                account_str += f"{chan.mention} - {humanize_list(accounts)}"
            embed_list = []
            for page in pagify(account_str):
                embed = discord.Embed(
                    title="Twitter accounts posting in {}".format(guild.name),
                    colour=await self.bot.get_embed_colour(ctx.channel),
                    description=page,
                )
                embed.set_author(name=guild.name, icon_url=guild.icon_url)
                embed_list.append(embed)
        if not embed_list:
            await ctx.send(_("There are no Twitter accounts posting in this server."))
            return
        await BaseMenu(source=TweetListPages(embed_list)).start(ctx=ctx)

    async def save_accounts(self) -> None:
        data = {str(k): v.to_json() for k, v in self.accounts.items()}
        await self.config.accounts.set(data)

    async def add_account(
        self, channel: discord.TextChannel, user_id: int, screen_name: str
    ) -> bool:
        """
        Adds a twitter account to the specified channel.
        Returns False if it is already in the channel.
        """

        if str(user_id) in self.accounts:
            if str(channel.id) in self.accounts[str(user_id)].channels:
                return False
            else:
                self.accounts[str(user_id)].channels[str(channel.id)] = ChannelData(
                    guild=channel.guild.id,
                    replies=False,
                    retweets=True,
                    embeds=True,
                )
                await self.save_accounts()
        else:
            channels = {str(channel.id): ChannelData(guild=channel.guild.id)}
            twitter_account = TweetEntry(
                twitter_id=user_id, twitter_name=screen_name, channels=channels, last_tweet=0
            )
            self.accounts[str(user_id)] = twitter_account
            await self.save_accounts()
        return True

    def get_tweet_list(self, api: tweepy.API, owner: str, list_name: str) -> List[int]:
        cursor = -1
        list_members: list = []
        for member in tweepy.Cursor(
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
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Add an entire twitter list to a specified channel.

        The list must be public or the bot owner must own it.
        `owner` is the owner of the list's @handle
        `list_name` is the name of the list
        `channel` is the channel where the tweets will be posted
        """
        try:
            api = await self.authenticate()
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        try:
            fake_task = functools.partial(
                self.get_tweet_list, api=api, owner=owner, list_name=list_name
            )
            task = ctx.bot.loop.run_in_executor(None, fake_task)
            list_members = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            msg = _("Adding that tweet list took too long.")
            log.error(msg, exc_info=True)
            await ctx.send(msg)
            return
        except Exception:
            log.error("Error adding list", exc_info=True)
            msg = _("That `owner` and `list_name` " "don't appear to be available")
            await ctx.send(msg)
            return
        if channel is None:
            channel = ctx.channel
        own_perms = channel.permissions_for(ctx.me)
        if not own_perms.send_messages:
            await ctx.send(
                _("I don't have permission to post in {channel}.").format(channel=channel.mention)
            )
            return
        if not own_perms.embed_links and not own_perms.manage_webhooks:
            msg = _(
                "I do not have embed links permission in {channel}, "
                "I recommend enabling that for pretty twitter posts!"
            ).format(channel=channel.mention)

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
            command = f"`{ctx.prefix}autotweet restart`"
            msg = _("Now do {commant} when you've finished adding all accounts!").format(
                command=command
            )
            await ctx.send(msg)
        if len(missed_accounts) != 0:
            msg = humanize_list(member for member in missed_accounts)
            msg_send = _(
                "The following accounts could not be added to {channel}:\n{accounts}"
            ).format(channel=channel.mention, accounts=msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    @_autotweet.command(name="remlist")
    async def rem_list(
        self,
        ctx: commands.context,
        owner: str,
        list_name: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Remove an entire twitter list from a specified channel.

        The list must be public or the bot owner must own it.
        `owner` is the owner of the list's @handle
        `list_name` is the name of the list
        `channel` is the channel where the tweets will be posted
        """
        try:
            api = await self.authenticate()
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        try:
            fake_task = functools.partial(
                self.get_tweet_list, api=api, owner=owner, list_name=list_name
            )
            task = ctx.bot.loop.run_in_executor(None, fake_task)
            list_members = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            msg = _("Adding that tweet list took too long.")
            log.error(msg, exc_info=True)
            await ctx.send(msg)
            return
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
            msg = humanize_list(member for member in removed_accounts)
            msg_send = _("Removed the following accounts from {channel}:\n{accounts}").format(
                channel=channel.mention, accounts=msg
            )
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)
        if len(missed_accounts) != 0:
            msg = ", ".join(member for member in missed_accounts)
            msg_send = _(
                "The following accounts weren't added to {channel} or "
                "there was another error: {accounts}"
            ).format(channel=channel.mention, accounts=msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    async def del_account(
        self, channel_id: int, user_id: Optional[int], screen_name: Optional[str]
    ) -> Optional[Dict[str, str]]:
        removed: Dict[str, str] = {}
        if user_id and str(user_id) not in self.accounts:
            return removed

        elif user_id and channel_id in self.accounts[str(user_id)].channels:
            removed[str(user_id)] = self.accounts[str(user_id)].twitter_name
            del self.accounts[str(user_id)].channels[str(channel_id)]

            if len(self.accounts[str(user_id)].channels) < 1:
                del self.accounts[str(user_id)]

        else:
            to_rem_ids = []
            async for user_id, data in AsyncIter(self.accounts.items()):
                if screen_name is not None:
                    if (
                        screen_name.lower() == data.twitter_name.lower()
                        and str(channel_id) in data.channels
                    ):
                        del self.accounts[user_id].channels[str(channel_id)]
                        removed[str(user_id)] = self.accounts[str(user_id)].twitter_name
                        if len(self.accounts[str(user_id)].channels) < 1:
                            # del self.accounts[str(user_id)]
                            to_rem_ids.append(str(user_id))
                else:
                    if str(channel_id) in data.channels:
                        del self.accounts[user_id].channels[str(channel_id)]
                        removed[str(user_id)] = self.accounts[str(user_id)].twitter_name
                        if len(self.accounts[str(user_id)].channels) < 1:
                            # del self.accounts[str(user_id)]
                            to_rem_ids.append(str(user_id))
            for user_ids in to_rem_ids:
                del self.accounts[user_ids]
        await self.save_accounts()
        return removed

    @_autotweet.command(name="del", aliases=["delete", "rem", "remove"])
    async def _del(
        self, ctx: commands.Context, channel: discord.TextChannel, username: Optional[str]
    ) -> None:
        """
        Removes a twitter username to the specified channel

        `<channel>` The channel in which you want to remove twitter posts for.
        `[username]` Optional @handle name for the user you want to remove.
        If `username` is not provided all users posting in the provided channel
        will be removed.
        """
        try:
            api = await self.authenticate()
        except MissingTokenError as e:
            await e.send_error(ctx)
            return
        user_id: Optional[int] = None
        screen_name: Optional[str] = None
        if username:
            try:
                for status in tweepy.Cursor(api.user_timeline, id=username).items(1):
                    user_id = status.user.id
                    screen_name = status.user.screen_name
            except tweepy.errors.TweepyException as e:
                msg = (
                    _("Whoops! Something went wrong here. The error code is ") + f"{e} {username}"
                )
                log.error(msg, exc_info=True)
                await ctx.send(_("Something went wrong here! Try again"))
                return
        removed = await self.del_account(channel.id, user_id, screen_name)
        if removed:
            accounts = humanize_list([i for i in removed.values()])
            msg = _("The following users have been removed from {channel}:\n{accounts}").format(
                channel=channel.mention, accounts=accounts
            )
            await ctx.send(msg)
        else:
            await ctx.send(
                _("{username} doesn't seem to be posting in {channel}").format(
                    username=username, channel=channel.mention
                )
            )

    @commands.group(name="tweetset")
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
            "access_secret YOUR_ACCESS_SECRET`"
        )
        await ctx.maybe_send_embed(msg)
