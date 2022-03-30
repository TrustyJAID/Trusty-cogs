import logging
from datetime import timedelta
from typing import Literal, Optional

import discord
from discord import app_commands
from redbot.core import Config, commands
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
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_settings_slash(self, interaction: discord.Interaction):
        """Show retrigger's modlog settings for this server."""
        await self.modlog_settings(interaction)

    @modlog.command(name="bans")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_bans_slash(self, interaction: discord.Interaction):
        """Toggle custom ban messages in the modlog"""
        await self.modlog_bans(interaction)

    @modlog.command(name="kicks")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_kicks_slash(self, interaction: discord.Interaction):
        """Toggle custom kick messages in the modlog"""
        await self.modlog_kicks(interaction)

    @modlog.command(name="filter")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_filter_slash(self, interaction: discord.Interaction):
        """Toggle custom filter messages in the modlog"""
        await self.modlog_filter(interaction)

    @modlog.command(name="addroles")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_addroles_slash(self, interaction: discord.Interaction):
        """Toggle custom add role messages in the modlog"""
        await self.modlog_addroles(interaction)

    @modlog.command(name="removeroles")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_removeroles_slash(self, interaction: discord.Interaction):
        """Toggle custom remove role messages in the modlog"""
        await self.modlog_removeroles(interaction)

    @modlog.command(name="channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def modlog_channel_slash(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]
    ):
        """Set the modlog channel for filtered words"""
        await self.modlog_channel(interaction, channel)

    @allowlist.command(name="add")
    @app_commands.checks.has_permissions(manage_messages=True)
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
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.whitelist_add(
            interaction, _trigger, [i for i in channel_user_role if i is not None]
        )

    @allowlist.command(name="remove")
    @app_commands.checks.has_permissions(manage_messages=True)
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
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.whitelist_remove(
            interaction, _trigger, [i for i in channel_user_role if i is not None]
        )

    @blocklist.command(name="add")
    @app_commands.checks.has_permissions(manage_messages=True)
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
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.blacklist_add(
            interaction, _trigger, [i for i in channel_user_role if i is not None]
        )

    @blocklist.command(name="remove")
    @app_commands.checks.has_permissions(manage_messages=True)
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
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.blacklist_remove(
            interaction, _trigger, [i for i in channel_user_role if i is not None]
        )

    @edit_slash.command(name="cooldown")
    async def cooldown_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        time: int,
        style: Optional[Literal["guild", "channel", "member"]] = "guild",
    ):
        """Set cooldown options for ReTrigger"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.cooldown(interaction, _trigger, time, style)

    @edit_slash.command(name="regex")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_regex_slash(self, interaction: discord.Interaction, trigger: str, regex: str):
        """Edit the regex of a saved trigger."""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=argument, e=e)
            await interaction.response.send_message(err_msg)
            return
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_regex(interaction, _trigger, regex=regex)

    # @edit_slash.command(name="ocr")
    async def toggle_ocr_search_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to use Optical Character Recognition"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.toggle_ocr_search(interaction, _trigger)

    @edit_slash.command(name="nsfw")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def toggle_nsfw_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether a trigger is considered age-restricted."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.toggle_nsfw(interaction, _trigger)

    @edit_slash.command(name="readfilenames")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def toggle_filename_search_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to search message attachment filenames."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.toggle_filename_search(interaction, _trigger)

    @edit_slash.command(name="reply")
    @app_commands.describe(
        set_to="True will reply with mention, False will reply without mention, blank will not use a reply."
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def set_reply_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: Optional[bool]
    ):
        """Set whether or not to reply to the triggered message."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.set_reply(interaction, _trigger, set_to)

    @edit_slash.command(name="tts")
    async def set_tts_slash(self, interaction: discord.Interaction, trigger: str, set_to: bool):
        """Set whether or not to send the message with text-to-speech."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.set_tts(interaction, _trigger, set_to)

    @edit_slash.command(name="usermention")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def set_user_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention users"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.set_user_menion(interaction, _trigger, set_to)

    @edit_slash.command(name="everyonemention")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def set_everyone_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention everyone"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.set_everyone_mention(interaction, _trigger, set_to)

    @edit_slash.command(name="rolemention")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def set_role_mention_slash(
        self, interaction: discord.Interaction, trigger: str, set_to: bool
    ):
        """Set whether or not this trigger can mention roles"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.set_role_mention(interaction, _trigger, set_to)

    @edit_slash.command(name="edited")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def toggle_check_edits_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether to search message edits."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.toggle_check_edits(interaction, _trigger)

    @edit_slash.command(name="ignorecommands")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_ignore_commands_slash(self, interaction: discord.Interaction, trigger: str):
        """Toggle whether a trigger will ignore commands."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_ignore_commands(interaction, _trigger)

    @edit_slash.command(name="text")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_text_slash(self, interaction: discord.Interaction, trigger: str, text: str):
        """Edit the text of a saved trigger."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_text(interaction, _trigger, text=text)

    @edit_slash.command(name="chance")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_chance_slash(self, interaction: discord.Interaction, trigger: str, chance: int):
        """Edit the chance a trigger will execute."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_chance(interaction, _trigger, chance)

    @edit_slash.command(name="command")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit_command_slash(
        self, interaction: discord.Interaction, trigger: str, command: str
    ):
        """Edit the command a trigger runs."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_command(interaction, _trigger, command=command)

    @edit_slash.command(name="role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def edit_roles_slash(
        self, interaction: discord.Interaction, trigger: str, role: discord.Role
    ):
        """Edit the added or removed role of a saved trigger."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_roles(interaction, _trigger, [role])

    @edit_slash.command(name="reaction")
    async def edit_reactions_slash(
        self,
        interaction: discord.Interaction,
        trigger: str,
        emoji: app_commands.Transform[str, PartialEmojiTransformer],
    ):
        """Edit the emoji reaction of a saved trigger."""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.edit_reactions(interaction, _trigger, [emoji])

    @edit_slash.command(name="enable")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def enable_trigger_slash(self, interaction: discord.Interaction, trigger: str):
        """Enable a trigger"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.enable_trigger(interaction, _trigger)

    @edit_slash.command(name="disable")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def disable_trigger_slash(self, interaction: discord.Interaction, trigger: str):
        """Disable a trigger"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.disable_trigger(interaction, _trigger)

    @app_commands.command(name="list")
    @app_commands.describe(guild_id="Only available to bot owner")
    async def list_slash(
        self,
        interaction: discord.Interaction,
        trigger: Optional[str],
        guild_id: Optional[app_commands.Transform[str, SnowflakeTransformer]],
    ):
        """List information about a trigger"""
        if guild_id is None:
            guild_id = interaction.guild.id

        if trigger is not None:
            _trigger = self.triggers[guild_id][trigger]
        else:
            _trigger = None
        await self.list(interaction, guild_id, _trigger)

    @app_commands.command(name="remove")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def remove_slash(self, interaction: discord.Interaction, trigger: str):
        """Remove a specified trigger"""
        _trigger = self.triggers[interaction.guild.id][trigger]
        await self.remove(interaction, _trigger)

    @app_commands.command(name="explain")
    async def explain_slash(
        self,
        interaction: discord.Interaction,
        page_num: Optional[app_commands.Range[int, 1, 13]] = 1,
    ):
        """Explain how to use retrigger"""
        await self.explain(interaction, page_num)

    @app_commands.command(name="text")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def text_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
        delete_after: Optional[app_commands.Transform[int, TimeDeltaTransformer]],
    ):
        """Add a text response trigger"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.text(interaction, name, regex, delete_after, text=text)

    @app_commands.command(name="dm")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def dm_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a dm response trigger"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.dm(interaction, name, regex, text=text)

    @app_commands.command(name="dmme")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def dmme_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a trigger to dm yourself"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.dmme(interaction, name, regex, text=text)

    @app_commands.command(name="rename")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.checks.bot_has_permissions(manage_nicknames=True)
    async def rename_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        text: str,
    ):
        """Add a trigger to rename users"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.rename(interaction, name, regex, text=text)

    @app_commands.command(name="ban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
    ):
        """Add a trigger to ban users"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.ban(interaction, name, regex)

    @app_commands.command(name="kick")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
    ):
        """Add a trigger to kick users"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.kick(interaction, name, regex)

    @app_commands.command(name="command")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def command_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        command: str,
    ):
        """Add a command trigger"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.command(interaction, name, regex, command)

    @app_commands.command(name="filter")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def filter_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        regex: str,
        check_filenames: Optional[bool] = False,
    ):
        """Add a trigger to filter messages"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.filter(interaction, name, check_filenames, regex=regex)

    @app_commands.command(name="addrole")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def addrole_slash(
        self, interaction: discord.Interaction, name: str, regex: str, role: discord.Role
    ):
        """Add a trigger to add a role"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.addrole(interaction, name, regex, [role])

    @app_commands.command(name="removerole")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def removerole_slash(
        self, interaction: discord.Interaction, name: str, regex: str, role: discord.Role
    ):
        """Add a trigger to remove a role"""
        try:
            re.compile(regex)
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=regex, e=e)
            await interaction.response.send_message(err_msg)
            return
        await self.removerole(interaction, name, regex, [role])

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

    async def on_error(
        self, interaction: discord.Interaction, command: discord.app_commands.Command, error
    ):
        if (
            isinstance(error, discord.app_commands.CheckFailure)
            and not interaction.response.is_done()
        ):
            await interaction.response.send_message(error, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        if not interaction.guild:
            await interaction.response.send_message(
                _("This command is not available outside of a guild."), ephemeral=True
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
