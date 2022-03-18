import logging
from typing import Literal, Optional

from datetime import timedelta

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator

try:
    import regex as re
except ImportError:
    import re

_ = Translator("ReTrigger", __file__)
log = logging.getLogger("red.trusty-cogs.ReTrigger")


class PartialEmojiTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> discord.PartialEmoji:
        return discord.PartialEmoji.from_str(value)


class TimeDeltaTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: int) -> timedelta:
        return timedelta(seconds=value)


class SnowflakeTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> int:
        return int(value)


class ReTriggerSlash:

    modlog = app_commands.Group(
        name="modlog", description="Set which events to record in the modlog."
    )
    allowlist = app_commands.Group(
        name="allowlist", description="Set allowlist options for ReTrigger."
    )
    blocklist = app_commands.Group(
        name="blocklist", description="Set blocklist options for ReTrigger."
    )
    edit_slash = app_commands.Group(
        name="edit", description="Edit various settings in a set trigger."
    )

    def __init__(self, *args):
        super().__init__()
        self.config: Config

    @modlog.command(name="settings")
    async def modlog_settings_slash(self, interaction: discord.Interaction):
        """Show retrigger's modlog settings for this server."""
        func = self.modlog_settings
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="bans")
    async def modlog_bans_slash(self, interaction: discord.Interaction):
        """Toggle custom ban messages in the modlog"""
        func = self.modlog_bans
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="kicks")
    async def modlog_kicks_slash(self, interaction: discord.Interaction):
        """Toggle custom kick messages in the modlog"""
        func = self.modlog_kicks
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="filter")
    async def modlog_filter_slash(self, interaction: discord.Interaction):
        """Toggle custom filter messages in the modlog"""
        func = self.modlog_filter
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="addroles")
    async def modlog_addroles_slash(self, interaction: discord.Interaction):
        """Toggle custom add role messages in the modlog"""
        func = self.modlog_addroles
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="removeroles")
    async def modlog_removeroles_slash(self, interaction: discord.Interaction):
        """Toggle custom remove role messages in the modlog"""
        func = self.modlog_removeroles
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @modlog.command(name="channel")
    async def modlog_channel_slash(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]
    ):
        """Set the modlog channel for filtered words"""
        func = self.modlog_channel
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        await func(interaction, channel)

    @allowlist.command(name="add")
    async def whitelist_add_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        channel: Optional[discord.TextChannel],
        user: Optional[discord.User],
        role: Optional[discord.Role],
    ):
        """Add a channel, user, or role to a triggers allowlist"""
        channel_user_role = [channel, user, role]
        if not any(channel_user_role):
            await interaction.response.send_message(
                _("You must provide at least one of either channel, user, or role.")
            )
            return
        func = self.whitelist_add
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [i for i in channel_user_role if i is not None])

    @allowlist.command(name="remove")
    async def whitelist_remove_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        channel: Optional[discord.TextChannel],
        user: Optional[discord.User],
        role: Optional[discord.Role],
    ):
        """Remove a channel, user, or role from a triggers allowlist"""
        channel_user_role = [channel, user, role]
        if not any(channel_user_role):
            await interaction.response.send_message(
                _("You must provide at least one of either channel, user, or role.")
            )
            return
        func = self.whitelist_remove
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [i for i in channel_user_role if i is not None])

    @blocklist.command(name="add")
    async def blacklist_add_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        channel: Optional[discord.TextChannel],
        user: Optional[discord.User],
        role: Optional[discord.Role],
    ):
        """Add a channel, user, or role to a triggers blocklist"""
        channel_user_role = [channel, user, role]
        if not any(channel_user_role):
            await interaction.response.send_message(
                _("You must provide at least one of either channel, user, or role.")
            )
            return
        func = self.blacklist_add
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [i for i in channel_user_role if i is not None])

    @blocklist.command(name="remove")
    async def blacklist_remove_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        channel: Optional[discord.TextChannel],
        user: Optional[discord.User],
        role: Optional[discord.Role],
    ):
        """Remove a channel, user, or role from a triggers blocklist"""
        channel_user_role = [channel, user, role]
        if not any(channel_user_role):
            await interaction.response.send_message(
                _("You must provide at least one of either channel, user, or role.")
            )
            return
        func = self.blacklist_remove
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [i for i in channel_user_role if i is not None])

    @edit_slash.command(name="cooldown")
    async def cooldown_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        time: int,
        style: Optional[Literal["guild", "channel", "member"]] = "guild",
    ):
        """Set cooldown options for ReTrigger"""
        func = self.cooldown
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, time, style)

    @edit_slash.command(name="regex")
    async def edit_regex_slash(self, interaction: discord.Interaction, trigger: str, regex: str):
        """Edit the regex of a saved trigger."""
        func = self.edit_regex
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=argument, e=e)
            await interaction.response.send_message(err_msg)
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, regex=regex)

    # @edit_slash.command(name="ocr")
    async def toggle_ocr_search_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to use Optical Character Recognition"""
        func = self.toggle_ocr_search
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="nsfw")
    async def toggle_nsfw_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether a trigger is considered age-restricted."""
        func = self.toggle_nsfw
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="readfilenames")
    async def toggle_filename_search_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to search message attachment filenames."""
        func = self.toggle_filename_search
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="reply")
    @app_commands.describe(
        set_to="True will reply with mention, False will reply without mention, blank will not use a reply."
    )
    async def set_reply_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: Optional[bool]
    ):
        """Set whether or not to reply to the triggered message."""
        func = self.set_reply
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, set_to)

    @edit_slash.command(name="tts")
    async def set_tts_slash(self, interaction: discord.Interaction, trigger: str, set_to: bool):
        """Set whether or not to send the message with text-to-speech."""
        func = self.set_tts
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, set_to)

    @edit_slash.command(name="usermention")
    async def set_user_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention users"""
        func = self.set_user_menion
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, set_to)

    @edit_slash.command(name="everyonemention")
    async def set_everyone_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention everyone"""
        func = self.set_everyone_mention
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, set_to)

    @edit_slash.command(name="rolemention")
    async def set_role_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention roles"""
        func = self.set_role_mention
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, set_to)

    @edit_slash.command(name="edited")
    async def toggle_check_edits_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to search message edits."""
        func = self.toggle_check_edits
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="ignorecommands")
    async def edit_ignore_commands_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether a trigger will ignore commands."""
        func = self.edit_ignore_commands
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="text")
    async def edit_text_slash(self, interaction: discord.Interaction, trigger: str, text: str):
        """Edit the text of a saved trigger."""
        func = self.edit_text
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, text=text)

    @edit_slash.command(name="chance")
    async def edit_chance_slash(self, interaction: discord.Interaction, trigger: str, chance: int):
        """Edit the chance a trigger will execute."""
        func = self.edit_chance
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, chance)

    @edit_slash.command(name="command")
    async def edit_command_slash(
        self, interaction: discord.Interaction, trigger: str, command: str
    ):
        """Edit the command a trigger runs."""
        func = self.edit_command
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, command=command)

    @edit_slash.command(name="role")
    async def edit_roles_slash(
        self, interaction: discord.Interaction, trigger: str, role: discord.Role
    ):
        """Edit the added or removed role of a saved trigger."""
        func = self.edit_roles
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [role])

    @edit_slash.command(name="reaction")
    async def edit_reactions_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        emoji: app_commands.Transform[str, PartialEmojiTransformer],
    ):
        """Edit the emoji reaction of a saved trigger."""
        func = self.edit_reactions
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger, [emoji])

    @edit_slash.command(name="enable")
    async def enable_trigger_slash(self, interaction: discord.Interaction, trigger: str):
        """Enable a trigger"""
        func = self.enable_trigger
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @edit_slash.command(name="disable")
    async def disable_trigger_slash(self, interaction: discord.Interaction, trigger: str):
        """Disable a trigger"""
        func = self.disable_trigger
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @app_commands.command(name="list")
    @app_commands.describe(guild_id="Only available to bot owner")
    async def list_slash(
        self,
        interaction: discord.Interaction,
        trigger: Optional[str],
        guild_id: Optional[app_commands.Transform[str, SnowflakeTransformer]],
    ):
        """List information about a trigger"""
        func = self.list
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        if guild_id is None:
            guild_id = interaction.guild.id

        if trigger is not None:
            _trigger = self.triggers[guild_id][trigger]
        else:
            _trigger = None
        await func(interaction, guild_id, _trigger)

    @app_commands.command(name="remove")
    async def remove_slash(self, interaction: discord.Interaction, trigger: str):
        """Remove a specified trigger"""
        func = self.remove
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await func(interaction, _trigger)

    @app_commands.command(name="explain")
    async def explain_slash(
        self,
        interaction: discord.Interaction,
        page_num: Optional[app_commands.Range[int, 1, 13]] = 1,
    ):
        """Explain how to use retrigger"""
        await self.explain(interaction, page_num)

    @app_commands.command(name="text")
    async def text_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
        delete_after: Optional[app_commands.Transform[int, TimeDeltaTransformer]],
    ):
        """Add a text response trigger"""
        func = self.text
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, delete_after, text=text)

    @app_commands.command(name="dm")
    async def dm_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a dm response trigger"""
        func = self.dm
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, text=text)

    @app_commands.command(name="dmme")
    async def dmme_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a trigger to dm yourself"""
        func = self.dmme
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, text=text)

    @app_commands.command(name="rename")
    async def rename_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a trigger to rename users"""
        func = self.rename
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, text=text)

    @app_commands.command(name="ban")
    async def ban_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
    ):
        """Add a trigger to ban users"""
        func = self.ban
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex)

    @app_commands.command(name="kick")
    async def kick_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
    ):
        """Add a trigger to kick users"""
        func = self.kick
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex)

    @app_commands.command(name="command")
    async def command_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        command: str,
    ):
        """Add a command trigger"""
        func = self.command
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, command)

    @app_commands.command(name="filter")
    async def filter_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        check_filenames: Optional[bool] = False,
    ):
        """Add a trigger to filter messages"""
        func = self.filter
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, check_filenames, regex=regex)

    @app_commands.command(name="addrole")
    async def addrole_slash(
        self, interaction: discord.Interaction, name: str, regex: str, role: discord.Role
    ):
        """Add a trigger to add a role"""
        func = self.addrole
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, [role])

    @app_commands.command(name="removerole")
    async def removerole_slash(
        self, interaction: discord.Interaction, name: str, regex: str, role: discord.Role
    ):
        """Add a trigger to remove a role"""
        func = self.removerole
        if not await self.pre_check_slash(interaction):
            return
        if not await self.check_requires(func, interaction):
            return
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await func(interaction, name, regex, [role])

    @cooldown_slash.autocomplete("trigger")
    @whitelist_add_slash.autocomplete("trigger")
    @whitelist_remove_slash.autocomplete("trigger")
    @blacklist_add_slash.autocomplete("trigger")
    @blacklist_remove_slash.autocomplete("trigger")
    @toggle_nsfw_slash.autocomplete("trigger")
    @edit_regex_slash.autocomplete("trigger")
    @toggle_filename_search_slash.autocomplete("trigger")
    @set_reply_slash.autocomplete("trigger")
    @set_tts_slash.autocomplete("trigger")
    @set_user_mention_slash.autocomplete("trigger")
    @set_everyone_mention_slash.autocomplete("trigger")
    @set_role_mention_slash.autocomplete("trigger")
    @toggle_check_edits_slash.autocomplete("trigger")
    @edit_ignore_commands_slash.autocomplete("trigger")
    @edit_text_slash.autocomplete("trigger")
    @edit_chance_slash.autocomplete("trigger")
    @edit_command_slash.autocomplete("trigger")
    @edit_roles_slash.autocomplete("trigger")
    @edit_reactions_slash.autocomplete("trigger")
    @enable_trigger_slash.autocomplete("trigger")
    @disable_trigger_slash.autocomplete("trigger")
    @list_slash.autocomplete("trigger")
    @remove_slash.autocomplete("trigger")
    async def trigger_autocomplete(self, interaction: discord.Interaction, current: str):
        guild_id = interaction.guild.id
        if getattr(interaction.namespace, "guild_id") and await self.bot.is_owner(
            interaction.user
        ):
            guild_id = int(interaction.namespace.guild_id)
        if guild_id in self.triggers:
            choices = [
                app_commands.Choice(name=t.name, value=t.name)
                for t in self.triggers[guild_id].values()
                if current in t.name
            ]
        else:
            choices = [app_commands.Choice(name="No Triggers set", value="No Triggers set")]
        return choices[:25]

    async def check_requires(self, func, interaction):
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        fake_ctx.bot = self.bot
        fake_ctx.cog = self
        fake_ctx.command = func
        fake_ctx.permission_state = commands.requires.PermState.NORMAL

        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        resp = await func.requires.verify(fake_ctx)
        if not resp:
            await interaction.response.send_message(
                _("You are not authorized to use this command."), ephemeral=True
            )
        return resp

    async def pre_check_slash(self, interaction):
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        if not await self.bot.ignored_channel_or_guild(fake_ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True
