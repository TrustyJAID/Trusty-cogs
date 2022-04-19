import logging
import re
from typing import Literal, Optional

import discord
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import RoleToolsMixin
from .converter import RoleHierarchyConverter

_ = Translator("RoleTools", __file__)
log = logging.getLogger("red.trusty-cogs.RoleTools")


class PartialEmojiTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> discord.PartialEmoji:
        return discord.PartialEmoji.from_str(value)


class MessageTransformer(app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> discord.Message:
        # TODO: figure out how to transform to a message object properly
        return value


class RoleToolsSlash(RoleToolsMixin):

    exclude_slash = app_commands.Group(name="exclude", description="Set role exclusion")
    include_slash = app_commands.Group(name="include", description="Set role inclusion")
    required_slash = app_commands.Group(name="required", description="Set role requirements")
    buttons_slash = app_commands.Group(name="buttons", description="Setup role buttons")
    select_slash = app_commands.Group(name="select", description="Setup role select menus")
    selfrole_slash = app_commands.Group(
        name="selfrole", description="Add or remove a defined selfrole"
    )

    def __init__(self, *args):
        super().__init__()
        self.config: Config

    @selfrole_slash.command(name="add")
    async def selfrole_add_slash(self, interaction: discord.Interaction, role: discord.Role):
        """Give yourself a role"""
        func = self.selfrole_add
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role)

    @selfrole_slash.command(name="remove")
    async def selfrole_remove_slash(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from yourself"""
        func = self.selfrole_remove
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role)

    @app_commands.command(name="forcerole")
    async def forcerole_slash(
        self, interaction: discord.Interaction, user: discord.User, role: discord.Role
    ):
        """Force a sticky role on a user"""
        func = self.forcerole
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, [user], role=role)

    @app_commands.command(name="forceroleremove")
    async def forceroleremove_slash(
        self, interaction: discord.Interaction, user: discord.User, role: discord.Role
    ):
        """Force remove a sticky role on a user"""
        func = self.forceroleremove
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, [user], role=role)

    @app_commands.command(name="view")
    async def viewroles_slash(
        self, interaction: discord.Interaction, role: Optional[discord.Role]
    ):
        """View current roletools setup for each role in the server"""
        func = self.viewroles
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role=role)

    @exclude_slash.command(name="add")
    async def exclusive_add_slash(
        self, interaction: discord.Interaction, role: discord.Role, exclude: discord.Role
    ):
        """Add role exclusion"""
        func = self.exclusive_add
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, exclude)

    @exclude_slash.command(name="remove")
    async def exclusive_remove_slash(
        self, interaction: discord.Interaction, role: discord.Role, exclude: discord.Role
    ):
        """Remove role exclusion"""
        func = self.exclusive_remove
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, exclude)

    @include_slash.command(name="add")
    async def inclusive_add_slash(
        self, interaction: discord.Interaction, role: discord.Role, include: discord.Role
    ):
        """Add role inclusion"""
        func = self.inclusive_add
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, include)

    @include_slash.command(name="remove")
    async def inclusive_remove_slash(
        self, interaction: discord.Interaction, role: discord.Role, include: discord.Role
    ):
        """Remove role inclusion"""
        func = self.inclusive_remove
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, include)

    @required_slash.command(name="add")
    async def required_add_slash(
        self, interaction: discord.Interaction, role: discord.Role, required: discord.Role
    ):
        """Add role requirements"""
        func = self.required_add
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, required)

    @required_slash.command(name="remove")
    async def required_remove_slash(
        self, interaction: discord.Interaction, role: discord.Role, required: discord.Role
    ):
        """Remove role requirements"""
        func = self.required_remove
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, role, required)

    @app_commands.command(name="cleanup")
    async def cleanup_slash(self, interaction: discord.Interaction):
        """Cleanup old/missing reaction roles and settings."""
        func = self.cleanup
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx)

    @app_commands.command(name="reactroles")
    async def reactroles_slash(self, interaction: discord.Interaction):
        """View current reaction roles in the server."""
        func = self.reactroles

        if not await self.check_requires(func, ctx):
            return
        await func(ctx)

    @app_commands.command(name="clearreact")
    async def clearreact_slash(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[str, MessageTransformer],
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
    ):
        """Clear the reactions for reaction roles."""
        func = self.clearreact
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, message, [emoji] if emoji else None)

    @app_commands.command(name="react")
    async def react_slash(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[str, MessageTransformer],
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
        role: discord.Role,
    ):
        """Create a reaction role."""
        func = self.react
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        try:
            await RoleHierarchyConverter().convert(interaction, role.mention)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)
            return
        await func(ctx, message, [emoji] if emoji else None, role=role)

    @app_commands.command(name="remreact")
    async def remreact_slash(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[str, MessageTransformer],
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
        role: Optional[discord.Role],
    ):
        """Remove a reaction role."""
        func = self.remreact
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        try:
            await RoleHierarchyConverter().convert(interaction, role.mention)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)
            return
        if emoji:
            role_or_emoji = emoji
        if role:
            role_or_emoji = role
        await func(ctx, message, role_or_emoji=role_or_emoji)

    @app_commands.command(name="selfadd")
    async def selfadd_slash(
        self, interaction: discord.Interaction, true_or_false: Optional[bool], role: discord.Role
    ):
        """Set whether or not a user can apply the role to themselves."""
        func = self.selfadd
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, true_or_false, role=role)

    @app_commands.command(name="selfrem")
    async def selfrem_slash(
        self, interaction: discord.Interaction, true_or_false: Optional[bool], role: discord.Role
    ):
        """Set whether or not a user can remove a role form themselves."""
        func = self.selfrem
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, true_or_false, role=role)

    @app_commands.command(name="sticky")
    async def sticky_slash(
        self, interaction: discord.Interaction, true_or_false: Optional[bool], role: discord.Role
    ):
        """Set whether or not a role will be re-applied when a user leaves and rejoins the server."""
        func = self.sticky
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, true_or_false, role=role)

    @app_commands.command(name="autorole")
    async def autorole_slash(
        self, interaction: discord.Interaction, true_or_false: Optional[bool], role: discord.Role
    ):
        """Set a role to be automatically applied when a user joins the server."""
        func = self.autorole
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, true_or_false, role=role)

    @app_commands.command(name="cost")
    async def cost_slash(
        self, interaction: discord.Interaction, cost: Optional[int], role: discord.Role
    ):
        """Set the cost to acquire a role."""
        func = self.cost
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, cost, role=role)

    @buttons_slash.command(name="view")
    async def button_roles_view_slash(
        self,
        interaction: discord.Interaction,
    ):
        """View current buttons setup for role assign in this server."""
        func = self.button_roles_view
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx)

    @buttons_slash.command(name="send")
    async def send_buttons_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        buttons: str,
        message: str,
    ):
        """Send buttons to a specified channel with optional message."""
        func = self.send_buttons
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, channel, buttons, message=message)

    @buttons_slash.command(name="create")
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Primary", value="primary"),
            app_commands.Choice(name="Secondary", value="secondary"),
            app_commands.Choice(name="Success", value="success"),
            app_commands.Choice(name="Danger", value="danger"),
            app_commands.Choice(name="Blurple", value="blurple"),
            app_commands.Choice(name="Grey", value="grey"),
            app_commands.Choice(name="Green", value="green"),
            app_commands.Choice(name="Red", value="red"),
        ]
    )
    async def create_button_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        role: discord.Role,
        label: Optional[str],
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
        style: Optional[app_commands.Choice[str]],
    ):
        """Create a role button"""
        func = self.create_button
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        try:
            await RoleHierarchyConverter().convert(ctx, role.mention)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)
            return
        await func(ctx, name, role, label, emoji, style)

    @buttons_slash.command(name="delete")
    async def delete_button_slash(self, interaction: discord.Interaction, name: str):
        """Delete a saved button."""
        func = self.delete_button
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, name)

    @buttons_slash.command(name="edit")
    async def edit_with_buttons_slash(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[str, MessageTransformer],
        buttons: str,
    ):
        """Edit a bots message to include Role Buttons"""
        func = self.edit_with_buttons
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, message, buttons)

    @select_slash.command(name="create")
    async def create_select_menu_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        options: str,
        min_values: Optional[int],
        max_values: Optional[int],
        placeholder: Optional[str],
    ):
        """Create a select menu"""
        func = self.create_select_menu
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, name, options, min_values, max_values, placeholder=placeholder)

    @select_slash.command(name="view")
    async def select_menu_views_slash(
        self,
        interaction: discord.Interaction,
    ):
        """View current select menus setup for role assign in this server."""
        func = self.select_menus_view
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx)

    @select_slash.command(name="delete")
    async def delete_select_menu_slash(self, interaction: discord.Interaction, name: str):
        """Delete a saved select menu."""
        func = self.delete_select_menu
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        _name = name.split(" ")[0]
        await func(ctx, _name)

    @select_slash.command(name="edit")
    async def edit_with_select_slash(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[str, MessageTransformer],
        menus: str,
    ):
        """Edit a bots message to include Role Buttons"""
        func = self.edit_with_select
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, message, menus)

    @select_slash.command(name="send")
    async def send_select_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        menus: str,
        message: str,
    ):
        """Send a select menu to a specified channel for role assignment"""
        func = self.send_select
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, channel, menus, message=message)

    @select_slash.command(name="viewoptions")
    async def select_options_view_slash(
        self,
        interaction: discord.Interaction,
    ):
        """View current select menus setup for role assign in this server."""
        func = self.select_options_view
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx)

    @select_slash.command(name="createoption")
    async def create_select_option_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        role: discord.Role,
        label: Optional[str],
        description: Optional[str],
        emoji: Optional[app_commands.Transform[str, PartialEmojiTransformer]],
    ):
        """Create a select menu option"""
        func = self.create_select_option
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        await func(ctx, name, role, label, description, emoji)

    @select_slash.command(name="deleteoption")
    async def delete_select_option_slash(self, interaction: discord.Interaction, name: str):
        """Delete a saved option."""
        func = self.delete_select_option
        ctx = await interaction.client.get_context(interaction)
        if not await self.check_requires(func, ctx):
            return
        _name = name.split(" ")[0]
        await func(ctx, _name)

    @send_buttons_slash.autocomplete("buttons")
    @edit_with_buttons_slash.autocomplete("buttons")
    @delete_button_slash.autocomplete("name")
    async def button_autocomplete(self, interaction: discord.Interaction, current: str) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).buttons()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            app_commands.Choice(name=f"{supplied_options} {g}", value=f"{supplied_options} {g}")
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(0, app_commands.Choice(name=supplied_options, value=supplied_options))
        return ret

    @create_select_menu_slash.autocomplete(name="options")
    @delete_select_option_slash.autocomplete("name")
    async def select_option_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).select_options()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            app_commands.Choice(name=f"{supplied_options} {g}", value=f"{supplied_options} {g}")
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(0, app_commands.Choice(name=supplied_options, value=supplied_options))
        return ret

    @delete_select_menu_slash.autocomplete("name")
    @send_select_slash.autocomplete("menus")
    async def select_menu_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).select_menus()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            app_commands.Choice(name=f"{supplied_options} {g}", value=f"{supplied_options} {g}")
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(0, app_commands.Choice(name=supplied_options, value=supplied_options))
        return ret

    async def check_requires(self, func, ctx: commands.Context):
        resp = await func.requires.verify(ctx, check_all_parents=True)
        if not resp:
            await ctx.send(_("You are not authorized to use this command."), ephemeral=True)
        return resp

    async def check_cooldowns(self, func, ctx: commands.Context):
        try:
            func._prepare_cooldowns(ctx)
        except commands.CommandOnCooldown as e:
            await ctx.send(
                _("This command is still on cooldown. Try again in {time}.").format(
                    time=humanize_timedelta(seconds=e.retry_after)
                )
            )
            return False
        return True

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
        ctx = await interaction.client.get_context(interaction)
        if not await self.bot.ignored_channel_or_guild(ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True
