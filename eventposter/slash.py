import logging
from typing import Optional

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator

log = logging.getLogger("red.trusty-cogs.EventPoster")
_ = Translator("EventPoster", __file__)


class PartialEmojiTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> discord.PartialEmoji:
        return discord.PartialEmoji.from_str(value)


class EventPosterSlash:

    event_editing = app_commands.Group(name="edit", description="Edit thinkgs about your event")
    event_set = app_commands.Group(
        name="set", description="Manage server specific settings for events"
    )

    @app_commands.command(name="ping")
    async def event_ping_slash(
        self,
        interaction: discord.Interaction,
        include_maybe: Optional[bool],
        message: Optional[str],
    ):
        """Ping all the registered members for your event with optional message"""

        await self.event_ping(interaction, include_maybe, message=message)

    @app_commands.command(name="make")
    async def make_event_slash(
        self,
        interaction: discord.Interaction,
        members: Optional[discord.Member],
        max_slots: Optional[int],
        description: str,
    ):
        """Create an event"""

        await self.make_event(interaction, [members], max_slots, description=description)

    @app_commands.command(name="clear")
    async def clear_event_slash(self, interaction: discord.Interaction, clear: Optional[bool]):
        """Delete/End your active event so you can make more"""

        await self.clear_event(interaction, clear)

    @app_commands.command(name="show")
    async def show_event_slash(
        self, interaction: discord.Interaction, member: Optional[discord.Member]
    ):
        """Show your current event or another members event."""

        await self.show_event(interaction, member)

    @app_commands.command(name="join")
    async def join_event_slash(self, interaction: discord.Interaction, hoster: discord.Member):
        """Join an event being hosted"""

        await self.join_event(interaction, hoster)

    @app_commands.command(name="leave")
    async def leave_event_slash(self, interaction: discord.Interaction, hoster: discord.Member):
        """Leave an event being hosted"""

        await self.leave_event(interaction, hoster)

    @event_editing.command(name="title")
    async def title_slash(self, interaction: discord.Interaction, new_description: str):
        """Edit the title of your event"""

        await self.title(interaction, new_description=new_description)

    @event_editing.command(name="slots")
    async def slots_slash(self, interaction: discord.Interaction, new_slots: Optional[int]):
        """Edit the number of slots available for your event"""

        await self.slots(interaction, new_slots)

    @event_editing.command(name="remaining")
    async def remaining_slash(self, interaction: discord.Interaction):
        """Show how long until your event will automatically ended if available."""

        await self.remaining(interaction)

    @event_editing.command(name="memberadd")
    async def members_add_slash(
        self, interaction: discord.Interaction, new_members: discord.Member
    ):
        """Add a new member to your event"""

        await self.members_add(interaction, [new_members])

    @event_editing.command(name="memberremove")
    async def members_remove_slash(
        self, interaction: discord.Interaction, members: discord.Member
    ):
        """Remove members from your event"""

        await self.members_remove(interaction, [members])

    @event_editing.command(name="maybeadd")
    async def maybe_add_slash(self, interaction: discord.Interaction, new_members: discord.Member):
        """Add a new member to your event"""

        await self.maybe_add(interaction, [new_members])

    @event_editing.command(name="mayberemove")
    async def maybe_remove_slash(self, interaction: discord.Interaction, members: discord.Member):
        """Remove members from your event"""

        await self.maybe_remove(interaction, [members])

    @event_set.command(name="settings")
    async def show_event_settings_slash(self, interaction: discord.Interaction):
        """Show the current event settings."""
        func = self.show_event_settings

        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @event_set.command(name="addplayerclass")
    async def add_guild_playerclass_slash(
        self,
        interaction: discord.Interaction,
        player_class: str,
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
    ):
        """Add a playerclass choice for users to pick from on this server."""
        func = self.add_guild_playerclass

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, emoji, player_class=player_class)

    @event_set.command(name="removeplayerclass")
    async def remove_guild_playerclass_slash(
        self, interaction: discord.Interaction, player_class: str
    ):
        """Remove a playerclass choice for users to pick from on this server."""
        func = self.remove_guild_playerclass

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, player_class=player_class)

    @event_set.command(name="listplayerclass")
    async def list_guild_playerclass_slash(self, interaction: discord.Interaction):
        """List the playerclass choices in this server."""
        func = self.list_guild_playerclass

        if not await self.check_requires(func, interaction):
            return
        await func(interaction)

    @event_set.command(name="defaultmax")
    async def set_default_max_slots_slash(
        self, interaction: discord.Interaction, max_slots: Optional[int]
    ):
        """Set the servers default maximum slots."""
        func = self.set_default_max_slots

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, max_slots)

    @event_set.command(name="channel")
    async def set_channel_slash(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]
    ):
        """Set the Announcement channel for events."""
        func = self.set_channel

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, channel)

    @event_set.command(name="approvalchannel")
    async def set_approval_channel_slash(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel]
    ):
        """Set the admin approval channel"""
        func = self.set_approval_channel

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, channel)

    @event_set.command(name="thread")
    async def make_thread_slash(self, interaction: discord.Interaction, true_or_false: bool):
        """Set whether to make a thread on event announcements"""
        func = self.make_thread

        if not await self.check_requires(func, interaction):
            return
        await func(interaction, true_or_false)

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
        resp = await func.can_run(fake_ctx)
        if not resp:
            await interaction.response.send_message(
                _("You are not authorized to use this command."), ephemeral=True
            )
        return resp

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
