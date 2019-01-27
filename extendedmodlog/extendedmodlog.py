from redbot.core import commands, checks, Config, modlog
import datetime
import discord
import asyncio
from random import choice, randint
from redbot.core.i18n import Translator, cog_i18n

from .eventmixin import EventMixin

inv_settings = {
    "message_edit": False,
    "message_delete": False,
    "user_change": False,
    "role_change": False,
    "voice_change": False,
    "user_join": False,
    "user_left": False,
    "channel_change": False,
    "guild_change": False,
    "emoji_change": False,
    "commands_used": False,
    "ignored_channels": [],
    "invite_links": {},
}

_ = Translator("ExtendedModLog", __file__)


@cog_i18n(_)
class ExtendedModLog(EventMixin, commands.Cog):
    """
        Extended modlogs
        Works with core modlogset channel
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895)
        self.config.register_guild(**inv_settings, force_registration=True)
        self.loop = bot.loop.create_task(self.invite_links_loop())

    @checks.admin_or_permissions(manage_channels=True)
    @commands.group(aliases=["modlogtoggle"])
    @commands.guild_only()
    async def modlogtoggles(self, ctx):
        """
            Toggle various extended modlog notifications

            Requires the channel to be setup with `[p]modlogset modlog #channel` first
        """
        if await self.config.guild(ctx.message.guild).settings() == {}:
            await self.config.guild(ctx.message.guild).set(inv_settings)
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            try:
                modlog_channel = await modlog.get_modlog_channel(guild)
            except:
                await ctx.send(
                    _("You need to setup a channel with `[p]modlogset modlog #channel` first.")
                )
                return
            cur_settings = {
                "message_edit": _("Message edits"),
                "message_delete": _("Message delete"),
                "user_change": _("Member changes"),
                "role_change": _("Role changes"),
                "voice_change": _("Voice changes"),
                "user_join": _("User join"),
                "user_left": _("Member left"),
                "channel_change": _("Channel changes"),
                "guild_change": _("Guild changes"),
                "emoji_change": _("Emoji changes"),
                "commands_used": _("Mod/Admin Commands"),
            }
            msg = _("Setting for ") + guild.name + "\n"
            e = discord.Embed(title=_("Setting for ") + guild.name)
            e.colour = await ctx.embed_colour()
            e.description = _("ModLogs channel set to ") + modlog_channel.mention
            ignored_channels = await self.config.guild(guild).ignored_channels()
            enabled = ""
            disabled = ""
            for setting, name in cur_settings.items():
                if await self.config.guild(ctx.guild).get_raw(setting):
                    enabled += name + ", "
                else:
                    disabled += name + ", "
            if enabled == "":
                enabled = _("None  ")
            if disabled == "":
                disabled = _("None  ")
            msg += _("Enabled") + ": " + enabled + "\n"
            msg += _("Disabled") + ": " + disabled + "\n"
            e.add_field(name=_("Enabled"), value=enabled[:-2])
            e.add_field(name=_("Disabled"), value=disabled[:-2])
            if ignored_channels:
                chans = ", ".join(guild.get_channel(c).mention for c in ignored_channels)
                msg += _("Ignored Channels") + ": " + chans
                e.add_field(name=_("Ignored Channels"), value=chans)

            e.set_thumbnail(url=guild.icon_url)
            if ctx.channel.permissions_for(ctx.me).embed_links:
                await ctx.send(embed=e)
            else:
                await ctx.send(msg)

    @modlogtoggles.command()
    async def edit(self, ctx):
        """
            Toggle message edit notifications
        """
        guild = ctx.message.guild
        msg = _("Edit messages ")
        if not await self.config.guild(guild).message_edit():
            await self.config.guild(guild).message_edit.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_edit.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def join(self, ctx):
        """
            Toggle member join notifications
        """
        guild = ctx.message.guild
        msg = _("Join message logs ")
        if not await self.config.guild(guild).user_join():
            await self.config.guild(guild).user_join.set(True)
            links = await self.save_invite_links(guild)
            if links:
                verb = _("enabled with invite links")
            else:
                verb = _("enabled")
        else:
            await self.config.guild(guild).user_join.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def guild(self, ctx):
        """
            Toggle guild change notifications

            Shows changes to name, region, afk timeout, and afk channel
        """
        guild = ctx.message.guild
        msg = _("Guild logs ")
        if not await self.config.guild(guild).guild_change():
            await self.config.guild(guild).guild_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).guild_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command(aliases=["channels"])
    async def channel(self, ctx):
        """
            Toggle channel edit notifications

            Shows changes to name, topic, slowmode, and NSFW
        """
        guild = ctx.message.guild
        msg = _("Channel logs ")
        if not await self.config.guild(guild).channel_change():
            await self.config.guild(guild).channel_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).channel_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def leave(self, ctx):
        """
            Toggle member leave notifications
        """
        guild = ctx.message.guild
        msg = _("Leave logs ")
        if not await self.config.guild(guild).user_left():
            await self.config.guild(guild).user_left.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_left.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def delete(self, ctx):
        """
            Toggle message delete notifications
        """
        guild = ctx.message.guild
        msg = _("Message delete logs ")
        if not await self.config.guild(guild).message_delete():
            await self.config.guild(guild).message_delete.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command(aliases=["member"])
    async def user(self, ctx):
        """
            Toggle member change notifications

            Shows changes to roles and nicknames
        """
        guild = ctx.message.guild
        msg = _("Profile logs ")
        if not await self.config.guild(guild).user_change():
            await self.config.guild(guild).user_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command(aliases=["roles"])
    async def role(self, ctx):
        """
            Toggle role change notifications

            Shows new roles, deleted roles, and permission changes
        """
        guild = ctx.message.guild
        msg = _("Role logs ")
        if not await self.config.guild(guild).role_change():
            await self.config.guild(guild).role_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).role_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def voice(self, ctx):
        """
            Toggle voice state notifications

            Shows changes to mute, deafen, self mute, self deafen, afk, and channel
        """
        guild = ctx.message.guild
        msg = _("Voice logs ")
        if not await self.config.guild(guild).voice_change():
            await self.config.guild(guild).voice_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).voice_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command(aliases=["emojis"])
    async def emoji(self, ctx):
        """
            Toggle emoji change notifications
        """
        guild = ctx.message.guild
        msg = _("Emoji logs ")
        if not await self.config.guild(guild).emoji_change():
            await self.config.guild(guild).emoji_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).emoji_change.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command(aliases=["commands"])
    async def command(self, ctx):
        """
            Toggle mod/admin command usage
        """
        guild = ctx.message.guild
        msg = _("Command logs ")
        if not await self.config.guild(guild).commands_used():
            await self.config.guild(guild).commands_used.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).commands_used.set(False)
            verb = _("disabled")
        await ctx.send(msg + verb)

    @modlogtoggles.command()
    async def ignore(self, ctx, channel: discord.TextChannel = None):
        """
            Ignore a channel from message delete/edit events and bot commands

            `channel` the channel to ignore message delete/edit events
            defaults to current channel
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id not in cur_ignored:
            cur_ignored.append(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            await ctx.send(_(" Now ignoring messages edited and deleted in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is already being ignored."))

    @modlogtoggles.command()
    async def unignore(self, ctx, channel: discord.TextChannel = None):
        """
            Unignore a channel from message delete/edit events and bot commands

            `channel` the channel to unignore message delete/edit events
            defaults to current channel
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id in cur_ignored:
            cur_ignored.remove(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            await ctx.send(_(" now tracking edited and deleted messages in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is not being ignored."))

    def __unload(self):
        self.loop.cancel()
