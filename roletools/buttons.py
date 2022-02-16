from __future__ import annotations

import logging
from typing import Optional, Union

import discord
from discord import Interaction
from discord.ext.commands import BadArgument, Converter
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator

from .abc import RoleToolsMixin, roletools
from .converter import ButtonStyleConverter, RoleHierarchyConverter
from .menus import BaseMenu, ButtonRolePages

log = logging.getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class ButtonRole(discord.ui.Button):
    def __init__(
        self,
        style: int,
        label: str,
        emoji: Union[discord.PartialEmoji, str],
        custom_id: str,
        role_id: int,
        name: str,
    ):
        super().__init__(style=style, label=label, emoji=emoji, custom_id=custom_id)
        self.role_id = role_id
        self.name = name

    async def callback(self, interaction: discord.Interaction):
        log.debug("Receiving button press")
        guild = interaction.message.guild
        role = guild.get_role(self.role_id)
        config = self.view.cog.config
        if role not in interaction.user.roles:
            if not await config.role(role).selfassignable():
                return
            if not role:
                return
            if interaction.user.bot:
                return
            if await self.view.cog.check_guild_verification(interaction.user, guild):
                log.debug("Ignoring user due to verification check.")
                return
            if getattr(interaction.user, "pending", False):
                return
            log.debug(f"Adding role to {interaction.user.name} in {guild}")
            await self.view.cog.give_roles(interaction.user, [role], _("Button Role"))
            await interaction.response.send_message(
                _("I have given you the {role} role.").format(role=role.mention), ephemeral=True
            )
        elif role in interaction.user.roles:
            if not await config.role(role).selfremovable():
                return

            if not role:
                return
            if interaction.user.bot:
                return
            log.debug(f"Removing role from {interaction.user.name} in {guild}")
            await self.view.cog.remove_roles(interaction.user, [role], _("Reaction Role"))
            await interaction.response.send_message(
                _("I have removed the {role} role from you.").format(role=role.mention),
                ephemeral=True,
            )


class ButtonRoleConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> ButtonRole:
        async with ctx.cog.config.guild(ctx.guild).buttons() as buttons:
            log.debug(argument)
            if argument.lower() in buttons:
                log.debug("Button exists")
                button_data = buttons[argument.lower()]
                role_id = button_data["role_id"]
                emoji = button_data["emoji"]
                if emoji is not None:
                    emoji = discord.PartialEmoji.from_str(emoji)
                button = ButtonRole(
                    style=button_data["style"],
                    label=button_data["label"],
                    emoji=emoji,
                    custom_id=f"{argument.lower()}-{role_id}",
                    role_id=role_id,
                    name=argument.lower(),
                )
                return button
            else:
                raise BadArgument(
                    _("Button with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )


class ButtonRoleView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        self.cog = cog
        super().__init__(timeout=None)
        pass


class RoleToolsButtons(RoleToolsMixin):
    """This class handles setting up button roles"""

    async def initialize_buttons(self):
        for guild_id, settings in self.settings.items():
            for button_name, button_data in settings["buttons"].items():
                log.debug(f"Adding Button {button_name}")
                view = ButtonRoleView(self)
                role_id = button_data["role_id"]
                emoji = button_data["emoji"]
                if emoji is not None:
                    emoji = discord.PartialEmoji.from_str(emoji)
                button = ButtonRole(
                    style=button_data["style"],
                    label=button_data["label"],
                    emoji=emoji,
                    custom_id=f"{button_name}-{role_id}",
                    role_id=role_id,
                    name=button_name,
                )
                view.add_item(button)
                self.bot.add_view(view)
                self.views.append(view)

    async def button_autocomplete(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).buttons()
        cur_values = interaction.data["options"][0]["options"][0]["options"]
        cur_value = next(i for i in cur_values if i.get("focused", False)).get("value")
        supplied_options = ""
        new_option = ""
        for sup in cur_value.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            {"name": f"{supplied_options} {g}", "value": f"{supplied_options} {g}"}
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(0, {"name": supplied_options, "value": supplied_options})
        return ret

    @roletools.group(name="buttons", aliases=["button"])
    @commands.admin_or_permissions(manage_roles=True)
    async def buttons(self, ctx: Union[Context, Interaction]) -> None:
        """
        Setup role buttons
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "view": self.button_roles_view,
                "send": self.send_buttons,
                "create": self.create_button,
                "delete": self.delete_button,
                "edit": self.edit_with_buttons,
            }
            options = ctx.data["options"][0]["options"][0]["options"]
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            if ctx.is_autocomplete and option in ["create", "edit", "delete"]:
                new_options = await self.button_autocomplete(ctx)
                if len(new_options) == 0:
                    new_options.append(
                        {
                            "name": "You need to create some options first.",
                            "value": "This option does not exist",
                        }
                    )
                await ctx.response.autocomplete(new_options[:25])
                return
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return

            try:
                kwargs = {}
                for op in options:
                    name = op["name"]
                    if name in kwargs:
                        continue
                    kwargs[name] = self.convert_slash_args(ctx, op)
            except KeyError:
                kwargs = {}
                pass
            except AttributeError:
                await ctx.response.send_message(
                    ("One or more options you have provided are not available in DM's."),
                    ephemeral=True,
                )
                return
            await func(ctx, **kwargs)

    @buttons.command(name="send")
    async def send_buttons(
        self,
        ctx: Union[Context, Interaction],
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
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
            _buttons = []
            for menu in buttons.split(" "):
                if menu:
                    _buttons.append(await ButtonRoleConverter().convert(fake_ctx, menu))
            buttons = _buttons

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
        if is_slash:
            await ctx.followup.send(_("Message sent."))

    @buttons.command(name="edit")
    async def edit_with_buttons(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        buttons: commands.Greedy[ButtonRoleConverter],
    ) -> None:
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[buttons]...` - The names of the buttons you want to include up to a maximum of 25.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True

            try:
                fake_ctx = discord.Object(ctx.id)
                fake_ctx.bot = self.bot
                fake_ctx.channel = ctx.channel
                fake_ctx.guild = ctx.guild
                fake_ctx.cog = self
                message = await commands.MessageConverter().convert(fake_ctx, message)
            except Exception:
                log.exception("Cannot find message to edit")
                await ctx.response.send_message(_("That message could not be found."))
                return
            await ctx.response.defer()
            _buttons = []
            for menu in buttons.split(" "):
                if menu:
                    _buttons.append(await ButtonRoleConverter().convert(fake_ctx, menu))
            buttons = _buttons

        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
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
        if is_slash:
            await ctx.followup.send(_("Message edited."))

    @buttons.command(name="create")
    async def create_button(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
        style: Optional[ButtonStyleConverter] = discord.ButtonStyle.primary,
    ) -> None:
        """
        Create a role button

        `<name>` - The name of the button for use later in setup.
        `<role>` - The role this button will assign or remove.
        `[label]` - The optional label for the button.
        `[emoji]` - The optional emoji used in the button.
        `[style]` - The background button style. Must be one of the following:
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
        """
        if " " in name:
            await ctx.send(_("There cannot be a space in the name of a button."))
            return
        emoji_id = None
        if emoji is not None:
            if not isinstance(emoji, discord.PartialEmoji):
                try:
                    await ctx.message.add_reaction(emoji)
                    emoji_id = str(emoji)
                except Exception:
                    emoji_id = None
            else:
                emoji_id = f"{emoji.name}:{emoji.id}"
                if emoji.animated:
                    emoji_id = f"a:{emoji_id}"
        if not emoji_id and not label:
            label = f"@{role.name}"

        async with self.config.guild(ctx.guild).buttons() as buttons:
            messages = []
            if name.lower() in buttons:
                messages = buttons[name.lower()]["messages"]
            buttons[name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "style": style.value,
                "name": name.lower(),
                "messages": messages,
            }
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["buttons"][name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "style": style.value,
                "name": name.lower(),
                "messages": messages,
            }
        async with self.config.role(role).buttons() as buttons:
            if name.lower() not in buttons:
                buttons.append(name.lower())
        button = ButtonRole(
            style=style,
            label=label,
            emoji=emoji_id,
            custom_id=f"{name.lower()}-{role.id}",
            role_id=role.id,
            name=name.lower(),
        )
        view = ButtonRoleView(self)
        view.add_item(button)
        self.views.append(view)
        msg = await ctx.send("Here is how your button will look.", view=view)
        async with self.config.guild(ctx.guild).buttons() as buttons:
            buttons[name.lower()]["messages"].append(f"{msg.channel.id}-{msg.id}")

    @buttons.command(name="delete", aliases=["del", "remove"])
    async def delete_button(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        """
        Delete a saved button.

        `<name>` - the name of the button you want to delete.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
            _buttons = []
            for menu in buttons.split(" "):
                if menu:
                    _buttons.append(await ButtonRoleConverter().convert(fake_ctx, menu))
            buttons = _buttons

        async with self.config.guild(ctx.guild).buttons() as buttons:
            if name in buttons:
                role_id = buttons[name]["role_id"]
                del buttons[name]
                async with self.config.role_from_id(role_id).buttons() as role_buttons:
                    if name in role_buttons:
                        role_buttons.remove(name)
                msg = _("Button `{name}` has been deleted.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
            else:
                msg = _("Button `{name}` doesn't appear to exist.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)

    @buttons.command(name="view")
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def button_roles_view(self, ctx: Union[Context, Interaction]) -> None:
        """
        View current buttons setup for role assign in this server.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()

        if ctx.guild.id not in self.settings:
            msg = _("There are no button roles in this server.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
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
                    message = (
                        f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{msg_id}"
                    )
                else:
                    message = "None"
                msg += _("[Button Message]({message})\n").format(
                    message=message,
                )
            pages.append(msg)
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
