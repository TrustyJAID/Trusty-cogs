import asyncio
from typing import Literal, Optional

import discord
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands
from redbot.core.commands.converter import TimedeltaConverter

from .errors import TwitchError
from .menus import BaseMenu, TwitchClipsPages, TwitchFollowersPages
from .twitch_api import TwitchAPI
from .twitch_models import TwitchFollower

log = getLogger("red.Trusty-cogs.Twitch")

BASE_URL = "https://api.twitch.tv/helix"


class Twitch(TwitchAPI, commands.Cog):
    """
    Get twitch user information and post when a user gets new followers
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.4.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1543454673)
        global_defaults = {
            "access_token": {},
            "twitch_accounts": [],
            "twitch_clips": {},
            "version": self.__version__,  # default value so that migrations are skipped on new installs
        }
        user_defaults = {"id": "", "login": "", "display_name": ""}
        self.config.register_global(**global_defaults, force_registration=True)
        self.config.register_user(**user_defaults, force_registration=True)
        self.rate_limit_resets = set()
        self.rate_limit_remaining = 0
        self.loop = None
        self.streams = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        await self.config.user_from_id(user_id).clear()

    async def initialize(self):
        log.debug("Initializing Twitch Cog")
        if await self.config.version() < "1.2.0":
            await self.migrate_api_tokens()
            await self.config.version.set("1.2.0")
        if await self.config.version() < "1.3.3":
            await self.migrate_clips()
        self.loop = asyncio.create_task(self.check_for_new_followers())

    async def migrate_clips(self):
        async with self.config.twitch_clips() as cur_data:
            for t_id, data in cur_data.items():
                if isinstance(data["channels"], list):
                    channels = {}
                    for channel in data["channels"]:
                        channels[str(channel)] = {
                            "view_count": 0,
                            "check_back": None,
                            "clips": data["clips"],
                        }
                    cur_data[t_id]["channels"] = channels
        await self.config.version.set("1.3.3")

    async def migrate_api_tokens(self):
        keys = await self.config.all()
        try:
            central_key = await self.bot.get_shared_api_tokens("twitch")
        except AttributeError:
            # Red 3.1 support
            central_key = await self.bot.db.api_tokens.get_raw("twitch", default={})
        if not central_key:
            try:
                await self.bot.set_shared_api_tokens(
                    "twitch",
                    client_id=keys["client_id"],
                    client_secret=keys["client_secret"],
                )
            except AttributeError:
                await self.bot.db.api_tokens.set_raw(
                    "twitch",
                    value={"client_id": keys["client_id"], "client_secret": keys["client_secret"]},
                )
            except KeyError:
                pass
        await self.config.api_key.clear()

    @commands.group(name="twitch")
    async def twitchhelp(self, ctx: commands.Context) -> None:
        """Twitch related commands"""
        if await self.config.client_id() == "":
            await ctx.send("You need to set the twitch token first!")
            return
        pass

    @twitchhelp.group(name="streams")
    async def twitch_streams(self, ctx: commands.Context) -> None:
        """
        Twitch Stream commands
        """
        pass

    @twitchhelp.group(name="clips")
    async def twitch_clips(self, ctx: commands.Context) -> None:
        """
        Twitch Clips commands
        """
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
        await ctx.typing()
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

    @twitch_clips.command(name="setclips")
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def set_clips(
        self,
        ctx: commands.Context,
        twitch_name: str,
        channel: Optional[discord.TextChannel] = None,
        view_count: Optional[int] = 0,
        *,
        check_back: Optional[TimedeltaConverter] = None,
    ) -> None:
        """
        Setup a channel for automatic clip notifications

        `<twitch_name>` The name of the streamers whose clips you want posted
        `[channel]` The channel to post clips into, if not provided will use the current channel.
        `[view_count]` The minimum view count required before posting a clip.
        `[check_back]` How far back to look back for new clips. Note: You must provide a number
        for `view_count` when providing the check_back. Default is 8 days.
        """
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(f"I don't have embed links permission in {channel.mention}")
        await ctx.typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        async with self.config.twitch_clips() as cur_accounts:
            chan_data = {
                "view_count": view_count,
                "check_back": check_back.total_seconds() if check_back else None,
                "clips": [],
            }
            if str(profile.id) not in cur_accounts:
                try:
                    clips = await self.get_new_clips(profile.id)
                except TwitchError as e:
                    return await ctx.send(e)

                user_data = {
                    "id": profile.id,
                    "login": profile.login,
                    "display_name": profile.display_name,
                    "channels": {str(channel.id): chan_data},
                }

                cur_accounts[str(profile.id)] = user_data
            else:
                cur_accounts[str(profile.id)]["channels"][str(channel.id)] = chan_data
        await ctx.send(
            "{} has been setup for new clip notifications in {}".format(
                profile.display_name, channel.mention
            )
        )

    @twitch_clips.command(name="remclips", aliases=["removeclips", "deleteclips", "delclips"])
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def remove_clips(
        self, ctx: commands.Context, twitch_name: str, channel: discord.TextChannel = None
    ) -> None:
        """
        Remove an account from new clip notifications in the specified channel
        defaults to the current channel
        """
        if channel is None:
            channel = ctx.channel
        await ctx.typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            return await ctx.send(e)
        async with self.config.twitch_clips() as cur_accounts:
            if str(profile.id) not in cur_accounts:
                await ctx.send(
                    "{} is not currently posting clip notifications in {}".format(
                        profile.login, channel.mention
                    )
                )
                return
            else:
                if str(channel.id) not in cur_accounts[str(profile.id)]["channels"]:
                    await ctx.send(
                        "{} is not currently posting new clips in {}".format(
                            profile.login, channel.mention
                        )
                    )
                    return
                else:
                    del cur_accounts[str(profile.id)]["channels"][str(channel.id)]
                    if len(cur_accounts[str(profile.id)]["channels"]) == 0:
                        # We don't need to be checking if there's no channels to post in
                        del cur_accounts[str(profile.id)]
            await ctx.send(
                "Done, {}'s new clips won't be posted in {} anymore.".format(
                    profile.login, channel.mention
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
        await ctx.typing()
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
            text_msg = f"{profile.display_name} has just " f"followed {account.display_name}!"
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
        await ctx.typing()
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
        await ctx.typing()
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
        await ctx.typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        new_url = "{}/users/follows?to_id={}&first=100".format(BASE_URL, profile.id)
        data = await self.get_response(new_url)
        follows = [TwitchFollower(**x) for x in data["data"]]
        total = data["total"]
        await BaseMenu(
            source=TwitchFollowersPages(followers=follows, total_follows=total),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
        ).start(ctx=ctx)

    @twitch_clips.command(name="view")
    async def get_user_clips(
        self, ctx: commands.Context, twitch_name: Optional[str] = None
    ) -> None:
        """
        Get latest twitch clips from a user
        """
        await ctx.typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        clips = await self.get_new_clips(profile.id)
        if not clips:
            return await ctx.send(
                f"{profile.display_name} does not have any public clips available."
            )
        urls = [c["url"] for c in clips]
        await BaseMenu(
            source=TwitchClipsPages(clips=urls),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
        ).start(ctx=ctx)

    @twitchhelp.command(name="user", aliases=["profile"])
    async def get_user(self, ctx: commands.Context, twitch_name: Optional[str] = None) -> None:
        """
        Shows basic Twitch profile information
        """
        await ctx.typing()
        try:
            profile = await self.maybe_get_twitch_profile(ctx, twitch_name)
        except TwitchError as e:
            await ctx.send(e)
            return
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = profile.make_user_embed()
            await ctx.send(embed=em)
        else:
            await ctx.send("https://twitch.tv/{}".format(profile.login))

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

    async def cog_unload(self):
        if getattr(self, "loop", None):
            self.loop.cancel()
