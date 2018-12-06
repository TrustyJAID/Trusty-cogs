from typing import Generator, Tuple, Iterable, Any
from random import choice as randchoice
from datetime import datetime as dt
from redbot.core import commands
import discord
import asyncio
import aiohttp
from io import BytesIO
from redbot.core import Config
from redbot.core import checks
from redbot.core.utils.chat_formatting import pagify
from .tweet_entry import TweetEntry
import tweepy as tw



numbs = {
    "next": "➡",
    "back": "⬅",
    "exit": "❌"
}


class TweetListener(tw.StreamListener):

    def __init__(self, api, bot):
        super().__init__(api=api)
        self.bot = bot

    def on_status(self, status):
        # print(status.text)
        self.bot.dispatch("tweet_status", status)
        if self.bot.is_closed():
            return False
        else:
            return True

    def on_error(self, status_code):
        msg = "A tweet stream error has occured! " + str(status_code)
        print(msg)
        self.bot.dispatch("tweet_error", msg)
        if status_code in [420, 504, 503, 502, 500, 400, 401, 403, 404]:
            return False

    def on_disconnect(self, notice):
        msg = "Twitter has sent a disconnect code"
        print(msg)
        self.bot.dispatch("tweet_error", msg)
        return False

    def on_warning(self, notice):
        msg = "Twitter has sent a disconnection warning"
        print(msg)
        self.bot.dispatch("tweet_error", msg)
        return True


class Tweets(getattr(commands, "Cog", object)):
    """
        Cog for displaying info from Twitter's API
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 133926854)
        default_global = {"api": {'consumer_key': '', 'consumer_secret': '',
                                  'access_token': '', 'access_secret': ''}, "accounts": [], "error_channel": None}
        self.config.register_global(**default_global)
        self.mystream = None
        self.loop = bot.loop.create_task(self.start_stream())

    ###################################################################
    # Here is all the logic for handling tweets and tweet creation

    async def start_stream(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Tweets"):
            if self.mystream is None:
                api = await self.authenticate()
                tweet_list = [str(x["twitter_id"]) for x in await self.config.accounts()]
                if tweet_list != []:
                    stream_start = TweetListener(api, self.bot)
                    self.mystream = tw.Stream(api.auth, stream_start, chunk_size=1024, timeout=900.0)
                    self.start_stream_loop(tweet_list)
            if not getattr(self.mystream, "running", False):
                api = await self.authenticate()
                tweet_list = [str(x["twitter_id"]) for x in await self.config.accounts()]
                stream_start = TweetListener(api, self.bot)
                self.mystream = tw.Stream(api.auth, stream_start, chunk_size=1024, timeout=900.0)
                self.start_stream_loop(tweet_list)
            await asyncio.sleep(300)

    def start_stream_loop(self, tweet_list):
        self.mystream.filter(follow=tweet_list, is_async=True)

    async def authenticate(self):
        """Authenticate with Twitter's API"""
        auth = tw.OAuthHandler(await self.config.api.consumer_key(),
                               await self.config.api.consumer_secret())
        auth.set_access_token(await self.config.api.access_token(),
                              await self.config.api.access_secret())
        return tw.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True, retry_count=10, retry_delay=5,
                      retry_errors=[500, 502, 503, 504])

    async def autotweet_restart(self):
        if self.mystream is not None:
            self.mystream.disconnect()
        self.loop.cancel()
        self.loop = self.bot.loop.create_task(self.start_stream())

    async def on_tweet_error(self, error):
        """Posts tweet stream errors to a specified channel"""
        if await self.config.error_channel() is not None:
            channel = self.bot.get_channel(await self.config.error_channel())
            await channel.send(error + "\n See here for more information <https://developer.twitter.com/en/docs/basics/response-codes.html>")
            if "420" in error:
                await channel.send("Maybe you should unload the cog for a while...")
        return

    async def build_tweet_embed(self, status):
        username = status.user.screen_name
        user_id = status.user.id
        post_url = "https://twitter.com/{}/status/{}".format(status.user.screen_name, status.id)
        em = discord.Embed(colour=discord.Colour(value=int(status.user.profile_link_color, 16)),
                           url=post_url,
                           timestamp=status.created_at)
        if hasattr(status, "retweeted_status"):
            em.set_author(name=status.user.name + " Retweeted", url=post_url,
                          icon_url=status.user.profile_image_url)
            status = status.retweeted_status
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    em.set_image(url=status.extended_tweet["entities"]["media"][0]["media_url_https"])
            else:
                text = status.text
        else:
            em.set_author(name=status.user.name, url=post_url, icon_url=status.user.profile_image_url)
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    em.set_image(url=status.extended_tweet["entities"]["media"][0]["media_url_https"])
            else:
                text = status.text
        em.description = text.replace("&amp;", "\n\n")
        em.set_footer(text="@" + username)
        return em

    async def on_tweet_status(self, status):
        """Posts the tweets to the channel"""
        username = status.user.screen_name
        user_id = status.user.id
        account = None
        post_url = "https://twitter.com/{}/status/{}".format(status.user.screen_name, status.id)
        for accounts in await self.get_followed_accounts():
            if accounts.twitter_id == user_id:
                account = accounts
        if not account:
            return
        try:
            if status.in_reply_to_screen_name is not None and not account.replies:
                return
            em = await self.build_tweet_embed(status)
            channel_list = account.channel
            for channel in channel_list:
                try:
                    channel_send = self.bot.get_channel(int(channel))
                    if channel_send is None:
                        await self.del_account(channel, user_id, username)
                    if channel_send.permissions_for(channel_send.guild.me).embed_links:
                        await channel_send.send(post_url, embed=em)
                    elif channel_send.permissions_for(channel_send.guild.me).manage_webhooks:
                        webhook = None
                        for hook in await channel_send.webhooks():
                            if hook.name == channel_send.guild.me.name:
                                webhook = hook
                        if webhook is None:
                            webhook = await channel_send.create_webhook(name=channel_send.guild.me.name)
                        avatar = status.user.profile_image_url
                        await webhook.send(post_url, username=username, avatar_url=avatar, embed=em)
                    else:
                        await channel_send.send(post_url)
                except Exception as e:
                    msg = "{0} from <#{1}>({1}): {2}".format(username, channel, e)
                    error_channel = self.bot.get_channel(await self.config.error_channel())
                    if "FORBIDDEN" in str(e) or "403" in str(e):
                        await error_channel.send("Removing " + msg)
                        await self.del_account(channel, user_id, username)
                    elif "NoneType" in str(e):
                        await error_channel.send("Removing " + msg)
                        await self.del_account(channel, user_id, username)
                    else:
                        await error_channel.send(msg)
                        
        except Exception as e:
            print((f"Whoops! Something went wrong here."
                   f"The error code is {e} {username}"))
            if await self.config.error_channel() is not None:
                error_channel = self.bot.get_channel(await self.config.error_channel())
                await error_channel.send(str(e) + ": Username" + username)
            return


    async def tweet_menu(self, ctx, post_list: list,
                         message: discord.Message = None,
                         page=0, timeout: int = 30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        s = post_list[page]
        if ctx.channel.permissions_for(ctx.me).embed_links:
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
        check = lambda react, user: user == ctx.message.author and react.emoji in ["➡", "⬅",
                                                                                   "❌"] and react.message.id == message.id
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", ctx.me)
            await message.remove_reaction("❌", ctx.me)
            await message.remove_reaction("➡", ctx.me)
            return None
        else:
            reacts = {v: k for k, v in numbs.items()}
            react = reacts[react.emoji]
            if react == "next":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("➡", ctx.message.author)
                return await self.tweet_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            elif react == "back":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.tweet_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()

    ###################################################################
    # here are all the commands for getting twitter info

    @commands.group(no_pm=True, name='tweets', aliases=["twitter"])
    async def _tweets(self, ctx):
        """Gets various information from Twitter's API"""
        pass

    @_tweets.command(name="send")
    @checks.is_owner()
    async def send_tweet(self, ctx, *, message: str):
        """
            Allows the owner to send tweets through discord

            Upload an image to send an image with it as well.
        """
        try:
            api = await self.authenticate()
            if ctx.message.attachments != []:
                temp = BytesIO()
                filename = ctx.message.attachments[0].filename
                file_send = await ctx.message.attachments[0].save(temp)
                api.update_with_media(filename, status=message, file=temp)
            else:
                api.update_status(message)
        except Exception as e:
            print(e)
            await ctx.send("An error has occured, check the console for more details.")
            return
        await ctx.send("Tweet sent!")

    def random_colour(self):
        """Returns a random hex colour for discord.Colour() objects"""
        return int(''.join([randchoice('0123456789ABCDEF') for x in range(6)]), 16)

    @_tweets.command(pass_context=True, name="trends")
    async def trends(self, ctx, *, location: str = "United States"):
        """
            Gets twitter trends for a given location

            You can provide a location and it will try to get
            different trend information from that location
            default is `United States`
        """
        api = await self.authenticate()
        location_list = api.trends_available()
        country_id = None
        location_names = []
        for locations in location_list:
            location_names.append(locations["name"])
            if location.lower() in locations["name"].lower():
                country_id = locations
        if country_id is None:
            await ctx.send("{} Is not a correct location!".format(location))
            return
        trends = api.trends_place(country_id["woeid"])[0]["trends"]
        em = discord.Embed(colour=discord.Colour(value=self.random_colour()),
                           title=country_id["name"])
        msg = ""
        for trend in trends[:25]:
            # trend = trends[0]["trends"][i]
            if trend["tweet_volume"] is not None:
                msg += "{}. [{}]({}) Volume: {}\n".format(trends.index(trend) + 1, trend["name"], trend["url"],
                                                          trend["tweet_volume"])
            else:
                msg += "{}. [{}]({})\n".format(trends.index(trend) + 1, trend["name"], trend["url"])
        em.description = msg[:2000]
        em.timestamp = dt.utcnow()
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(embed=em)
        else:
            await ctx.send("```\n{}```".format(msg[:1990]))

    @_tweets.command(no_pm=True, name='getuser')
    async def get_user(self, ctx, username: str):
        """Get info about the specified user"""
        try:
            api = await self.authenticate()
            user = api.get_user(username)
        except tw.error.TweepError as e:
            await ctx.send(e)
            return
        profile_url = "https://twitter.com/" + user.screen_name
        description = str(user.description)
        for url in user.entities["description"]["urls"]:
            if str(url["url"]) in description:
                description = description.replace(url["url"], str(url["expanded_url"]))
        emb = discord.Embed(colour=discord.Colour(value=int(user.profile_link_color, 16)),
                            url=profile_url,
                            description=str(description),
                            timestamp=user.created_at)
        emb.set_author(name=user.name, url=profile_url, icon_url=user.profile_image_url)
        emb.set_thumbnail(url=user.profile_image_url)
        emb.add_field(name="Followers", value=user.followers_count)
        emb.add_field(name="Friends", value=user.friends_count)
        if user.verified:
            emb.add_field(name="Verified", value="Yes")
        footer = "Created at "
        emb.set_footer(text=footer)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send("<"+profile_url+">", embed=emb)
        else:
            await ctx.send(profile_url)

    @_tweets.command(no_pm=True, name='gettweets')
    async def get_tweets(self, ctx, username: str, count: int = 10):
        """
            Display a users tweets as a scrollable message

            defaults to 10 tweets
        """
        cnt = count
        if count > 25:
            cnt = 25
        followed_accounts = [x for x in await self.config.accounts()]
        if username.lower() in [x["twitter_name"].lower() for x in followed_accounts]:
            account = [x for x in followed_accounts if username.lower() == x["twitter_name"].lower()]
            replies_on = account[0]["replies"]
        else:
            replies_on = False
        if username is not None:
            msg_list = []
            api = await self.authenticate()
            try:
                for status in \
                        tw.Cursor(api.user_timeline, id=username).items(cnt):
                    if status.in_reply_to_screen_name is not None and not replies_on:
                        continue
                    msg_list.append(status)
            except tw.TweepError as e:
                await ctx.send("Whoops! Something went wrong here. \
                    The error code is " + str(e))
                return
            if len(msg_list) > 0:
                await self.tweet_menu(ctx, msg_list, page=0, timeout=30)
            else:
                await ctx.send("No tweets available to display!")
        else:
            await ctx.send("No username specified!")
            return

    @commands.group(name='autotweet')
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def _autotweet(self, ctx):
        """Command for setting accounts and channels for posting"""
        pass

    @_autotweet.command(name="error")
    @checks.is_owner()
    async def _error(self, ctx, channel: discord.TextChannel = None):
        """Set an error channel for tweet stream error updates"""
        if not channel:
            channel = ctx.channel
        await self.config.error_channel.set(channel.id)
        await ctx.send("Twitter error channel set to {}".format(channel.mention))

    @_autotweet.command(name="cleanup")
    @checks.is_owner()
    async def tweets_cleanup(self, ctx):
        """Searches for unavailable channels and removes posting in those channels"""
        account_list = await self.config.accounts()
        for account in account_list:
            for channel in account["channel"]:
                chn = self.bot.get_channel(channel)
                if chn is None:
                    print("Removing channel {}".format(channel))
                    account_list.remove(account)
                    account["channel"].remove(channel)
                    account_list.append(account)
            if len(account["channel"]) == 0:
                print("Removing account {}".format(account["twitter_name"]))
                account_list.remove(account)
        await self.config.accounts.set(account_list)

    @_autotweet.command(name="restart")
    async def restart_stream(self, ctx):
        """Restarts the twitter stream if any issues occur."""
        await ctx.channel.trigger_typing()
        await self.autotweet_restart()
        await ctx.send("Restarting the twitter stream.")

    @_autotweet.command(name="replies")
    async def _replies(self, ctx, account):
        """
            Toggle an accounts replies being posted

            This is checked on `autotweet` as well as `gettweets`
        """
        account = account.lower()
        edited_account = None
        all_accounts = await self.config.accounts()
        for accounts in all_accounts:
            if accounts["twitter_name"].lower() == account:
                edited_account = accounts
        if edited_account is None:
            await ctx.send("I am not tracking {}".format(account))
            return
        else:
            all_accounts.remove(edited_account)
            edited_account["replies"] = not edited_account["replies"]
            all_accounts.append(edited_account)
            await self.config.accounts.set(all_accounts)
            if edited_account["replies"]:
                await ctx.send(f"Posting {account} replies.")
            else:
                await ctx.send(f"No longer posting {account} replies.")

    async def get_followed_accounts(self) -> Generator[TweetEntry, None, None]:
        return (TweetEntry.from_json(d) for d in (await self.config.accounts()))

    async def is_followed_account(self, twitter_id) -> Tuple[bool, Any]:
        followed_accounts = await self.config.accounts()

        for account in followed_accounts:
            if account["twitter_id"] == twitter_id:
                return True, account
        return False, None

    @_autotweet.command(name="add")
    async def _add(self, ctx, account: str, channel: discord.TextChannel = None):
        """
            Adds a twitter account to the specified channel

            `account` needs to be the @handle for the twitter account
            `channel` has to be a valid server channel, defaults to the current channel
        """
        api = await self.authenticate()
        try:
            user_id = None
            screen_name = None
            last_id = None
            for status in tw.Cursor(api.user_timeline, id=account).items(1):
                user_id = status.user.id
                screen_name = status.user.screen_name
                last_id = status.id
        except tw.TweepError as e:
            print("Whoops! Something went wrong here. \
                    The error code is " + str(e) + account)
            await ctx.send("That account does not exist! Try again")
            return
        if user_id is None:
            await ctx.send("No status was retrieved! Try again")
            return
        if channel is None:
            channel = ctx.message.channel
        own_perms = channel.permissions_for(ctx.guild.me)
        if not own_perms.send_messages:
            await ctx.send("I don't have permission to post in {}".format(channel.mention))
            return
        if not own_perms.embed_links and not own_perms.manage_webhooks:
            msg = (f"I do not have embed links or manage webhooks permission in {channel.mention}, "
                   "I recommend enabling that for pretty twitter posts!")
            await ctx.send(msg)
        in_list = True if str(user_id) in [str(x["twitter_id"]) for x in await self.config.accounts()] else False
        added = await self.add_account(channel, user_id, screen_name)
        if added:
            await ctx.send("{0} Added to {1}!".format(account, channel.mention))
            if not in_list:
                prefix_list = await self.bot.command_prefix(self.bot, ctx.message)
                msg = (f"Now do `{prefix_list[0]}autotweet restart` when you've "
                       "finished adding all accounts!")
                await ctx.send(msg)
        else:
            await ctx.send(f"I am already posting {screen_name} tweets in {channel.mention}")
        # await self.autotweet_restart()

    @_autotweet.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def _list(self, ctx):
        """Lists the autotweet accounts on the guild"""
        account_list = ""
        guild = ctx.message.guild

        accounts = [x for x in await self.config.accounts()]
        embed = discord.Embed(title="Twitter accounts posting in {}".format(guild.name),
                              colour=discord.Colour(value=self.random_colour()),
                              # description=account_list[:-2],
                              timestamp=ctx.message.created_at)
        embed.set_author(name=guild.name, icon_url=guild.icon_url)
        for channel in guild.channels:
            account_list = ""
            for account in accounts:
                if channel.id in account["channel"]:
                    account_list += account["twitter_name"] + ", "
            if account_list != "":
                embed.add_field(name=channel.name, value=account_list[:-2])
        await ctx.send(embed=embed)

    async def add_account(self, channel, user_id, screen_name):
        """
            Adds a twitter account to the specified channel. 
            Returns False if it is already in the channel.
        """
        followed_accounts = await self.config.accounts()

        is_followed, twitter_account = await self.is_followed_account(user_id)
        if is_followed:
            if channel.id in twitter_account["channel"]:
                return False
            else:
                followed_accounts.remove(twitter_account)
                twitter_account["channel"].append(channel.id)
                followed_accounts.append(twitter_account)
                await self.config.accounts.set(followed_accounts)
        else:
            twitter_account = TweetEntry(user_id, screen_name, [channel.id], 0)
            followed_accounts.append(twitter_account.to_json())
            await self.config.accounts.set(followed_accounts)
        return True

    @_autotweet.command(name="addlist")
    async def add_list(self, ctx, owner, list_name, channel: discord.TextChannel = None):
        """
            Add an entire twitter list to a specified channel.

            The list must be public or the bot owner must own it.
            `owner` is the owner of the list's @handle
            `list_name` is the name of the list
            `channel` is the channel where the tweets will be posted
        """
        api = await self.authenticate()
        try:
            cursor = -1
            list_members = []
            member_count = api.get_list(owner_screen_name=owner, slug=list_name).member_count
            while len(list_members) < member_count:
                member_list = api.list_members(owner_screen_name=owner, slug=list_name, cursor=cursor)
                for member in member_list[0]:
                    list_members.append(member)
                cursor = member_list[1][-1]
                print("{} members added".format(len(member_list[0])))

        except Exception as e:
            print(e)
            await ctx.send("The owner {} and list name {} don't appear to be available!".format(owner, list_name))
            return
        if channel is None:
            channel = ctx.message.channel
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send("I don't have permission to post in {}".format(channel.mention))
            return
        if not channel.permissions_for(ctx.guild.me).embed_links:
            await ctx.send(
                "I do not have embed links permission in {}, I recommend enabling that for pretty twitter posts!".format(
                    channel.mention))
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
            msg_send = "Added the following accounts to {}: {}".format(channel.mention, msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)
            prefix_list = await self.bot.command_prefix(self.bot, ctx.message)
            await ctx.send("Now do `{}autotweet restart` when you've finished adding all accounts!".format(prefix_list[0]))
        if len(missed_accounts) != 0:
            msg = ", ".join(member for member in missed_accounts)
            msg_send = "The following accounts could not be added to {}: {}".format(channel.mention, msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    @_autotweet.command(name="remlist")
    async def rem_list(self, ctx, owner, list_name, channel: discord.TextChannel = None):
        """
            Remove an entire twitter list from a specified channel. 

            The list must be public or the bot owner must own it.
            `owner` is the owner of the list's @handle
            `list_name` is the name of the list
            `channel` is the channel where the tweets will be posted
        """
        api = await self.authenticate()
        try:
            cursor = -1
            list_members = []
            member_count = api.get_list(owner_screen_name=owner, slug=list_name).member_count
            while len(list_members) < member_count:
                member_list = api.list_members(owner_screen_name=owner, slug=list_name, cursor=cursor)
                for member in member_list[0]:
                    list_members.append(member)
                cursor = member_list[1][-1]
        except:
            await ctx.send("The owner {} and list name {} don't appear to be available!".format(owner, list_name))
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
            msg_send = "Removed the following accounts from {}: {}".format(channel.mention, msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)
        if len(missed_accounts) != 0:
            msg = ", ".join(member for member in missed_accounts)
            msg_send = "The following accounts weren't added to {} or there was another error: {}".format(
                channel.mention, msg)
            for page in pagify(msg_send, ["\n"]):
                await ctx.send(page)

    async def del_account(self, channel_id, user_id, screen_name):
        account_ids = [x["twitter_id"] for x in await self.config.accounts()]
        if user_id not in account_ids:
            return False
        account_list = [x for x in await self.config.accounts()]
        twitter_account = [x for x in account_list if user_id == x["twitter_id"]][0]
        if channel_id in twitter_account["channel"]:
            account_list.remove(twitter_account)
            twitter_account["channel"].remove(channel_id)
            account_list.append(twitter_account)
            await self.config.accounts.set(account_list)
            if len(twitter_account["channel"]) < 1:
                account_list.remove(twitter_account)
                await self.config.accounts.set(account_list)
        return True

    @_autotweet.command(name="del", aliases=["delete", "rem", "remove"])
    async def _del(self, ctx, account, channel: discord.TextChannel = None):
        """
            Removes a twitter account to the specified channel

            `account` must be the users @handle
            `channel` is the channel where the account is currently being posted
        """
        account = account.lower()
        api = await self.authenticate()
        if channel is None:
            channel = ctx.message.channel
        try:
            user_id = None
            screen_name = None
            for status in tw.Cursor(api.user_timeline, id=account).items(1):
                user_id = status.user.id
                screen_name = status.user.screen_name
        except tw.TweepError as e:
            print("Whoops! Something went wrong here. \
                    The error code is " + str(e) + account)
            await ctx.send("Something went wrong here! Try again")
            return
        if user_id is None:
            await ctx.send("No status was retrieved! Try again")
            return
        removed = await self.del_account(channel.id, user_id, screen_name)
        if removed:
            await ctx.send("{} has been removed from {}".format(account, channel.mention))
        else:
            await ctx.send("{0} doesn't seem to be posting in {1}!".format(account, channel.mention))

    @commands.group(name='tweetset')
    @checks.admin_or_permissions(manage_guild=True)
    async def _tweetset(self, ctx):
        """Command for setting required access information for the API.

        1. Visit https://apps.twitter.com and apply for a developer account.
        2. Once your account is approved setup an application and follout the form
        3. Do `[p]tweetset creds consumer_key consumer_secret access_token access_secret`
        to the bot in a private channel (DM's preferred).
        """
        pass

    @_tweetset.command(name='creds')
    @checks.is_owner()
    async def set_creds(self, ctx, consumer_key: str, consumer_secret: str, access_token: str, access_secret: str):
        """[p]tweetset """
        api = {'consumer_key': consumer_key, 'consumer_secret': consumer_secret,
               'access_token': access_token, 'access_secret': access_secret}
        await self.config.api.set(api)
        await ctx.send('Set the access credentials!')

    def __unload(self):
        if self.mystream is not None:
            self.mystream.disconnect()
            self.loop.cancel()
