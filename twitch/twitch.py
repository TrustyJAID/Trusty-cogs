import discord
from redbot.core import Config, checks, commands
from redbot.core.commands import Context
from .twitch_profile import TwitchProfile
from .twitch_follower import TwitchFollower
from .errors import *
from datetime import datetime
import asyncio
import aiohttp
import time


BASE_URL = "https://api.twitch.tv/helix"


class Twitch(commands.Cog):
    """
        Get twitch user information and post when a user gets new followers
    """

    global_defaults = {
        "client_id": "",
        "client_secret": "",
        "access_token": {},
        "twitch_accounts": [],
    }
    user_defaults = {"id": "", "login": "", "display_name": ""}

    def __init__(self, bot):
        self.config = Config.get_conf(self, 1543454673)
        self.config.register_global(**self.global_defaults, force_registration=True)
        self.config.register_user(**self.user_defaults, force_registration=True)
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.rate_limit_resets = set()
        self.rate_limit_remaining = 0
        self.loop = bot.loop.create_task(self.check_for_new_followers())

    #####################################################################################
    # Logic for accessing twitch API with rate limit checks                             #
    # https://github.com/tsifrer/python-twitch-client/blob/master/twitch/helix/base.py  #
    #####################################################################################

    async def get_header(self):
        header = {"Client-ID": await self.config.client_id()}
        access_token = await self.config.access_token()
        if access_token != {}:
            # Return bearer token if availavble for more access
            header["Authorization"] = "Bearer {}".format(access_token["access_token"])
        return header

    async def wait_for_rate_limit_reset(self):
        """Check rate limits in response header and ensure we're following them
        https://github.com/tsifrer/python-twitch-client/blob/master/twitch/helix/base.py
        """
        if self.rate_limit_remaining == 0:
            current_time = int(time.time())
            self.rate_limit_resets = set(x for x in self.rate_limit_resets if x > current_time)

            if len(self.rate_limit_resets) > 0:
                reset_time = list(self.rate_limit_resets)[0]
                # Calculate wait time and add 0.1s to the wait time to allow Twitch to reset
                # their counter
                wait_time = reset_time - current_time + 0.1
                await asyncio.sleep(wait_time)

    async def oauth_check(self):
        url = "https://id.twitch.tv/oauth2/token"
        client_id = await self.config.client_id()
        client_secret = await self.config.client_secret()
        access_token = await self.config.access_token()
        if client_secret == "":
            # Can't get the app access token without the client secret being set
            return
        if access_token == {}:
            # Attempts to acquire an app access token
            params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "analytics:read:extensions analytics:read:games bits:read clips:edit user:edit user:edit:broadcast",
            }
            async with self.session.post(url, params=params) as resp:
                access_token = await resp.json()
            await self.config.access_token.set(access_token)
        else:
            if "access_token" not in access_token:
                # Tries to re-aquire access token if set one is incorrect
                await self.config.access_token.set({})
                return await self.oauth_check()
            header = {"Authorization": "OAuth {}".format(access_token["access_token"])}
            url = "https://id.twitch.tv/oauth2/validate"
            resp = await self.session.get(url, headers=header)
            if resp.status == 200:
                # Validates the access token before use
                return
            else:
                await self.config.access_token.set({})
                return await self.oauth_check()

    async def get_response(self, url):
        """Get responses from twitch after checking rate limits"""
        await self.oauth_check()
        header = await self.get_header()
        await self.wait_for_rate_limit_reset()
        resp = await self.session.get(url, headers=header)
        remaining = resp.headers.get("Ratelimit-Remaining")
        if remaining:
            self.rate_limit_remaining = int(remaining)
        reset = resp.headers.get("Ratelimit-Reset")
        if reset:
            self.rate_limit_resets.add(int(reset))

        if resp.status == 429:
            return self.get_response(url)

        return await resp.json()

    #####################################################################################

    async def make_user_embed(self, profile):
        # makes the embed for a twitch profile
        em = discord.Embed(colour=int("6441A4", 16))
        em.description = profile.description
        url = "https://twitch.tv/{}".format(profile.login)
        em.set_author(
            name="{}".format(profile.display_name), url=url, icon_url=profile.profile_image_url
        )
        em.set_image(url=profile.offline_image_url)
        em.set_thumbnail(url=profile.profile_image_url)
        footer_text = "{} Viewer count".format(profile.view_count)
        em.set_footer(text=footer_text, icon_url=profile.profile_image_url)
        return em

    async def make_follow_embed(self, profile, total_followers):
        # makes the embed for a twitch profile
        em = discord.Embed(colour=int("6441A4", 16))
        url = "https://twitch.tv/{}".format(profile.login)
        em.description = "[{}]({}) has just followed!".format(profile.display_name, url)
        em.set_author(
            name="{} has just followed!".format(profile.display_name),
            url=url,
            icon_url=profile.profile_image_url,
        )
        # em.set_image(url=profile.offline_image_url)
        em.set_thumbnail(url=profile.profile_image_url)
        footer_text = "{} followers".format(total_followers)
        em.set_footer(text=footer_text, icon_url=profile.profile_image_url)
        return em

    async def get_all_followers(self, user_id):
        # Get's all of a users current followers
        url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, user_id)
        data = await self.get_response(url)
        follows = [x["from_id"] for x in data["data"]]
        total = data["total"]
        print("{} of {}".format(len(follows), total))
        count = 0
        while len(follows) < total:
            count += 1
            cursor = data["pagination"]["cursor"]
            data = await self.get_response(url + "&after=" + cursor)
            for user in data["data"]:
                if user["from_id"] not in follows:
                    follows.append(user["from_id"])
            print("{} of {}".format(len(follows), total))
            if count == (int(total / 100) + (total % 100 > 0)):
                # Break the loop if we've gone over the total we could theoretically get
                break
        return follows, total

    async def get_profile_from_name(self, twitch_name):
        url = "{}/users?login={}".format(BASE_URL, twitch_name)
        return TwitchProfile.from_json(await self.get_response(url))

    async def get_profile_from_id(self, twitch_id):
        url = "{}/users?id={}".format(BASE_URL, twitch_id)
        return TwitchProfile.from_json(await self.get_response(url))

    async def get_new_followers(self, user_id):
        # Gets the last 100 followers from twitch
        url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, user_id)
        data = await self.get_response(url)
        follows = [TwitchFollower.from_json(x) for x in data["data"]]
        total = data["total"]
        return follows, total

    async def maybe_get_twitch_profile(self, ctx, twitch_name: str):
        if twitch_name is not None:
            # Search for twitch login name
            try:
                profile = await self.get_profile_from_name(twitch_name)
            except Exception as e:
                print(e)
                raise TwitchError("{} is not a valid Twitch username".format(twitch_name))
        else:
            # User has set their twitch ID on the bot
            twitch_id = await self.config.user(ctx.author).id()
            if twitch_id == "":
                raise TwitchError("You must set a twitch ID")
            else:
                profile = await self.get_profile_from_id(twitch_id)
        return profile

    async def check_account_added(self, account_list, profile):
        # Checks if the account is in the config and returns only that one
        account_return = None
        for account in account_list:
            if account["id"] == profile.id:
                account_return = account
        return account_return

    async def check_for_new_followers(self):
        # Checks twitch every minute for new followers
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Twitch"):
            check_accounts = await self.config.twitch_accounts()
            for account in check_accounts:
                followers, total = await self.get_new_followers(account["id"])
                for follow in reversed(followers):
                    if follow.from_id not in account["followers"]:
                        try:
                            profile = await self.get_profile_from_id(follow.from_id)
                        except Exception as e:
                            print(e)
                        print(
                            "{} Followed! You have {} followers now.".format(profile.login, total)
                        )
                        em = await self.make_follow_embed(profile, total)
                        for channel_id in account["channels"]:
                            channel = self.bot.get_channel(id=channel_id)
                            await channel.send(embed=em)
                        check_accounts.remove(account)
                        account["followers"].append(follow.from_id)
                        check_accounts.append(account)
                        await self.config.twitch_accounts.set(check_accounts)

            await asyncio.sleep(60)

    @commands.group(aliases=["t", "twi"])
    async def twitchhelp(self, ctx):
        """Twitch related commands"""
        if await self.config.client_id() == "":
            await ctx.send("You need to set the twitch token first!")
            return
        pass

    @twitchhelp.command(name="setfollow")
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def set_follow(self, ctx, twitch_name=None, channel: discord.TextChannel = None):
        """
            Setup a channel for automatic follow notifications
        """
        if channel is None:
            channel = ctx.channel
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        cur_accounts = await self.config.twitch_accounts()
        user_data = await self.check_account_added(cur_accounts, profile)
        if user_data is None:
            followers, total = await self.get_all_followers(profile.id)
            user_data = {
                "id": profile.id,
                "login": profile.login,
                "display_name": profile.display_name,
                "followers": followers,
                "total_followers": total,
                "channels": [channel.id],
            }

            cur_accounts.append(user_data)
            await self.config.twitch_accounts.set(cur_accounts)
        else:
            cur_accounts.remove(user_data)
            user_data["channels"].append(channel.id)
            cur_accounts.append(user_data)
            await self.config.twitch_accounts.set(cur_accounts)
        await ctx.send(
            "{} has been setup for twitch follow notifications in {}".format(
                profile.display_name, channel.mention
            )
        )

    @twitchhelp.command(name="remfollow", aliases=["remove", "delete", "del"])
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def remove_follow(self, ctx, twitch_name=None, channel: discord.TextChannel = None):
        """
            Remove an account from follow notifications in the specified channel
            defaults to the current channel
        """
        if channel is None:
            channel = ctx.channel
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx
        cur_accounts = await self.config.twitch_accounts()
        user_data = await self.check_account_added(cur_accounts, profile)
        if user_data is None:
            await ctx.send(
                "{} is not currently posting follow notifications in {}".format(
                    profile.login, channel.mention
                )
            )
            return
        else:
            if channel.id not in user_data["channels"]:
                await ctx.send(
                    "{} is not currently posting follow notifications in {}".format(
                        profile.login, channel.mention
                    )
                )
                return
            else:
                cur_accounts.remove(user_data)
                user_data["channels"].remove(channel.id)
                if len(user_data["channels"]) == 0:
                    # We don't need to be checking if there's no channels to post in
                    await self.config.twitch_accounts.set(cur_accounts)
                else:
                    cur_accounts.append(user_data)
                    await self.config.twitch_accounts.set(cur_accounts)
        await ctx.send(
            "Done, {}'s new followers won't be posted in {} anymore.".format(
                profile.login, channel.mention
            )
        )

    @twitchhelp.command(name="set")
    async def twitch_set(self, ctx, twitch_name):
        """
            Sets the twitch user info for individual users to make commands easier
        """
        profile = await self.get_profile_from_name(twitch_name)
        await self.config.user(ctx.author).id.set(profile.id)
        await self.config.user(ctx.author).login.set(profile.login)
        await self.config.user(ctx.author).display_name.set(profile.display_name)
        await ctx.send("{} set for you.".format(profile.display_name))

    @twitchhelp.command(name="follows", aliases=["followers"])
    async def get_user_follows(self, ctx, twitch_name: str = None):
        """
            Get latest Twitch followers
        """
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        new_url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, profile.id)
        data = await self.get_response(new_url)
        follows = [TwitchFollower.from_json(x) for x in data["data"]]
        total = data["total"]
        await self.twitch_menu(ctx, follows, total)

    @twitchhelp.command(name="user", aliases=["profile"])
    async def get_user(self, ctx, twitch_name=None):
        """
            Shows basic Twitch profile information
        """
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = await self.make_user_embed(profile)
            await ctx.send(embed=em)
        else:
            await ctx.send("https://twitch.tv/{}".format(profile.login))

    async def twitch_menu(
        self,
        ctx: Context,
        post_list: list,
        total_followers=0,
        message: discord.Message = None,
        page=0,
        timeout: int = 30,
    ):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        user_id = post_list[page].from_id
        followed_at = post_list[page].followed_at
        url = "{}/users?id={}".format(BASE_URL, user_id)
        header = {"Client-ID": await self.config.client_id()}
        async with self.session.get(url, headers=header) as resp:
            data = await resp.json()

        profile = TwitchProfile.from_json(data)
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = await self.make_user_embed(profile)
            em.timestamp = datetime.strptime(followed_at, "%Y-%m-%dT%H:%M:%SZ")
        else:
            em = None
        prof_url = "https://twitch.tv/{}".format(profile.login)

        if not message:
            message = await ctx.send(prof_url, embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(content=prof_url, embed=em)
        check = (
            lambda react, user: user == ctx.message.author
            and react.emoji in ["➡", "⬅", "❌"]
            and react.message.id == message.id
        )
        try:
            react, user = await ctx.bot.wait_for("reaction_add", check=check, timeout=timeout)
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
                return await self.twitch_menu(
                    ctx,
                    post_list,
                    total_followers,
                    message=message,
                    page=next_page,
                    timeout=timeout,
                )
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.twitch_menu(
                    ctx,
                    post_list,
                    total_followers,
                    message=message,
                    page=next_page,
                    timeout=timeout,
                )
            else:
                return await message.delete()

    @commands.command(name="twitchcreds")
    @checks.is_owner()
    async def twitch_creds(self, ctx, client_id: str, client_secret: str = None):
        """
            Set twitch client_id and client_secret if required for larger followings

            1. Go to https://glass.twitch.tv/console/apps login and select Register Your Application
            2. Fillout the form with the OAuth redirect URL set to https://localhost
            3. Supply the client_id and client_secret to the bot
            **Note:** client_secret is only necessary if you have more than 3000 followers
            or you expect to be making more than 30 calls per minute to the API
        """
        await self.config.client_id.set(client_id)
        if client_secret is not None:
            await self.config.client_secret.set(client_secret)
        await ctx.send("Twitch token set.")

    def cog_unload(self):
        if getattr(self, "loop", None) is not None:
            self.loop.cancel()
        self.bot.loop.create_task(self.session.close())

    __del__ = cog_unload
    __unload = cog_unload
