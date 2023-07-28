from typing import Optional

import discord
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .api import ChannelUserRole, CleverbotAPI, IntRange

log = getLogger("red.trusty-cogs.Cleverbot")

_ = Translator("cleverbot", __file__)


@cog_i18n(_)
class Cleverbot(CleverbotAPI, commands.Cog):
    """
    Cleverbot rewritten for V3 from
    https://github.com/Twentysix26/26-Cogs/tree/master/cleverbot

    """

    __author__ = ["Twentysix", "TrustyJAID"]
    __version__ = "2.4.5"

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
            "reply": True,
            "whitelist": [],
            "blacklist": [],
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

    @cleverbotset.group(name="blocklist", aliases=["blacklist"])
    @commands.guild_only()
    async def blacklist(self, ctx: commands.Context):
        """
        Blacklist settings for cleverbot
        """
        pass

    @cleverbotset.group(name="allowlist", aliases=["whitelist"])
    @commands.guild_only()
    async def whitelist(self, ctx: commands.Context):
        """
        Whitelist settings for cleverbot
        """
        pass

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Add a channel, user, or role to cleverbots whitelist

        `[channel_user_role...]` is the channel, user or role to whitelist
        (You can supply more than one of any at a time)

        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be whitelisted.")
            )
        async with self.config.guild(ctx.guild).whitelist() as whitelist:
            for obj in channel_user_role:
                if obj.id not in whitelist:
                    whitelist.append(obj.id)
        msg = _("`{list_type}` added to the whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Remove a channel, user, or role from cleverbots whitelist

        `[channel_user_role...]` is the channel, user or role to remove from the whitelist
        (You can supply more than one of any at a time)
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels users or roles to be removed from the whitelist."
                )
            )
        async with self.config.guild(ctx.guild).whitelist() as whitelist:
            for obj in channel_user_role:
                if obj.id in whitelist:
                    whitelist.remove(obj.id)
        msg = _("`{list_type}` removed from the whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="info")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_info(self, ctx: commands.Context):
        """
        Show what's currently in cleverbots whitelist
        """
        msg = _("Cleverbot allowlist for {guild}:\n").format(guild=ctx.guild.name)
        whitelist = await self.config.guild(ctx.guild).whitelist()
        can_embed = ctx.channel.permissions_for(ctx.me).embed_links
        for obj_id in whitelist:
            obj = await ChannelUserRole().convert(ctx, str(obj_id))
            if isinstance(obj, discord.TextChannel):
                msg += f"{obj.mention}\n"
                continue
            if can_embed:
                msg += f"{obj.mention}\n"
                continue
            else:
                msg += f"{obj.name}\n"
        for page in pagify(msg):
            await ctx.maybe_send_embed(page)

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Add a channel, user, or role to cleverbots blacklist

        `[channel_user_role...]` is the channel, user or role to blacklist
        (You can supply more than one of any at a time)
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be blacklisted.")
            )
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            for obj in channel_user_role:
                if obj.id not in blacklist:
                    blacklist.append(obj.id)
        msg = _("`{list_type}` added to the blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Remove a channel, user, or role from cleverbots blacklist

        `[channel_user_role...]` is the channel, user or role to remove from the blacklist
        (You can supply more than one of any at a time)

        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels users or roles to remove from the blacklist."
                )
            )
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            for obj in channel_user_role:
                if obj.id in blacklist:
                    blacklist.remove(obj.id)
        msg = _("`{list_type}` removed from the blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="info")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_info(self, ctx: commands.Context):
        """
        Show what's currently in cleverbots blacklist
        """
        msg = _("Cleverbot blocklist for {guild}:\n").format(guild=ctx.guild.name)
        blacklist = await self.config.guild(ctx.guild).blacklist()
        can_embed = ctx.channel.permissions_for(ctx.me).embed_links
        for obj_id in blacklist:
            obj = await ChannelUserRole().convert(ctx, str(obj_id))
            if isinstance(obj, discord.TextChannel):
                msg += f"{obj.mention}\n"
                continue
            if can_embed:
                msg += f"{obj.mention}\n"
                continue
            else:
                msg += f"{obj.name}\n"
        for page in pagify(msg):
            await ctx.maybe_send_embed(page)

    @cleverbotset.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def guildtweaks(
        self, ctx: commands.Context, tweak1: IntRange, tweak2: IntRange, tweak3: IntRange
    ):
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
        await ctx.send(msg + "in this guild.")

    @cleverbotset.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def tweakinfo(self, ctx: commands.Context):
        """
        Show the current cleverbot tweaks in this server
        """
        msg = await self.build_tweak_msg(ctx.guild)
        return await ctx.send(msg + "in this guild.")

    @cleverbotset.command()
    @checks.is_owner()
    async def tweaks(
        self, ctx: commands.Context, tweak1: IntRange, tweak2: IntRange, tweak3: IntRange
    ):
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
        await ctx.send(msg + "globally.")

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
            await self.config.guild(guild).toggle.clear()
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
            await self.config.guild(guild).mention.clear()
            await ctx.send(_("I won't mention on reply."))

    @cleverbotset.command(aliases=["replies"])
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def reply(self, ctx: commands.Context) -> None:
        """Toggles reply messages

        Note: This is only available for Red 3.4.6 and discord.py 1.6.0
        """
        guild = ctx.message.guild
        if not await self.config.guild(guild).reply():
            await self.config.guild(guild).reply.clear()
            await ctx.send(_("I will use replies in cleverbot responses."))
        else:
            await self.config.guild(guild).reply.set(False)
            await ctx.send(_("I won't use replies on cleverbot responses anymore."))

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
            await self.config.guild(guild).channel.clear()
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
