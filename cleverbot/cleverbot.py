import discord
import logging
import re

from typing import Optional, Union

from discord.ext.commands.converter import Converter  # type: ignore[import]
from discord.ext.commands.errors import BadArgument  # type: ignore[import]

from redbot import version_info, VersionInfo
from redbot.core import commands, checks, Config
from redbot.core.i18n import Translator, cog_i18n

from .api import CleverbotAPI

from .errors import (
    NoCredentials,
    InvalidCredentials,
    APIError,
    OutOfRequests,
)

log = logging.getLogger("red.trusty-cogs.Cleverbot")

_ = Translator("ReTrigger", __file__)


@cog_i18n(_)
class Cleverbot(CleverbotAPI, commands.Cog):
    """
    Cleverbot rewritten for V3 from
    https://github.com/Twentysix26/26-Cogs/tree/master/cleverbot

    """

    __author__ = ["Twentysix", "TrustyJAID"]
    __version__ = "2.2.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 127486454786)
        default_global = {
            "api": None,
            "io_user": None,
            "io_key": None,
            "allow_dm": False,
            "tweak1": 0,
            "tweak2": 0,
            "tweak3": 0,
        }
        default_guild = {
            "channel": None,
            "toggle": False,
            "mention": False,
            "tweak1": -1,
            "tweak2": -1,
            "tweak3": -1,
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.instances = {}

    def format_help_for_context(self, ctx: commands.Context):
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

    @commands.command()
    async def cleverbot(self, ctx: commands.Context, *, message: str) -> None:
        """Talk with cleverbot"""
        author = ctx.message.author
        await self.send_cleverbot_response(message, author, ctx)

    @commands.group()
    async def cleverbotset(self, ctx: commands.Context) -> None:
        """
        Settings for cleverbot
        """
        pass

    class IntRange(Converter):

        async def convert(self, ctx, argument) -> int:
            try:
                argument = int(argument)
            except ValueError:
                raise BadArgument("The provided input must be a number.")
            if argument == -1:
                return argument
            if argument < -1:
                raise BadArgument("You must provide a number greater than -1.")
            return max(min(100, argument), 0)

    async def build_tweak_msg(self, guild: Optional[discord.Guild] = None) -> str:
        if guild:
            g_tweak1 = await self.config.guild(guild).tweak1()
            g_tweak2 = await self.config.guild(guild).tweak2()
            g_tweak3 = await self.config.guild(guild).tweak3()
        else:
            g_tweak1, g_tweak2, g_tweak3 = -1, -1, -1
        tweak1 = await self.config.tweak1() if g_tweak1 == -1 else g_tweak1
        tweak2 = await self.config.tweak2() if g_tweak2 == -1 else g_tweak2
        tweak3 = await self.config.tweak3() if g_tweak3 == -1 else g_tweak3
        msg = "Alright, I will be "
        if tweak1 < 50:
            msg += f"{100-tweak1}% sensible, "
        if tweak1 > 50:
            msg += f"{tweak1}% wacky, "
        if tweak1 == 50:
            msg += f"{tweak1}% wacky and sensible, "

        if tweak2 < 50:
            msg += f"{100-tweak2}% shy, and "
        if tweak2 > 50:
            msg += f"{tweak2}% talkative, and "
        if tweak2 == 50:
            msg += f"{tweak2}% shy and talkative, and "

        if tweak3 < 50:
            msg += f"{100-tweak3}% self-centered."
        if tweak3 > 50:
            msg += f"{tweak3}% attentive."
        if tweak3 == 50:
            msg += f"{tweak3}% self-centered and attentive."
        return msg

    @cleverbotset.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def guildtweaks(self, ctx: commands.Context, tweak1: IntRange, tweak2: IntRange, tweak3: IntRange):
        """
        Set the response tweaks from cleverbot

        `<tweak1>` a number from 0-100 varies replies from sensible to wacky
        `<tweak2>` a number from 0-100 varies replies from shy to talkative
        `<tweak3>` a number from 0-100 varies replies from self-centered to attentive

        Setting any tweak to -1 will default to the bots global tweaks.
        """
        await self.config.guild(ctx.guild).tweak1.set(tweak1)
        await self.config.guild(ctx.guild).tweak2.set(tweak2)
        await self.config.guild(ctx.guild).tweak3.set(tweak3)
        msg = await self.build_tweak_msg(ctx.guild)
        await ctx.send(msg + " In this guild.")

    @cleverbotset.command()
    @checks.is_owner()
    async def tweaks(self, ctx: commands.Context, tweak1: IntRange, tweak2: IntRange, tweak3: IntRange):
        """
        Set the response tweaks from cleverbot

        `<tweak1>` a number from 0-100 varies replies from sensible to wacky
        `<tweak2>` a number from 0-100 varies replies from shy to talkative
        `<tweak3>` a number from 0-100 varies replies from self-centered to attentive
        """
        await self.config.tweak1.set(tweak1)
        await self.config.tweak2.set(tweak2)
        await self.config.tweak3.set(tweak3)
        msg = await self.build_tweak_msg()
        await ctx.send(msg + " Globally.")

    @cleverbotset.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def toggle(self, ctx: commands.Context) -> None:
        """Toggles reply when the bot is mentioned"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).toggle():
            await self.config.guild(guild).toggle.set(True)
            await ctx.send(_("I will reply when I am mentioned."))
        else:
            await self.config.guild(guild).toggle.set(False)
            await ctx.send(_("I won't reply when I am mentioned anymore."))

    @cleverbotset.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def mention(self, ctx: commands.Context) -> None:
        """Toggles mention on reply"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).mention():
            await self.config.guild(guild).mention.set(True)
            await ctx.send(_("I will mention on reply."))
        else:
            await self.config.guild(guild).mention.set(False)
            await ctx.send(_("I won't mention on reply."))

    @cleverbotset.command()
    @checks.is_owner()
    async def dm(self, ctx: commands.Context) -> None:
        """Toggles reply in DM"""
        if not await self.config.allow_dm():
            await self.config.allow_dm.set(True)
            await ctx.send(_("I will reply directly to DM's."))
        else:
            await self.config.allow_dm.set(False)
            await ctx.send(_("I won't reply directly to DM's."))

    @cleverbotset.command()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def channel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """
        Toggles channel for automatic replies

        do `[p]cleverbot channel` after a channel is set to disable.
        """
        guild = ctx.message.guild
        cur_auto_channel = await self.config.guild(guild).channel()
        if not cur_auto_channel:
            if channel is None:
                channel = ctx.message.channel
            await self.config.guild(guild).channel.set(channel.id)
            await ctx.send(
                _("I will automaticall reply to all messages in {channel}").format(
                    channel=channel.mention
                )
            )
        else:
            await self.config.guild(guild).channel.set(None)
            await ctx.send(_("Automatic replies turned off."))

    @cleverbotset.command()
    @checks.is_owner()
    async def apikey(self, ctx: commands.Context, key: Optional[str] = None) -> None:
        """
        Sets token to be used with cleverbot.com
        You can get it from https://www.cleverbot.com/api/
        Use this command in direct message to keep your
        token secret
        """
        await self.config.api.set(key)
        await ctx.send(_("Credentials set."))
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()

    @cleverbotset.command()
    @checks.is_owner()
    async def ioapikey(
        self, ctx: commands.Context, io_user: Optional[str] = None, io_key: Optional[str] = None
    ) -> None:
        """
        Sets token to be used with cleverbot.io
        You can get it from https://www.cleverbot.io/
        Use this command in direct message to keep your
        token secret
        """
        await self.config.io_user.set(io_user)
        await self.config.io_key.set(io_key)
        await ctx.send(_("Credentials set."))
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()

    async def send_cleverbot_response(
        self, message: str, author: Union[discord.Member, discord.User], ctx: commands.Context
    ) -> None:
        """
        This is called when we actually want to send a reply
        """
        await ctx.trigger_typing()
        try:
            response = await self.get_response(author, message)
        except NoCredentials:
            msg = _(
                "The owner needs to set the credentials first.\n" "See: [p]cleverbotset apikey"
            )
            await ctx.send(msg)
        except APIError as e:
            await ctx.send("Error contacting the API. Error code: {}".format(e))
        except InvalidCredentials:
            msg = _("The token that has been set is not valid.\n" "See: [p]cleverbotset")
            await ctx.send(msg)
        except OutOfRequests:
            msg = _(
                "You have ran out of requests for this month. "
                "The free tier has a 5000 requests a month limit."
            )
            await ctx.send(msg)
        else:
            if ctx.guild and await self.config.guild(ctx.guild).mention():
                await ctx.send(f"{author.mention} {response}")
            else:
                await ctx.send(response)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        ctx = await self.bot.get_context(message)
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, ctx.guild):
                return
        author = message.author
        text = message.clean_content
        to_strip = f"(?m)^(<@!?{self.bot.user.id}>)"
        is_mention = re.search(to_strip, message.content)
        if is_mention:
            text = text[len(ctx.me.display_name) + 2 :]
            log.debug(text)
        if not text:
            log.debug("No text to send to cleverbot.")
            return
        if guild is None:
            if await self.config.allow_dm() and message.author.id != self.bot.user.id:
                if ctx.prefix:
                    return
                await self.send_cleverbot_response(text, message.author, ctx)
            return

        if message.author.id != self.bot.user.id:

            if not is_mention and message.channel.id != await self.config.guild(guild).channel():
                return
            if not await self.config.guild(guild).toggle():
                return
            await self.send_cleverbot_response(text, author, ctx)
