from typing import Union

import discord
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands, modlog
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .eventmixin import CommandPrivs, EventChooser, EventMixin, MemberUpdateEnum
from .settings import inv_settings

_ = Translator("ExtendedModLog", __file__)
logger = getLogger("red.trusty-cogs.ExtendedModLog")


def wrapped_additional_help():
    """
    This wrapper lets me add a common string to multiple commands via a decorator.

    Note: This must be the last decorator on the function for it to work.
    """
    added_doc = _(
        """
    - `[events...]` must be any of the following options (more than one event can be provided at once):
     - `channel_change` - Updates to channel name, etc.
     - `channel_create`
     - `channel_delete`
     - `commands_used`  - Bot command usage
     - `emoji_change`   - Emojis added or deleted
     - `guild_change`   - Server settings changed
     - `message_edit`
     - `message_delete`
     - `member_change`  - Member changes like roles added/removed, nicknames, etc.
     - `role_change`    - Role updates permissions, name, etc.
     - `role_create`
     - `role_delete`
     - `voice_change`   - Voice channel join/leave
     - `member_join`
     - `member_left`
     - `invite_created`
     - `invite_deleted`
     - `thread_create`
     - `thread_delete`
     - `thread_change`
     - `stickers_change`
    """
    )

    def decorator(func):
        old = func.__doc__ or ""
        setattr(func, "__doc__", old + added_doc)
        return func

    return decorator


@cog_i18n(_)
class ExtendedModLog(EventMixin, commands.Cog):
    """
    Extended modlogs
    Works with core modlogset channel
    """

    __author__ = ["RePulsar", "TrustyJAID"]
    __version__ = "2.12.3"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895, force_registration=True)
        self.config.register_guild(**inv_settings)
        self.config.register_global(version="0.0.0")
        self.settings = {}
        self._ban_cache = {}
        self.invite_links_loop.start()
        self.allowed_mentions = discord.AllowedMentions(users=False, roles=False, everyone=False)

    def format_help_for_context(self, ctx: commands.Context):
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self):
        self.invite_links_loop.stop()

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def cog_load(self) -> None:
        if await self.config.version() < "2.8.5":
            await self.migrate_2_8_5_settings()
        for guild_id in await self.config.all_guilds():
            self.settings[int(guild_id)] = await self.config.guild_from_id(guild_id).all()

    async def migrate_2_8_5_settings(self):
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
            logger.info("Saving guild %s data to new version type", guild_id)
            await self.config.guild(guild).set(all_data[guild_id])
        await self.config.version.set("2.8.5")

    async def modlog_settings(self, ctx: commands.Context) -> None:
        guild = ctx.message.guild
        try:
            _modlog_channel = await modlog.get_modlog_channel(guild)
            modlog_channel = _modlog_channel.mention
        except Exception:
            modlog_channel = _("Not Set")
        cur_settings = {
            "message_edit": _("Message edits"),
            "message_delete": _("Message delete"),
            "user_change": _("Member changes"),
            "role_change": _("Role changes"),
            "role_create": _("Role created"),
            "role_delete": _("Role deleted"),
            "voice_change": _("Voice changes"),
            "user_join": _("Member join"),
            "user_left": _("Member left"),
            "channel_change": _("Channel changes"),
            "channel_create": _("Channel created"),
            "channel_delete": _("Channel deleted"),
            "guild_change": _("Guild changes"),
            "emoji_change": _("Emoji changes"),
            "stickers_change": _("Stickers changes"),
            "commands_used": _("Commands"),
            "invite_created": _("Invite created"),
            "invite_deleted": _("Invite deleted"),
            "thread_create": _("Thread created"),
            "thread_delete": _("Thread deleted"),
            "thread_change": _("Thread changed"),
        }
        msg = _("Setting for {guild}\n Modlog Channel {channel}\n\n").format(
            guild=guild.name, channel=modlog_channel
        )
        if guild.id not in self.settings:
            self.settings[guild.id] = await self.config.guild(guild).all()

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
            if settings == "commands_used":
                msg += "\n" + humanize_list(data[settings]["privs"])
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
        pass

    async def save(self, guild: discord.Guild):
        async with self.config.guild(guild).all() as all_settings:
            for key, value in self.settings[guild.id].items():
                all_settings[key] = value

    @_modlog.command(name="settings")
    async def _show_modlog_settings(self, ctx: commands.Context):
        """
        Show the servers current ExtendedModlog settings
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        await self.modlog_settings(ctx)

    @_modlog.command(name="colour", aliases=["color"])
    @wrapped_additional_help()
    async def _set_event_colours(
        self, ctx: commands.Context, colour: discord.Colour, *events: EventChooser
    ):
        """
        Set custom colours for modlog events

        - `<colour>` must be a hex code or a [built colour.](https://discordpy.readthedocs.io/en/latest/api.html#colour)
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        if colour:
            new_colour = colour.value
        else:
            new_colour = colour
        for event in events:
            self.settings[ctx.guild.id][event]["colour"] = new_colour
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} has been set to {colour}").format(
                event=humanize_list([e.replace("user_", "member_") for e in events]),
                colour=str(colour),
            )
        )

    @_modlog.command(name="embeds", aliases=["embed"])
    @wrapped_additional_help()
    async def _set_embds(
        self, ctx: commands.Context, true_or_false: bool, *events: EventChooser
    ) -> None:
        """
        Set modlog events to use embeds or text

        - `<true_or_false>` The desired embed setting either on or off.
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        for event in events:
            self.settings[ctx.guild.id][event]["embed"] = true_or_false
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} embed logs have been set to {true_or_false}").format(
                event=humanize_list([e.replace("user_", "member_") for e in events]),
                true_or_false=str(true_or_false),
            )
        )

    @_modlog.command(name="emojiset", send_help=True)
    @commands.bot_has_permissions(add_reactions=True)
    @wrapped_additional_help()
    async def _set_event_emoji(
        self,
        ctx: commands.Context,
        emoji: Union[discord.Emoji, str],
        *events: EventChooser,
    ) -> None:
        """
        Set the emoji used in text modlogs.

        - `<new_emoji>` can be any discord emoji or unicode emoji the bot has access to use.
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        if isinstance(emoji, str):
            try:
                await ctx.message.add_reaction(emoji)
            except discord.errors.HTTPException:
                return await ctx.send(_("{emoji} is not a valid emoji.").format(emoji=emoji))
        new_emoji = str(emoji)
        for event in events:
            self.settings[ctx.guild.id][event]["emoji"] = new_emoji
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} emoji has been set to {new_emoji}").format(
                event=humanize_list([e.replace("user_", "member_") for e in events]),
                new_emoji=str(new_emoji),
            )
        )

    @_modlog.command(name="toggle")
    @wrapped_additional_help()
    async def _set_event_on_or_off(
        self,
        ctx: commands.Context,
        true_or_false: bool,
        *events: EventChooser,
    ) -> None:
        """
        Turn on and off specific modlog actions

        - `<true_or_false>` Either on or off.
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        for event in events:
            self.settings[ctx.guild.id][event]["enabled"] = true_or_false
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} logs have been set to {true_or_false}").format(
                event=humanize_list([e.replace("user_", "member_") for e in events]),
                true_or_false=str(true_or_false),
            )
        )

    @_modlog.command(name="channel")
    @wrapped_additional_help()
    async def _set_event_channel(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        *events: EventChooser,
    ) -> None:
        """
        Set the channel for modlogs.

        - `<channel>` The text channel to send the events to.
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        for event in events:
            self.settings[ctx.guild.id][event]["channel"] = channel.id
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} logs have been set to {channel}").format(
                event=humanize_list([e.replace("user_", "member_") for e in events]),
                channel=channel.mention,
            )
        )

    @_modlog.command(name="resetchannel")
    @wrapped_additional_help()
    async def _reset_event_channel(
        self,
        ctx: commands.Context,
        *events: EventChooser,
    ) -> None:
        """
        Reset the modlog event to the default modlog channel.
        """
        if len(events) == 0:
            return await ctx.send(_("You must provide which events should be included."))
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        for event in events:
            self.settings[ctx.guild.id][event]["channel"] = None
        await self.save(ctx.guild)
        await ctx.send(
            _("{event} logs channel have been reset.").format(event=humanize_list(events))
        )

    @_modlog.command(name="all", aliaes=["all_settings", "toggle_all"])
    async def _toggle_all_logs(self, ctx: commands.Context, true_or_false: bool) -> None:
        """
        Turn all logging options on or off.

        - `<true_or_false>` True of False, what to set all loggable settings to.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        for setting in self.settings[ctx.guild.id].keys():
            if "enabled" in self.settings[ctx.guild.id][setting]:
                self.settings[ctx.guild.id][setting]["enabled"] = true_or_false
        await self.save(ctx.guild)
        await self.modlog_settings(ctx)

    @_modlog.group(name="delete")
    async def _delete(self, ctx: commands.Context) -> None:
        """
        Delete logging settings.
        """
        pass

    @_delete.command(name="bulkdelete")
    async def _delete_bulk_toggle(self, ctx: commands.Context) -> None:
        """
        Toggle bulk message delete notifications.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Bulk message delete logs {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_delete.bulk_enabled():
            self.settings[ctx.guild.id]["message_delete"]["bulk_enabled"] = True
            verb = _("enabled")
        else:
            self.settings[ctx.guild.id]["message_delete"]["bulk_enabled"] = False
            verb = _("disabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_delete.command(name="individual")
    async def _delete_bulk_individual(self, ctx: commands.Context) -> None:
        """
        Toggle individual message delete notifications for bulk message delete.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Individual message delete logs for bulk message delete {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_delete.bulk_individual():
            self.settings[ctx.guild.id]["message_delete"]["bulk_individual"] = True
            verb = _("enabled")
        else:
            self.settings[ctx.guild.id]["message_delete"]["bulk_individual"] = False
            verb = _("disabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_delete.command(name="cachedonly")
    async def _delete_cachedonly(self, ctx: commands.Context) -> None:
        """
        Toggle message delete notifications for non-cached messages.

        Delete notifications for non-cached messages
        will only show channel info without content of deleted message or its author.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Delete logs for non-cached messages {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_delete.cached_only():
            self.settings[ctx.guild.id]["message_delete"]["cached_only"] = True
            verb = _("disabled")
        else:
            self.settings[ctx.guild.id]["message_delete"]["cached_only"] = False
            verb = _("enabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_delete.command(name="ignorecommands")
    async def _delete_ignore_commands(self, ctx: commands.Context) -> None:
        """
        Toggle message delete notifications for valid bot command messages.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Ignore deleted command messages {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_delete.cached_only():
            self.settings[ctx.guild.id]["message_delete"]["ignore_commands"] = False
            verb = _("disabled")
        else:
            self.settings[ctx.guild.id]["message_delete"]["ignore_commands"] = True
            verb = _("enabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_modlog.group(name="member", aliases=["members", "memberchanges"])
    async def _members(self, ctx: commands.Context) -> None:
        """
        Toggle individual member update settings.
        """

    @_members.command(name="settings")
    async def _members_show_settings(self, ctx: commands.Context) -> None:
        """
        Show the current settings on member updates.
        """
        await self._members_settings(ctx)

    async def _members_settings(self, ctx: commands.Context, msg: str = ""):
        guild = ctx.guild
        msg += _("\n### Member logging Settings for {guild}\n").format(guild=guild.name)
        if guild.id not in self.settings:
            self.settings[guild.id] = inv_settings

        data = self.settings[guild.id]["user_change"]
        for update_type in MemberUpdateEnum:
            msg += f"{update_type.get_name()}: **{data[update_type.name]}**\n"
        await self.save(ctx.guild)
        # save the data back to config incase we had some deleted channels
        await ctx.maybe_send_embed(msg)

    @_members.command(name="nickname", aliases=["nicknames"])
    async def _user_nickname_logging(self, ctx: commands.Context) -> None:
        """
        Toggle nickname updates for member changes.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["nicknames"]
        self.settings[ctx.guild.id]["user_change"]["nicknames"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Nicknames will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(
                ctx, _("Nicknames will be tracked in member change logs.")
            )

    @_members.command(name="avatar")
    async def _user_avatar_logging(self, ctx: commands.Context) -> None:
        """
        Toggle avatar updates for member changes.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["avatar"]
        self.settings[ctx.guild.id]["user_change"]["avatar"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Avatars will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(ctx, _("Avatars will be tracked in member change logs."))

    @_members.command(name="roles", aliases=["role"])
    async def _user_role_logging(self, ctx: commands.Context) -> None:
        """
        Toggle role updates for members.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["roles"]
        self.settings[ctx.guild.id]["user_change"]["roles"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Roles will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(ctx, _("Roles will be tracked in member change logs."))

    @_members.command(name="pending")
    async def _user_pending_logging(self, ctx: commands.Context) -> None:
        """
        Toggle pending updates for members.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["pending"]
        self.settings[ctx.guild.id]["user_change"]["pending"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Pending will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(ctx, _("Pending will be tracked in member change logs."))

    @_members.command(name="timeout")
    async def _user_timeout_logging(self, ctx: commands.Context) -> None:
        """
        Toggle timeout updates for members.

        Note: Due to a discord limitation this will not update when a members
        timeout has expired and may display a before timeout in the past.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["timeout"]
        self.settings[ctx.guild.id]["user_change"]["timeout"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Timeout will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(ctx, _("Timeout will be tracked in member change logs."))

    @_members.command(name="flags")
    async def _user_flags_logging(self, ctx: commands.Context) -> None:
        """
        Toggle flags updates for members.

        This includes things like:
        - `did_rejoin`
        - `completed_onboarding`
        - `bypasses_verification`
        - `started_onboarding`
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["flags"]
        self.settings[ctx.guild.id]["user_change"]["flags"] = not setting
        await self.save(ctx.guild)
        if setting:
            await self._members_settings(
                ctx, _("Member flags will no longer be tracked in member change logs.")
            )
        else:
            await self._members_settings(
                ctx, _("Member flags will be tracked in member change logs.")
            )

    # For whatever reason trying to toggle all these settings causes all of the guilds
    # config to reset and I have no clue why so this will be unsupported for now
    @_members.command(name="all")
    async def _user_all_logging(self, ctx: commands.Context, set_to: bool) -> None:
        """
        Set all member update settings.

        - `<set_to>` True or False what to set all the member update settings to.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            logger.debug("Adding %s to cache", ctx.guild.id)
        # async with self.config.guild(ctx.guild).user_change() as user_change:
        for update_type in MemberUpdateEnum:
            self.settings[ctx.guild.id]["user_change"][update_type.name] = set_to
        await self.save(ctx.guild)
        # user_change[update_type.name] = set_to
        await self._members_settings(ctx)

    @_modlog.command(name="commandlevel", aliases=["commandslevel"])
    async def _command_level(self, ctx: commands.Context, *level: CommandPrivs) -> None:
        """
        Set the level of commands to be logged.

        - `[level...]` must include all levels you want from:
         - `NONE`
         - `MOD`
         - `ADMIN`
         - `GUILD_OWNER`
         - `BOT_OWNER`

        These are the basic levels commands check for in permissions.
        `NONE` is a command anyone has permission to use, where as `MOD`
        can be `mod or permissions`
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        if len(level) == 0:
            return await ctx.send_help()
        msg = _("Command logs set to: ")
        self.settings[ctx.guild.id]["commands_used"]["privs"] = list(level)
        await self.save(ctx.guild)
        await ctx.send(msg + humanize_list(level))

    @_modlog.command()
    async def ignore(
        self,
        ctx: commands.Context,
        channel: Union[
            discord.TextChannel,
            discord.ForumChannel,
            discord.CategoryChannel,
            discord.VoiceChannel,
        ],
    ) -> None:
        """
        Ignore a channel from message delete/edit events and bot commands.

        - `<channel>` the channel or category to ignore events in
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id not in cur_ignored:
            cur_ignored.append(channel.id)
            self.settings[guild.id]["ignored_channels"] = cur_ignored
            await self.save(ctx.guild)
            await ctx.send(_("Now ignoring events in {channel}.").format(channel=channel.mention))
        else:
            await ctx.send(
                _("{channel} is already being ignored.").format(channel=channel.mention)
            )

    @_modlog.command()
    async def unignore(
        self,
        ctx: commands.Context,
        channel: Union[
            discord.TextChannel,
            discord.ForumChannel,
            discord.CategoryChannel,
            discord.VoiceChannel,
        ],
    ) -> None:
        """
        Unignore a channel from message delete/edit events and bot commands.

        - `<channel>` the channel to unignore message delete/edit events.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id in cur_ignored:
            cur_ignored.remove(channel.id)
            self.settings[guild.id]["ignored_channels"] = cur_ignored
            await self.save(ctx.guild)
            await ctx.send(_("Now tracking events in {channel}.").format(channel=channel.mention))
        else:
            await ctx.send(_("{channel} is not being ignored.").format(channel=channel.mention))

    @_modlog.group(name="bot", aliases=["bots"])
    async def _modlog_bot(self, ctx: commands.Context) -> None:
        """Bot filter settings."""

    @_modlog_bot.command(name="edits", aliases=["edit"])
    async def _edit_toggle_bots(self, ctx: commands.Context) -> None:
        """
        Toggle message edit notifications for bot users.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Bots edited messages {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_edit.bots():
            self.settings[guild.id]["message_edit"]["bots"] = True
            verb = _("enabled")
        else:
            self.settings[guild.id]["message_edit"]["bots"] = False
            verb = _("disabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_modlog_bot.command(name="deletes", aliases=["delete"])
    async def _delete_bots(self, ctx: commands.Context) -> None:
        """
        Toggle message delete notifications for bot users.

        This will not affect delete notifications for messages that aren't in bot's cache.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        guild = ctx.message.guild
        msg = _("Bot delete logs {enabled_or_disabled}.")
        if not await self.config.guild(guild).message_delete.bots():
            self.settings[ctx.guild.id]["message_delete"]["bots"] = True
            verb = _("enabled")
        else:
            self.settings[ctx.guild.id]["message_delete"]["bots"] = False
            verb = _("disabled")
        await self.save(ctx.guild)
        await ctx.send(msg.format(enabled_or_disabled=verb))

    @_modlog_bot.command(name="change")
    async def _user_bot_logging(self, ctx: commands.Context) -> None:
        """
        Toggle bots from being logged in user updates.

        This includes roles and nickname.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["user_change"]["bots"]
        self.settings[ctx.guild.id]["user_change"]["bots"] = not setting
        await self.save(ctx.guild)
        if setting:
            await ctx.send(_("Bots will no longer be tracked in member change logs."))
        else:
            await ctx.send(_("Bots will be tracked in member change logs."))

    @_modlog_bot.command(name="voice")
    async def _user_bot_voice_logging(self, ctx: commands.Context) -> None:
        """
        Toggle bots from being logged in voice state updates.
        """
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        setting = self.settings[ctx.guild.id]["voice_change"]["bots"]
        self.settings[ctx.guild.id]["voice_change"]["bots"] = not setting
        await self.save(ctx.guild)
        if setting:
            await ctx.send(_("Bots will no longer be tracked in voice update logs."))
        else:
            await ctx.send(_("Bots will be tracked in voice update logs."))
