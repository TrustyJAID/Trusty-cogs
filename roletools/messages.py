from __future__ import annotations

from typing import List

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .abc import RoleToolsMixin
from .components import ButtonRole, RoleToolsView, SelectRole
from .converter import ButtonRoleConverter, SelectRoleConverter

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsMessages(RoleToolsMixin):
    @roletools.group(name="message", with_app_command=False)
    async def roletools_message(self, ctx: commands.Context):
        """Commands for sending/editing messages for roletools"""
        pass

    async def check_totals(self, ctx: commands.Context, buttons: int, menus: int) -> bool:
        menus_total = menus * 5
        total = buttons + menus_total
        if total > 25:
            await ctx.send(
                _(
                    "You have a maximum of 25 slots per message for buttons and menus. "
                    "Buttons count as 1 slot each and menus count as 5 slots each."
                )
            )
            return False
        return True

    @roletools_message.command(name="send", with_app_command=False)
    async def send_message(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        buttons: commands.Greedy[ButtonRoleConverter],
        menus: commands.Greedy[SelectRoleConverter],
        *,
        message: str,
    ) -> None:
        """
        Send a select menu to a specified channel for role assignment

        `<channel>` - the channel to send the button role buttons to.
        `[buttons]...` - The names of the buttons you want included in the
        `[menus]...` - The names of the select menus you want included in the
        message up to a maximum of 5.
        `<message>` - The message to be included with the select menu.

        Note: There is a maximum of 25 slots available on one message. Each menu
        uses up 5 slots while each button uses up 1 slot.
        """
        if not await self.check_totals(ctx, buttons=len(buttons), menus=len(menus)):
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        new_view = RoleToolsView(self)
        for select in menus:
            new_view.add_item(select)
        for button in buttons:
            new_view.add_item(button)

        msg = await channel.send(content=message[:2000], view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"

        await self.save_settings(ctx.guild, message_key, buttons=buttons, select_menus=menus)
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message sent."))

    async def save_settings(
        self,
        guild: discord.Guild,
        message_key: str,
        *,
        buttons: List[ButtonRole] = [],
        select_menus: List[SelectRole] = [],
    ):
        async with self.config.guild(guild).select_menus() as saved_select_menus:
            for select in select_menus:
                messages = set(saved_select_menus[select.name]["messages"])
                messages.add(message_key)
                saved_select_menus[select.name]["messages"] = list(messages)
                self.settings[guild.id]["select_menus"][select.name]["messages"] = list(messages)
        async with self.config.guild(guild).buttons() as saved_buttons:
            for button in buttons:
                messages = set(saved_buttons[button.name]["messages"])
                messages.add(message_key)
                saved_buttons[button.name]["messages"] = list(messages)
                self.settings[guild.id]["buttons"][button.name]["messages"] = list(messages)

    async def check_and_replace_existing(self, guild_id: int, message_key: str):
        if guild_id not in self.views:
            return
        if message_key not in self.views[guild_id]:
            return
        for c in self.views[guild_id][message_key].children:
            if isinstance(c, SelectRole):
                existing = self.settings[guild_id]["select_menus"].get(c.name, {})
                if message_key in existing.get("messages", []):
                    self.settings[guild_id]["select_menus"][c.name]["messages"].remove(message_key)
            elif isinstance(c, ButtonRole):
                existing = self.settings[guild_id]["buttons"].get(c.name, {})
                if message_key in existing.get("messages", []):
                    self.settings[guild_id]["buttons"][c.name]["messages"].remove(message_key)
        await self.config.guild_from_id(guild_id).buttons.set(self.settings[guild_id]["buttons"])
        await self.config.guild_from_id(guild_id).select_menus.set(
            self.settings[guild_id]["select_menus"]
        )

    @roletools_message.command(name="edit", with_app_command=False)
    async def edit_message(
        self,
        ctx: Context,
        message: discord.Message,
        buttons: commands.Greedy[ButtonRoleConverter],
        menus: commands.Greedy[SelectRoleConverter],
    ) -> None:
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[buttons]...` - The names of the buttons you want to include up to a maximum of 25.
        `[menus]...` - The names of the select menus you want to include up to a maximum of 5.

        Note: There is a maximum of 25 slots available on one message. Each menu
        uses up 5 slots while each button uses up 1 slot.
        """
        if not await self.check_totals(ctx, buttons=len(buttons), menus=len(menus)):
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        new_view = RoleToolsView(self)
        for select_menu in menus:
            new_view.add_item(select_menu)
        for button in buttons:
            new_view.add_item(button)
        await message.edit(view=new_view)
        message_key = f"{message.channel.id}-{message.id}"
        await self.check_and_replace_existing(ctx.guild.id, message_key)
        await self.save_settings(ctx.guild, message_key, buttons=buttons, select_menus=menus)
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message edited."))

    @roletools_message.command(name="sendselect", with_app_command=False)
    async def send_select(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        menus: commands.Greedy[SelectRoleConverter],
        *,
        message: str,
    ) -> None:
        """
        Send a select menu to a specified channel for role assignment

        `<channel>` - the channel to send the button role buttons to.
        `[menus]...` - The names of the select menus you want included in the
        message up to a maximum of 5.
        `<message>` - The message to be included with the select menu.
        """
        if not await self.check_totals(ctx, buttons=0, menus=len(menus)):
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        new_view = RoleToolsView(self)
        # for button in s:
        # new_view.add_item(button)
        # log.debug(options)
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        for select in menus:
            new_view.add_item(select)
        msg = await channel.send(content=message, view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"

        await self.save_settings(ctx.guild, message_key, buttons=[], select_menus=menus)
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message sent."))

    @roletools_message.command(name="editselect", with_app_command=False)
    async def edit_with_select(
        self,
        ctx: Context,
        message: discord.Message,
        menus: commands.Greedy[SelectRoleConverter],
    ) -> None:
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[menus]...` - The names of the select menus you want to include up to a maximum of 5.
        """
        if not await self.check_totals(ctx, buttons=0, menus=len(menus)):
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        new_view = RoleToolsView(self)
        for select_menu in menus:
            new_view.add_item(select_menu)
        await message.edit(view=new_view)
        message_key = f"{message.channel.id}-{message.id}"
        await self.check_and_replace_existing(ctx.guild.id, message_key)

        await self.save_settings(ctx.guild, message_key, buttons=[], select_menus=menus)
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message edited."))

    @roletools_message.command(name="sendbutton", with_app_command=False)
    async def send_buttons(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        buttons: commands.Greedy[ButtonRoleConverter],
        *,
        message: str,
    ) -> None:
        """
        Send buttons to a specified channel with optional message.

        `<channel>` - the channel to send the button role buttons to.
        `[buttons]...` - The names of the buttons you want included in the
        message up to a maximum of 25.
        `<message>` - The message to be included with the buttons.
        """
        if not await self.check_totals(ctx, buttons=len(buttons), menus=0):
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        new_view = RoleToolsView(self)
        log.verbose("send_buttons buttons: %s", buttons)
        for button in buttons:
            new_view.add_item(button)
        msg = await channel.send(content=message, view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"

        await self.save_settings(ctx.guild, message_key, buttons=buttons, select_menus=[])
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message sent."))

    @roletools_message.command(name="editbutton", with_app_command=False)
    async def edit_with_buttons(
        self,
        ctx: Context,
        message: discord.Message,
        buttons: commands.Greedy[ButtonRoleConverter],
    ) -> None:
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[buttons]...` - The names of the buttons you want to include up to a maximum of 25.
        """
        if not await self.check_totals(ctx, buttons=len(buttons), menus=0):
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        new_view = RoleToolsView(self)
        for button in buttons:
            new_view.add_item(button)
        await message.edit(view=new_view)
        message_key = f"{message.channel.id}-{message.id}"
        await self.check_and_replace_existing(ctx.guild.id, message_key)

        await self.save_settings(ctx.guild, message_key, buttons=buttons, select_menus=[])
        self.views[ctx.guild.id][message_key] = new_view
        await ctx.send(_("Message edited."))
