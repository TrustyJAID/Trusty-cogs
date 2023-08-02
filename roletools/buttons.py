from __future__ import annotations

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .abc import RoleToolsMixin
from .components import ButtonRole, RoleToolsView
from .converter import ButtonFlags, RoleHierarchyConverter
from .menus import BaseMenu, ButtonRolePages

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsButtons(RoleToolsMixin):
    """This class handles setting up button roles"""

    async def initialize_buttons(self):
        for guild_id, settings in self.settings.items():
            if guild_id not in self.views:
                log.trace("Adding guild ID %s to views in buttons", guild_id)
                self.views[guild_id] = {}
            for button_name, button_data in settings["buttons"].items():
                log.verbose("Adding Button %s", button_name)
                role_id = button_data["role_id"]
                emoji = button_data["emoji"]
                if emoji is not None:
                    emoji = discord.PartialEmoji.from_str(emoji)

                guild = self.bot.get_guild(guild_id)
                for message_id in set(button_data.get("messages", [])):
                    # we need a new instance of this object for every message
                    button = ButtonRole(
                        style=button_data["style"],
                        label=button_data["label"],
                        emoji=emoji,
                        custom_id=f"{button_name}-{role_id}",
                        role_id=role_id,
                        name=button_name,
                    )
                    if guild is not None:
                        button.replace_label(guild)
                    if message_id not in self.views[guild_id]:
                        log.trace("Creating view for button %s", button_name)
                        self.views[guild_id][message_id] = RoleToolsView(self)
                    if button.custom_id not in {
                        c.custom_id for c in self.views[guild_id][message_id].children
                    }:
                        try:
                            self.views[guild_id][message_id].add_item(button)
                        except ValueError:
                            log.error(
                                "There was an error adding button %s on message https://discord.com/channels/%s/%s",
                                button.name,
                                guild_id,
                                message_id.replace("-", "/"),
                            )

    @roletools.group(name="buttons", aliases=["button"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def buttons(self, ctx: Context) -> None:
        """
        Setup role buttons
        """

    @buttons.command(name="create", usage="<name> <role> [extras]")
    async def create_button(
        self,
        ctx: Context,
        name: str,
        role: RoleHierarchyConverter,
        *,
        extras: ButtonFlags,
    ) -> None:
        """
        Create a role button

        - `<name>` - The name of the button for use later in setup.
        - `<role>` - The role this button will assign or remove.
        - `[extras]`
         - `label:` - The optional label for the button.
         - `emoji:` - The optional emoji used in the button.
         - `style:` - The background button style. Must be one of the following:
           - `primary`
           - `secondary`
           - `success`
           - `danger`
           - `blurple`
           - `grey`
           - `green`
           - `red`

        Note: If no label and no emoji are provided the roles name will be used instead.
        This name will not update if the role name is changed.

        Example:
            `[p]roletools button create role1 @role label: Super fun role style: blurple emoji: 😀`
        """
        if " " in name:
            await ctx.send(_("There cannot be a space in the name of a button."))
            return
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        emoji_id = None
        if extras.emoji is not None:
            if not isinstance(extras.emoji, discord.PartialEmoji):
                try:
                    await ctx.message.add_reaction(extras.emoji)
                    emoji_id = str(extras.emoji)
                except Exception:
                    emoji_id = None
            else:
                emoji_id = f"{extras.emoji.name}:{extras.emoji.id}"
                if extras.emoji.animated:
                    emoji_id = f"a:{emoji_id}"
        label = extras.label or ""
        if not emoji_id and not label:
            label = f"@{role.name}"

        button_settings = {
            "role_id": role.id,
            "label": label,
            "emoji": emoji_id,
            "style": extras.style.value,
            "name": name.lower(),
            "messages": [],
        }
        custom_id = f"{name.lower()}-{role.id}"
        async with self.config.guild(ctx.guild).buttons() as buttons:
            if name.lower() in buttons and buttons[name.lower()]["role_id"] == role.id:
                # only transfer messages settings and fix old buttons if the role ID has not changed
                # this will allow for seamlessly modifying a buttons look
                button_settings["messages"] = buttons[name.lower()]["messages"]
            buttons[name.lower()] = button_settings

        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        self.settings[ctx.guild.id]["buttons"][name.lower()] = button_settings
        async with self.config.role(role).buttons() as buttons:
            if name.lower() not in buttons:
                buttons.append(name.lower())
        button = ButtonRole(
            style=extras.style.value,
            label=label,
            emoji=emoji_id,
            custom_id=custom_id,
            role_id=role.id,
            name=name.lower(),
        )
        for message_id in button_settings["messages"]:
            # fix old buttons with the new one when interacted with
            replacement_view = self.views.get(ctx.guild.id, {}).get(message_id, None)
            if replacement_view is None:
                continue
            for item in replacement_view.children:
                if item.custom_id == custom_id:
                    replacement_view.remove_item(item)
            replacement_view.add_item(button)
        button.replace_label(ctx.guild)
        view = RoleToolsView(self, timeout=180.0)
        view.add_item(button)
        await ctx.send("Here is how your button will look.", view=view)
        await self.confirm_selfassignable(ctx, [role])

    @buttons.command(name="delete", aliases=["del", "remove"])
    async def delete_button(self, ctx: Context, *, name: str) -> None:
        """
        Delete a saved button.

        `<name>` - the name of the button you want to delete.
        """
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        async with self.config.guild(ctx.guild).buttons() as buttons:
            if name in buttons:
                role_id = buttons[name]["role_id"]
                custom_id = f"{name.lower()}-{role_id}"
                for view in self.views[ctx.guild.id].values():
                    for child in view.children:
                        if child.custom_id == custom_id:
                            child.disabled = True
                if name in self.settings.get(ctx.guild.id, {}).get("buttons", {}):
                    del self.settings[ctx.guild.id]["buttons"][name]
                del buttons[name]
                async with self.config.role_from_id(role_id).buttons() as role_buttons:
                    if name in role_buttons:
                        role_buttons.remove(name)
                msg = _("Button `{name}` has been deleted.").format(name=name)
            else:
                msg = _("Button `{name}` doesn't appear to exist.").format(name=name)
        await ctx.send(msg)

    @buttons.command(name="view")
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def button_roles_view(self, ctx: Context) -> None:
        """
        View current buttons setup for role assign in this server.
        """
        no_buttons = _("There are no button roles on this server.")
        if ctx.guild.id not in self.settings:
            await ctx.send(no_buttons)
            return
        pages = []
        colour_index = {
            1: "blurple",
            2: "grey",
            3: "green",
            4: "red",
        }
        for name, button_data in self.settings[ctx.guild.id]["buttons"].items():
            msg = _("Button Roles in {guild}\n").format(guild=ctx.guild.name)
            role = ctx.guild.get_role(button_data["role_id"])
            emoji = button_data["emoji"]
            if emoji is not None:
                emoji = discord.PartialEmoji.from_str(emoji)
            style = colour_index[button_data["style"]]
            msg += _(
                "**Name:** {name}\n**Role:** {role}\n**Label:** {label}\n"
                "**Style:** {style}\n**Emoji:** {emoji}\n"
            ).format(
                name=name,
                role=role.mention if role else _("Missing Role"),
                label=button_data["label"],
                style=style,
                emoji=emoji,
            )
            for messages in button_data["messages"]:
                channel_id, msg_id = messages.split("-")

                channel = ctx.guild.get_channel(int(channel_id))
                if channel:
                    # This can be potentially a very expensive operation
                    # so instead we fake the message link unless the channel is missing
                    # this way they can check themselves without rate limitng
                    # the bot trying to fetch something constantly that is broken.
                    message = f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{msg_id}"
                else:
                    message = "None"
                msg += _("[Button Message]({message})\n").format(
                    message=message,
                )
            pages.append(msg)
        if not pages:
            await ctx.send(no_buttons)
            return
        await BaseMenu(
            source=ButtonRolePages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @buttons.command(name="cleanup")
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True)
    async def button_cleanup(self, ctx: commands.Context):
        """
        Check each button that has registered a message still exists and remove buttons with
        missing messages.

        # Note: This will also potentially cause problems if the button exists in a thread
        it will not be found if the thread is archived and subsequently removed.
        """
        guild = ctx.guild
        async with ctx.typing():
            async with self.config.guild(guild).buttons() as buttons:
                for name, button_settings in self.settings[guild.id].get("buttons", {}).items():
                    messages = set(button_settings["messages"])
                    for message_ids in button_settings["messages"]:
                        try:
                            channel_id, message_id = message_ids.split("-")
                            channel = guild.get_channel_or_thread(int(channel_id))
                            # threads shouldn't be used and this will break if the thread
                            # in question is archived
                            if channel is None:
                                messages.remove(message_ids)
                                continue
                            await channel.fetch_message(int(message_id))
                        except discord.Forbidden:
                            # We can't confirm the message doesn't exist with this
                            continue
                        except (discord.NotFound, discord.HTTPException):
                            messages.remove(message_ids)
                            log.info(
                                "Removing %s message reference on %s button %s since it can't be found.",
                                message_ids,
                                name,
                                guild.id,
                            )
                        except Exception:
                            log.exception(
                                "Error attempting to remove a message reference on select menu %s",
                                name,
                            )
                            continue
                    buttons[name]["messages"] = list(messages)
                    self.settings[guild.id]["buttons"][name]["messages"] = list(messages)
        await ctx.send(_("I am finished deleting old button message references."))
