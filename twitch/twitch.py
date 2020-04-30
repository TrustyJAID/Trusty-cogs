import discord
import asyncio
import aiohttp
import logging

from datetime import datetime
from typing import Optional

from redbot.core import Config, checks, commands
from redbot.core.commands import Context

from .twitch_api import TwitchAPI
from .twitch_profile import TwitchProfile
from .twitch_follower import TwitchFollower
from .errors import TwitchError


log = logging.getLogger("red.Trusty-cogs.Twitch")

BASE_URL = "https://api.twitch.tv/helix"


class Twitch(TwitchAPI, commands.Cog):
    """
        Get twitch user information and post when a user gets new followers
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.2.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1543454673)
        global_defaults = {
            "access_token": {},
            "twitch_accounts": [],
        }
        user_defaults = {"id": "", "login": "", "display_name": ""}
        self.config.register_global(**global_defaults, force_registration=True)
        self.config.register_user(**user_defaults, force_registration=True)
        self.rate_limit_resets = set()
        self.rate_limit_remaining = 0
        self.loop = bot.loop.create_task(self.check_for_new_followers())

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def initialize(self):
        keys = await self.config.all()
        if "client_id" not in keys:
            return
        try:
            central_key = await self.bot.get_shared_api_tokens("twitch")
        except AttributeError:
            # Red 3.1 support
            central_key = await self.bot.db.api_tokens.get_raw("twitch", default={})
        if not central_key:
            try:
                await self.bot.set_shared_api_tokens(
                    "twitch", client_id=keys["client_id"], client_secret=keys["client_secret"],
                )
            except AttributeError:
                await self.bot.db.api_tokens.set_raw(
                    "twitch",
                    value={"client_id": keys["client_id"], "client_secret": keys["client_secret"]},
                )
        await self.config.api_key.clear()

    @commands.group(name="twitch")
    async def twitchhelp(self, ctx: commands.Context) -> None:
        """Twitch related commands"""
        if await self.config.client_id() == "":
            await ctx.send("You need to set the twitch token first!")
            return
        pass

    @twitchhelp.command(name="setfollow")
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def set_follow(
        self,
        ctx: commands.Context,
        twitch_name: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
            Setup a channel for automatic follow notifications
        """
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(f"I don't have embed links permission in {channel.mention}")
        await ctx.trigger_typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        async with self.config.twitch_accounts() as cur_accounts:
            user_data = await self.check_account_added(cur_accounts, profile)
            if user_data is None:
                try:
                    followers, total = await self.get_all_followers(profile.id)
                except TwitchError as e:
                    return await ctx.send(e)
                user_data = {
                    "id": profile.id,
                    "login": profile.login,
                    "display_name": profile.display_name,
                    "followers": followers,
                    "total_followers": total,
                    "channels": [channel.id],
                }

                cur_accounts.append(user_data)
            else:
                cur_accounts.remove(user_data)
                user_data["channels"].append(channel.id)
                cur_accounts.append(user_data)
            await ctx.send(
                "{} has been setup for twitch follow notifications in {}".format(
                    profile.display_name, channel.mention
                )
            )

    @twitchhelp.command(name="testfollow")
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def followtest(
        self,
        ctx: commands.Context,
        twitch_name: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
            Test channel for automatic follow notifications
        """
        if channel is None:
            channel = ctx.channel
        await ctx.trigger_typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        try:
            followers, total = await self.get_all_followers(profile.id)
        except TwitchError as e:
            return await ctx.send(e)
        try:
            follower = await self.get_profile_from_id(int(followers[0]))
        except Exception:
            return
        em = await self.make_follow_embed(profile, follower, total)
        if channel.permissions_for(channel.guild.me).embed_links:
            await channel.send(embed=em)
        else:
            text_msg = (
                f"{profile.display_name} has just "
                f"followed {account.display_name}!"
            )
            await channel.send(text_msg)

    @twitchhelp.command(name="remfollow", aliases=["remove", "delete", "del"])
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def remove_follow(
        self, ctx: commands.Context, twitch_name: str, channel: discord.TextChannel = None
    ) -> None:
        """
            Remove an account from follow notifications in the specified channel
            defaults to the current channel
        """
        if channel is None:
            channel = ctx.channel
        await ctx.trigger_typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            return await ctx.send(e)
        async with self.config.twitch_accounts() as cur_accounts:
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
                    user_data["channels"].remove(channel.id)
                    if len(user_data["channels"]) == 0:
                        # We don't need to be checking if there's no channels to post in
                        cur_accounts.remove(user_data)
            await ctx.send(
                "Done, {}'s new followers won't be posted in {} anymore.".format(
                    profile.login, channel.mention
                )
            )

    @twitchhelp.command(name="set")
    async def twitch_set(self, ctx: commands.Context, twitch_name: str) -> None:
        """
            Sets the twitch user info for individual users to make commands easier
        """
        await ctx.trigger_typing()
        try:
            profile = await self.get_profile_from_name(twitch_name)
        except TwitchError as e:
            return await ctx.send(e)
        await self.config.user(ctx.author).id.set(profile.id)
        await self.config.user(ctx.author).login.set(profile.login)
        await self.config.user(ctx.author).display_name.set(profile.display_name)
        await ctx.send("{} set for you.".format(profile.display_name))

    @twitchhelp.command(name="follows", aliases=["followers"])
    async def get_user_follows(
        self, ctx: commands.Context, twitch_name: Optional[str] = None
    ) -> None:
        """
            Get latest Twitch followers
        """
        await ctx.trigger_typing()
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
    async def get_user(self, ctx: commands.Context, twitch_name: Optional[str] = None) -> None:
        """
            Shows basic Twitch profile information
        """
        await ctx.trigger_typing()
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
        message: Optional[discord.Message] = None,
        page=0,
        timeout: int = 30,
    ):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        user_id = post_list[page].from_id
        followed_at = post_list[page].followed_at
        url = "{}/users?id={}".format(BASE_URL, user_id)
        keys = await self._get_api_tokens()
        header = {"Client-ID": keys["client_id"]}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=header) as resp:
                data = await resp.json()

        profile = TwitchProfile.from_json(data)
        em = None
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = await self.make_user_embed(profile)
            em.timestamp = datetime.strptime(followed_at, "%Y-%m-%dT%H:%M:%SZ")

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

    @twitchhelp.command(name="creds")
    @checks.is_owner()
    async def twitch_creds(self, ctx: commands.Context) -> None:
        """
            Set twitch client_id and client_secret if required for larger followings
        """
        msg = (
            "1. Go to https://glass.twitch.tv/console/apps login and select"
            "Register Your Application\n"
            "2. Fillout the form with the OAuth redirect URL set to https://localhost\n"
            "3. `{prefix}set api twitch client_id,YOUR_CLIENT_ID_HERE client_secret,YOUR_CLIENT_SECRET_HERE`\n\n"
            "**Note:** client_secret is only necessary if you have more than 3000 followers"
            "or you expect to be making more than 30 calls per minute to the API"
        ).format(prefix=ctx.clean_prefix)
        await ctx.maybe_send_embed(msg)

    def cog_unload(self):
        if getattr(self, "loop", None) is not None:
            self.loop.cancel()

    __del__ = cog_unload
    __unload = cog_unload
