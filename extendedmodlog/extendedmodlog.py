import discord
import logging

from redbot.core import commands, checks, Config, modlog
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.i18n import Translator, cog_i18n
from typing import Union

from .eventmixin import EventMixin, CommandPrivs, EventChooser
from .settings import inv_settings


_ = Translator("ExtendedModLog", __file__)
logger = logging.getLogger("red.trusty-cogs.ExtendedModLog")


@cog_i18n(_)
class ExtendedModLog(EventMixin, commands.Cog):
    """
        Extended modlogs
        Works with core modlogset channel
    """

    __author__ = ["RePulsar", "TrustyJAID"]
    __version__ = "2.8.8"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895, force_registration=True)
        self.config.register_guild(**inv_settings)
        self.config.register_global(version="0.0.0")
        self.settings = {}
        self.loop = bot.loop.create_task(self.invite_links_loop())

    def format_help_for_context(self, ctx: commands.Context):
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def initialize(self) -> None:
        all_data = await self.config.all_guilds()
        for guild_id, data in all_data.items():
            guild = discord.Object(id=guild_id)
            for entry, default in inv_settings.items():
                if entry not in data:
                    all_data[guild_id][entry] = inv_settings[entry]
                if type(default) == dict:

                    for key, _default in inv_settings[entry].items():
                        if not isinstance(all_data[guild_id][entry], dict):
                            all_data[guild_id][entry] = default
                        try:
                            if key not in all_data[guild_id][entry]:
                                all_data[guild_id][entry][key] = _default
                        except TypeError:
                            # del all_data[guild_id][entry]
                            logger.error("Somehow your dict was invalid.")
                            continue
            if await self.config.version() < "2.8.5":
                logger.info("Saving all guild data to new version type")
                await self.config.guild(guild).set(all_data[guild_id])
                await self.config.version.set("2.8.5")

        self.settings = all_data

    async def modlog_settings(self, ctx: commands.Context) -> None:
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
            "role_create": _("Role created"),
            "role_delete": _("Role deleted"),
            "voice_change": _("Voice changes"),
            "user_join": _("User join"),
            "user_left": _("User left"),
            "channel_change": _("Channel changes"),
            "channel_create": _("Channel created"),
            "channel_delete": _("Channel deleted"),
            "guild_change": _("Guild changes"),
            "emoji_change": _("Emoji changes"),
            "commands_used": _("Mod/Admin Commands"),
            "invite_created": _("Invite created"),
            "invite_deleted": _("Invite deleted")
        }
        msg = _("Setting for {guild}\n Modlog Channel {channel}\n\n").format(
            guild=guild.name, channel=modlog_channel
        )
        if guild.id not in self.settings:
            self.settings[guild.id] = inv_settings

        data = self.settings[guild.id]
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
    async def _modlog(self, ctx: commands.Context) -> None:
        """
            Toggle various extended modlog notifications

            Requires the channel to be setup with `[p]modlogset modlog #channel`
            Or can be sent to separate channels with `[p]modlog channel #channel event_name`
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if await self.config.guild(ctx.message.guild).all() == {}:
            await self.config.guild(ctx.message.guild).set(inv_settings)
        if ctx.invoked_subcommand is None:
            await self.modlog_settings(ctx)

    @_modlog.command(name="colour", aliases=["color"])
    async def _set_event_colours(self, ctx: commands.Context, colour: discord.Colour, *events: EventChooser):
        """
            Set custom colours for modlog events

            `colour` must be a hex code or a [built colour.](https://discordpy.readthedocs.io/en/latest/api.html#colour)

            `event` must be one of the following options (more than one event can be provided at once.):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if colour:
            new_colour = colour.value
        else:
            new_colour = colour
        for event in events:
            self.settings[ctx.guild.id][event]["colour"] = new_colour
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} has been set to {colour}").format(
                event=humanize_list(events), colour=str(colour)
            )
        )

    @_modlog.command(name="embeds", aliases=["embed"])
    async def _set_embds(self, ctx: commands.Context, set_to: bool, *events: EventChooser) -> None:
        """
            Set modlog events to use embeds or text

            `set_to` The desired embed setting either on or off.

            `[events...]` must be any of the following options (more than one event can be provided at once):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        for event in events:
            self.settings[ctx.guild.id][event]["embed"] = set_to
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} embed logs have been set to {set_to}").format(
                event=humanize_list(events), set_to=str(set_to)
            )
        )

    @_modlog.command(name="emojiset", send_help=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def _set_event_emoji(
        self, ctx: commands.Context, emoji: Union[discord.Emoji, str], *events: EventChooser,
    ) -> None:
        """
            Set the emoji used in text modlogs.

            `new_emoji` can be any discord emoji or unicode emoji the bot has access to use.

            `[events...]` must be one of the following options (more than one event can be provided at once):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        if isinstance(emoji, str):
            try:
                await ctx.message.add_reaction(emoji)
            except discord.errors.HTTPException:
                return await ctx.send(_("{emoji} is not a valid emoji.").format(emoji=emoji))
        new_emoji = str(emoji)
        for event in events:
            self.settings[ctx.guild.id][event]["emoji"] = new_emoji
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} emoji has been set to {new_emoji}").format(
                event=humanize_list(events), new_emoji=str(new_emoji)
            )
        )

    @_modlog.command(name="toggle")
    async def _set_event_on_or_off(
        self, ctx: commands.Context, set_to: bool, *events: EventChooser,
    ) -> None:
        """
            Turn on and off specific modlog actions

            `set_to` Either on or off.

            `[events...]` must be one of the following options (more than one event can be provided at once):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        for event in events:
            self.settings[ctx.guild.id][event]["enabled"] = set_to
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} logs have been set to {set_to}").format(
                event=humanize_list(events), set_to=str(set_to)
            )
        )

    @_modlog.command(name="channel")
    async def _set_event_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, *events: EventChooser,
    ) -> None:
        """
            Set the channel for modlogs.

            `channel` The text channel to send the events to.

            `[events...]` must be one of the following options (more than one event can be provided at once):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        for event in events:
            self.settings[ctx.guild.id][event]["channel"] = channel.id
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} logs have been set to {channel}").format(
                event=humanize_list(events), channel=channel.mention
            )
        )

    @_modlog.command(name="resetchannel")
    async def _reset_event_channel(
        self, ctx: commands.Context, *events: EventChooser,
    ) -> None:
        """
            Reset the modlog event to the default modlog channel.

            `[events...]` must be one of the following options (more than one event can be provided at once):
                `message_edit`
                `message_delete`
                `user_change`
                `role_change`
                `role_create`
                `role_delete`
                `voice_change`
                `user_join`
                `user_left`
                `channel_change`
                `channel_create`
                `channel_delete`
                `guild_change`
                `emoji_change`
                `commands_used`

                **Requires Red 3.3 and discord.py 1.3**
                `invite_created`
                `invite_deleted`
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        for event in events:
            self.settings[ctx.guild.id][event]["channel"] = None
            await self.config.guild(ctx.guild).set_raw(
                event, value=self.settings[ctx.guild.id][event]
            )
        await ctx.send(
            _("{event} logs channel have been reset.").format(
                event=humanize_list(events)
            )
        )

    @_modlog.command(name="all", aliaes=["all_settings", "toggle_all"])
    async def _toggle_all_logs(self, ctx: commands.Context, set_to: bool) -> None:
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

    @_modlog.command(name="botedits", aliases=["botedit"])
    async def _edit_toggle_bots(self, ctx: commands.Context) -> None:
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

    @_modlog.command(name="botdeletes", aliases=["botdelete"])
    async def _delete_bots(self, ctx: commands.Context) -> None:
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

    @_modlog.group(name="delete")
    async def _delete(self, ctx: commands.Context) -> None:
        """
            Delete logging settings
        """
        pass

    @_delete.command(name="bulkdelete")
    async def _delete_bulk_toggle(self, ctx: commands.Context) -> None:
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

    @_delete.command(name="individual")
    async def _delete_bulk_individual(self, ctx: commands.Context) -> None:
        """
            Toggle individual message delete notifications for bulk message delete
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
    async def _delete_cachedonly(self, ctx: commands.Context) -> None:
        """
            Toggle message delete notifications for non-cached messages

            Delete notifications for non-cached messages
            will only show channel info without content of deleted message or its author.
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

    @_modlog.command(name="botchange")
    async def _user_bot_logging(self, ctx: commands.Context) -> None:
        """
            Toggle bots from being logged in user updates

            This includes roles and nickname.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        setting = self.settings[ctx.guild.id]["user_change"]["bots"]
        self.settings[ctx.guild.id]["user_change"]["bots"] = not setting
        await self.config.guild(ctx.guild).user_change.bots.set(not setting)
        if setting:
            await ctx.send(_("Bots will no longer be tracked in user change logs."))
        else:
            await ctx.send(_("Bots will be tracked in user change logs."))

    @_modlog.command(name="nickname", aliases=["nicknames"])
    async def _user_nickname_logging(self, ctx: commands.Context) -> None:
        """
            Toggle nickname updates for user changes
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = inv_settings
        setting = self.settings[ctx.guild.id]["user_change"]["nicknames"]
        self.settings[ctx.guild.id]["user_change"]["nicknames"] = not setting
        await self.config.guild(ctx.guild).user_change.nicknames.set(not setting)
        if setting:
            await ctx.send(_("Nicknames will no longer be tracked in user change logs."))
        else:
            await ctx.send(_("Nicknames will be tracked in user change logs."))

    @_modlog.command(name="commandlevel", aliases=["commandslevel"])
    async def _command_level(self, ctx: commands.Context, *level: CommandPrivs) -> None:
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

    @_modlog.command()
    async def ignore(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.CategoryChannel, discord.VoiceChannel],
    ) -> None:
        """
            Ignore a channel from message delete/edit events and bot commands

            `channel` the channel or category to ignore events in
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
            await ctx.send(_(" Now ignoring events in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is already being ignored."))

    @_modlog.command()
    async def unignore(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.CategoryChannel, discord.VoiceChannel],
    ) -> None:
        """
            Unignore a channel from message delete/edit events and bot commands

            `channel` the channel to unignore message delete/edit events
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
            await ctx.send(_(" Now tracking events in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is not being ignored."))

    def __unload(self):
        self.loop.cancel()
