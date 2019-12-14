import discord

from redbot.core import commands, checks, Config, modlog
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.i18n import Translator, cog_i18n

from .eventmixin import EventMixin, CommandPrivs

inv_settings = {
    "message_edit": {"enabled": False, "channel": None, "bots": False},
    "message_delete": {
        "enabled": False,
        "channel": None,
        "bots": False,
        "bulk_enabled": False,
        "bulk_individual": False,
        "cached_only": True,
    },
    "user_change": {"enabled": False, "channel": None},
    "role_change": {"enabled": False, "channel": None},
    "voice_change": {"enabled": False, "channel": None},
    "user_join": {"enabled": False, "channel": None},
    "user_left": {"enabled": False, "channel": None},
    "channel_change": {"enabled": False, "channel": None},
    "guild_change": {"enabled": False, "channel": None},
    "emoji_change": {"enabled": False, "channel": None},
    "commands_used": {
        "enabled": False,
        "channel": None,
        "privs": ["MOD", "ADMIN", "BOT_OWNER", "GUILD_OWNER"],
    },
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

    __version__ = "2.2.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895, force_registration=True)
        self.config.register_guild(**inv_settings)
        self.settings = {}
        self.loop = bot.loop.create_task(self.invite_links_loop())

    async def initialize(self):
        all_data = await self.config.all_guilds()
        for guild_id, data in all_data.items():
            guild = discord.Object(id=guild_id)
            for entry in inv_settings.keys():
                setting = data[entry]
                # print(type(setting))
                if type(setting) == bool:
                    new_data = {"enabled": setting, "channel": None}
                    if entry == "commands_used":
                        new_data["privs"] = ["MOD", "ADMIN", "BOT_OWNER", "GUILD_OWNER"]
                    await self.config.guild(guild).set_raw(entry, value=new_data)
        self.settings = all_data

    async def modlog_settings(self, ctx):
        guild = ctx.message.guild
        try:
            _modlog_channel = await modlog.get_modlog_channel(guild)
            modlog_channel = _modlog_channel.mention
        except Exception:
            modlog_channel = "Not Set"
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
        msg = _("Setting for {guild}\n Modlog Channel {channel}\n\n").format(
            guild=guild.name, channel=modlog_channel
        )
        data = await self.config.guild(guild).all()
        ign_chans = data["ignored_channels"]
        ignored_channels = []
        for c in ign_chans:
            chn = guild.get_channel(c)
            if chn is None:
                # a bit of automatic cleanup so things don't break
                data["ignored_channels"].remove(c)
            else:
                ignored_channels.append(chn)
        enabled = ""
        disabled = ""
        for settings, name in cur_settings.items():
            msg += f"{name}: **{data[settings]['enabled']}**"
            if data[settings]["channel"]:
                chn = guild.get_channel(data[settings]["channel"])
                if chn is None:
                    # a bit of automatic cleanup so things don't break
                    data[settings]["channel"] = None
                else:
                    msg += f" {chn.mention}\n"
            else:
                msg += "\n"

        if enabled == "":
            enabled = _("None  ")
        if disabled == "":
            disabled = _("None  ")
        if ignored_channels:
            chans = ", ".join(c.mention for c in ignored_channels)
            msg += _("Ignored Channels") + ": " + chans
        await self.config.guild(ctx.guild).set(data)
        # save the data back to config incase we had some deleted channels
        await ctx.maybe_send_embed(msg)

    @checks.admin_or_permissions(manage_channels=True)
    @commands.group(name="modlog", aliases=["modlogtoggle", "modlogs"])
    @commands.guild_only()
    async def _modlog(self, ctx):
        """
            Toggle various extended modlog notifications

            Requires the channel to be setup with `[p]modlogset modlog #channel` first
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if await self.config.guild(ctx.message.guild).all() == {}:
            await self.config.guild(ctx.message.guild).set(inv_settings)
        if ctx.invoked_subcommand is None:
            await self.modlog_settings(ctx)

    @_modlog.command(name="all", aliaes=["all_settings", "toggle_all"])
    async def _toggle_all_logs(self, ctx, set_to: bool):
        """
            Turn all logging options on or off

            `<set_to>` what to set all logging settings to must be `true`, `false`, `yes`, `no`.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        for setting in inv_settings.keys():
            if "enabled" in self.settings[ctx.guild.id][setting]:
                self.settings[ctx.guild.id][setting]["enabled"] = set_to
        await self.config.guild(ctx.guild).set(self.settings[ctx.guild.id])
        await self.modlog_settings(ctx)

    @_modlog.group(name="edit")
    async def _edit(self, ctx):
        """
            Message edit logging settings
        """
        pass

    @_edit.command(name="toggle")
    async def _edit_toggle(self, ctx):
        """
            Toggle message edit notifications
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Edit messages ")
        if not await self.config.guild(guild).message_edit.enabled():
            await self.config.guild(guild).message_edit.enabled.set(True)
            self.settings[guild.id]["message_edit"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_edit.enabled.set(False)
            self.settings[guild.id]["message_edit"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_edit.command(name="bots")
    async def _edit_toggle_bots(self, ctx):
        """
            Toggle message edit notifications for bot users
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Bots edited messages ")
        if not await self.config.guild(guild).message_edit.bots():
            await self.config.guild(guild).message_edit.bots.set(True)
            self.settings[guild.id]["message_edit"]["bots"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_edit.bots.set(False)
            self.settings[guild.id]["message_edit"]["bots"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_edit.command(name="channel")
    async def _edit_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for edit logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).message_edit.channel.set(channel)
        self.settings[ctx.guild.id]["message_edit"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="join")
    async def _join(self, ctx):
        """
            Member join logging settings
        """
        pass

    @_join.command(name="toggle")
    async def _join_toggle(self, ctx):
        """
            Toggle member join notifications
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Join message logs ")
        if not await self.config.guild(guild).user_join.enabled():
            await self.config.guild(guild).user_join.enabled.set(True)
            self.settings[ctx.guild.id]["user_join"]["enabled"] = True
            links = await self.save_invite_links(guild)
            if links:
                verb = _("enabled with invite links")
            else:
                verb = _("enabled")
        else:
            await self.config.guild(guild).user_join.enabled.set(False)
            self.settings[ctx.guild.id]["user_join"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_join.command(name="channel")
    async def _join_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for join logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).user_join.channel.set(channel)
        self.settings[ctx.guild.id]["user_join"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="guild")
    async def _guild(self, ctx):
        """
            Guild change logging settings
        """
        pass

    @_guild.command(name="toggle")
    async def _guild_toggle(self, ctx):
        """
            Toggle guild change notifications

            Shows changes to name, region, afk timeout, and afk channel
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Guild logs ")
        if not await self.config.guild(guild).guild_change.enabled():
            await self.config.guild(guild).guild_change.enabled.set(True)
            self.settings[ctx.guild.id]["guild_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).guild_change.enabled.set(False)
            self.settings[ctx.guild.id]["guild_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_guild.command(name="channel")
    async def _guild_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for guild logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).guild_change.channel.set(channel)
        self.settings[ctx.guild.id]["guild_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="channel", aliases=["channels"])
    async def _channel(self, ctx):
        """
            Channel change logging settings
        """
        pass

    @_channel.command(name="toggle")
    async def _channel_toggle(self, ctx):
        """
            Toggle channel edit notifications

            Shows changes to name, topic, slowmode, and NSFW
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Channel logs ")
        if not await self.config.guild(guild).channel_change.enabled():
            await self.config.guild(guild).channel_change.enabled.set(True)
            self.settings[ctx.guild.id]["channel_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).channel_change.enabled.set(False)
            self.settings[ctx.guild.id]["channel_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_channel.command(name="channel")
    async def _channel_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for channel logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).channel_change.channel.set(channel)
        self.settings[ctx.guild.id]["channel_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="leave")
    async def _leave(self, ctx):
        """
            Member leave logging settings
        """
        pass

    @_leave.command(name="toggle")
    async def _leave_toggle(self, ctx):
        """
            Toggle member leave notifications
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Leave logs ")
        if not await self.config.guild(guild).user_left.enabled():
            await self.config.guild(guild).user_left.enabled.set(True)
            self.settings[ctx.guild.id]["user_left"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_left.enabled.set(False)
            self.settings[ctx.guild.id]["user_left"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_leave.command(name="channel")
    async def _leave_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for member leave logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).user_left.channel.set(channel)
        self.settings[ctx.guild.id]["user_left"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="delete")
    async def _delete(self, ctx):
        """
            Delete logging settings
        """
        pass

    @_delete.command(name="toggle")
    async def _delete_toggle(self, ctx):
        """
            Toggle message delete notifications
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Message delete logs ")
        if not await self.config.guild(guild).message_delete.enabled():
            await self.config.guild(guild).message_delete.enabled.set(True)
            self.settings[ctx.guild.id]["message_delete"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.enabled.set(False)
            self.settings[ctx.guild.id]["message_delete"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_delete.command(name="bots")
    async def _delete_bots(self, ctx):
        """
            Toggle message delete notifications for bot users

            This will not affect delete notifications for messages that aren't in bot's cache.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Bot delete logs ")
        if not await self.config.guild(guild).message_delete.bots():
            await self.config.guild(guild).message_delete.bots.set(True)
            self.settings[ctx.guild.id]["message_delete"]["bots"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.bots.set(False)
            self.settings[ctx.guild.id]["message_delete"]["bots"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_delete.group(name="bulk")
    async def _delete_bulk(self, ctx):
        """
            Bulk message delete logging settings
        """
        pass

    @_delete_bulk.command(name="toggle")
    async def _delete_bulk_toggle(self, ctx):
        """
            Toggle bulk message delete notifications
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Bulk message delete logs ")
        if not await self.config.guild(guild).message_delete.bulk_enabled():
            await self.config.guild(guild).message_delete.bulk_enabled.set(True)
            self.settings[ctx.guild.id]["message_delete"]["bulk_enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.bulk_enabled.set(False)
            self.settings[ctx.guild.id]["message_delete"]["bulk_enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_delete_bulk.command(name="individual")
    async def _delete_bulk_individual(self, ctx):
        """
            Toggle individual message delete notifications for bulk message delete

            NOTE: In versions under Red 3.1 this setting doesn't work
            and individual message delete notifications will show regardless of it.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Individual message delete logs for bulk message delete ")
        if not await self.config.guild(guild).message_delete.bulk_individual():
            await self.config.guild(guild).message_delete.bulk_individual.set(True)
            self.settings[ctx.guild.id]["message_delete"]["bulk_individual"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.bulk_individual.set(False)
            self.settings[ctx.guild.id]["message_delete"]["bulk_individual"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_delete.command(name="cachedonly")
    async def _delete_cachedonly(self, ctx):
        """
            Toggle message delete notifications for non-cached messages

            Delete notifications for non-cached messages
            will only show channel info without content of deleted message or its author.
            NOTE: This setting only works in Red 3.1+
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Delete logs for non-cached messages ")
        if not await self.config.guild(guild).message_delete.cached_only():
            await self.config.guild(guild).message_delete.cached_only.set(True)
            self.settings[ctx.guild.id]["message_delete"]["cached_only"] = True
            verb = _("disabled")
        else:
            await self.config.guild(guild).message_delete.cached_only.set(False)
            self.settings[ctx.guild.id]["message_delete"]["cached_only"] = False
            verb = _("enabled")
        await ctx.send(msg + verb)

    @_delete.command(name="channel")
    async def _delete_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for delete logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).message_delete.channel.set(channel)
        self.settings[ctx.guild.id]["message_delete"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="member", aliases=["user"])
    async def _user(self, ctx):
        """
            Member logging settings
        """
        pass

    @_user.command(name="toggle")
    async def _user_toggle(self, ctx):
        """
            Toggle member change notifications

            Shows changes to roles and nicknames
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Profile logs ")
        if not await self.config.guild(guild).user_change.enabled():
            await self.config.guild(guild).user_change.enabled.set(True)
            self.settings[ctx.guild.id]["user_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_change.enabled.set(False)
            self.settings[ctx.guild.id]["user_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_user.command(name="channel")
    async def _user_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for user logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).user_change.channel.set(channel)
        self.settings[ctx.guild.id]["user_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="roles", aliases=["role"])
    async def _roles(self, ctx):
        """
            Role logging settings
        """
        pass

    @_roles.command(name="toggle")
    async def _roles_toggle(self, ctx):
        """
            Toggle role change notifications

            Shows new roles, deleted roles, and permission changes
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Role logs ")
        if not await self.config.guild(guild).role_change.enabled():
            await self.config.guild(guild).role_change.enabled.set(True)
            self.settings[ctx.guild.id]["role_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).role_change.enabled.set(False)
            self.settings[ctx.guild.id]["role_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_roles.command(name="channel")
    async def _roles_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for roles logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).role_change.channel.set(channel)
        self.settings[ctx.guild.id]["role_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="voice")
    async def _voice(self, ctx):
        """
            Voice logging settings
        """
        pass

    @_voice.command(name="toggle")
    async def _voice_toggle(self, ctx):
        """
            Toggle voice state notifications

            Shows changes to mute, deafen, self mute, self deafen, afk, and channel
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Voice logs ")
        if not await self.config.guild(guild).voice_change.enabled():
            await self.config.guild(guild).voice_change.enabled.set(True)
            self.settings[ctx.guild.id]["voice_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).voice_change.enabled.set(False)
            self.settings[ctx.guild.id]["voice_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_voice.command(name="channel")
    async def _voice_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for voice logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).voice_change.channel.set(channel)
        self.settings[ctx.guild.id]["voice_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="emoji", aliases=["emojis"])
    async def _emoji(self, ctx):
        """
            Emoji change logging settings
        """
        pass

    @_emoji.command(name="toggle")
    async def _emoji_toggle(self, ctx):
        """
            Toggle emoji change logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Emoji logs ")
        if not await self.config.guild(guild).emoji_change.enabled():
            await self.config.guild(guild).emoji_change.enabled.set(True)
            self.settings[ctx.guild.id]["emoji_change"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).emoji_change.enabled.set(False)
            self.settings[ctx.guild.id]["emoji_change"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_emoji.command(name="channel")
    async def _emoji_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for emoji logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).emoji_change.channel.set(channel)
        self.settings[ctx.guild.id]["emoji_change"]["channel"] = channel
        await ctx.tick()

    @_modlog.group(name="command", aliases=["commands"])
    async def _command(self, ctx):
        """
            Toggle command logging
        """
        pass

    @_command.command(name="level")
    async def _command_level(self, ctx, *level: CommandPrivs):
        """
            Set the level of commands to be logged

            `[level...]` must include all levels you want from:
            MOD, ADMIN, BOT_OWNER, GUILD_OWNER, and NONE

            These are the basic levels commands check for in permissions.
            `NONE` is a command anyone has permission to use, where as `MOD`
            can be `mod or permissions`
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if len(level) == 0:
            return await ctx.send_help()
        guild = ctx.message.guild
        msg = _("Command logs set to: ")
        await self.config.guild(guild).commands_used.privs.set(list(level))
        self.settings[ctx.guild.id]["commands_used"]["privs"] = list(level)
        await ctx.send(msg + humanize_list(level))

    @_command.command(name="toggle")
    async def _command_toggle(self, ctx):
        """
            Toggle command usage logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        msg = _("Command logs ")
        if not await self.config.guild(guild).commands_used.enabled():
            await self.config.guild(guild).commands_used.enabled.set(True)
            self.settings[ctx.guild.id]["commands_used"]["enabled"] = True
            verb = _("enabled")
        else:
            await self.config.guild(guild).commands_used.enabled.set(False)
            self.settings[ctx.guild.id]["commands_used"]["enabled"] = False
            verb = _("disabled")
        await ctx.send(msg + verb)

    @_command.command(name="channel")
    async def _command_channel(self, ctx, channel: discord.TextChannel = None):
        """
            Set custom channel for command logging
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if channel is not None:
            channel = channel.id
        await self.config.guild(ctx.guild).commands_used.channel.set(channel)
        self.settings[ctx.guild.id]["commands_used"]["channel"] = channel
        await ctx.tick()

    @_modlog.command()
    async def ignore(self, ctx, channel: discord.TextChannel = None):
        """
            Ignore a channel from message delete/edit events and bot commands

            `channel` the channel to ignore message delete/edit events
            defaults to current channel
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id not in cur_ignored:
            cur_ignored.append(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            self.settings[guild.id]["ignored_channels"] = cur_ignored
            await ctx.send(_(" Now ignoring messages edited and deleted in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is already being ignored."))

    @_modlog.command()
    async def unignore(self, ctx, channel: discord.TextChannel = None):
        """
            Unignore a channel from message delete/edit events and bot commands

            `channel` the channel to unignore message delete/edit events
            defaults to current channel
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id in cur_ignored:
            cur_ignored.remove(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            self.settings[guild.id]["ignored_channels"] = cur_ignored
            await ctx.send(_(" now tracking edited and deleted messages in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is not being ignored."))

    def __unload(self):
        self.loop.cancel()
