from __future__ import annotations

import logging

import discord
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .abc import RoleToolsMixin
from .buttons import ButtonRoleConverter, ButtonRoleView
from .select import SelectRoleConverter, SelectRoleView

roletools = RoleToolsMixin.roletools

log = logging.getLogger("red.Trusty-cogs.RoleTools")
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
        new_view = SelectRoleView(self)
        # for button in s:
        # new_view.add_item(button)
        # log.debug(options)

        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        for select in menus:
            new_view.add_item(select)
        for button in buttons:
            new_view.add_item(button)
        self.views.append(new_view)
        msg = await channel.send(content=message, view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            for select in menus:
                select_menus[select.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["select_menus"][select.name.lower()][
                    "messages"
                ].append(message_key)
        async with self.config.guild(ctx.guild).buttons() as saved_buttons:
            for button in buttons:
                saved_buttons[button.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["buttons"][button.name.lower()]["messages"].append(
                    message_key
                )
        await ctx.send(_("Message sent."))

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
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        view = SelectRoleView(self)
        for select_menu in menus:
            view.add_item(select_menu)
        for button in buttons:
            view.add_item(button)
        self.views.append(view)
        await message.edit(view=view)
        message_key = f"{message.channel.id}-{message.id}"
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            for select in menus:
                if message_key not in select_menus[select.name.lower()]["messages"]:
                    select_menus[select.name.lower()]["messages"].append(message_key)
                    self.settings[ctx.guild.id]["select_menus"][select.name.lower()][
                        "messages"
                    ].append(message_key)
        async with self.config.guild(ctx.guild).buttons() as saved_buttons:
            for button in buttons:
                saved_buttons[button.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["buttons"][button.name.lower()]["messages"].append(
                    message_key
                )
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
        new_view = SelectRoleView(self)
        # for button in s:
        # new_view.add_item(button)
        # log.debug(options)
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        for select in menus:
            new_view.add_item(select)
        self.views.append(new_view)
        msg = await channel.send(content=message, view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            for select in menus:
                select_menus[select.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["select_menus"][select.name.lower()][
                    "messages"
                ].append(message_key)
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
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            await ctx.send(msg)
            return
        view = SelectRoleView(self)
        for select_menu in menus:
            view.add_item(select_menu)
        self.views.append(view)
        await message.edit(view=view)
        message_key = f"{message.channel.id}-{message.id}"
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            for select in menus:
                if message_key not in select_menus[select.name.lower()]["messages"]:
                    select_menus[select.name.lower()]["messages"].append(message_key)
                    self.settings[ctx.guild.id]["select_menus"][select.name.lower()][
                        "messages"
                    ].append(message_key)
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
        new_view = ButtonRoleView(self)
        log.info(buttons)
        for button in buttons:
            new_view.add_item(button)
        msg = await channel.send(content=message, view=new_view)
        self.views.append(new_view)
        message_key = f"{msg.channel.id}-{msg.id}"
        async with self.config.guild(ctx.guild).buttons() as saved_buttons:
            for button in buttons:
                saved_buttons[button.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["buttons"][button.name.lower()]["messages"].append(
                    message_key
                )
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
        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            await ctx.send(msg)
            return
        view = ButtonRoleView(self)
        for button in buttons:
            view.add_item(button)
        self.views.append(view)
        await message.edit(view=view)
        message_key = f"{message.channel.id}-{message.id}"
        async with self.config.guild(ctx.guild).buttons() as saved_buttons:
            for button in buttons:
                saved_buttons[button.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["buttons"][button.name.lower()]["messages"].append(
                    message_key
                )
        await ctx.send(_("Message edited."))
