from __future__ import annotations
import discord
import logging

from typing import Union, Optional

from discord.ext.commands import BadArgument, Converter

from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.commands import Context
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin, roletools
from .converter import RoleHierarchyConverter, ButtonStyleConverter
from .menus import ButtonRolePages, BaseMenu

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
                button_data = buttons[argument.lower()]
                role_id = button_data["role_id"]
                emoji = button_data["emoji"]
                if len(emoji) > 4:
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

    @roletools.group(name="buttons", aliases=["button"])
    async def buttons(self, ctx: Context) -> None:
        """
        Setup role buttons
        """
        pass

    async def initialize_buttons(self):
        for guild_id, settings in self.settings.items():
            for button_name, button_data in settings["buttons"].items():
                log.debug(f"Adding Button {button_name}")
                view = ButtonRoleView(self)
                role_id = button_data["role_id"]
                emoji = discord.PartialEmoji.from_str(button_data["emoji"])
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

    @buttons.command(name="send")
    async def send_buttons(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        buttons: commands.Greedy[ButtonRoleConverter],
        *,
        message: str,
    ):
        """
        Send buttons to a specified channel with optional message.

        `<channel>` - the channel to send the button role buttons to.
        `[buttons]...` - The names of the buttons you want included in the
        message up to a maximum of 25.
        `<message>` - The message to be included with the buttons.
        """
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

    @buttons.command(name="edit")
    async def edit_with_buttons(
        self,
        ctx: commands.Context,
        message: discord.Message,
        buttons: commands.Greedy[ButtonRoleConverter],
    ):
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[buttons]...` - The names of the buttons you want to include up to a maximum of 25.
        """
        if message.author.id != ctx.me.id:
            await ctx.send(_("I cannot edit someone elses message to include buttons."))
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

    @buttons.command(name="create")
    async def create_button(
        self,
        ctx: Context,
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
        style: Optional[ButtonStyleConverter] = discord.ButtonStyle.primary,
    ):
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
    async def delete_button(self, ctx: Context, *, name: str):
        """
        Delete a saved button.

        `<name>` - the name of the button you want to delete.
        """
        async with self.config.guild(ctx.guild).buttons() as buttons:
            if name in buttons:
                role_id = buttons[name]["role_id"]
                del buttons[name]
                async with self.config.role_from_id(role_id).buttons() as role_buttons:
                    if name in role_buttons:
                        role_buttons.remove(name)
                await ctx.send(_("Button `{name}` has been deleted.").format(name=name))
            else:
                await ctx.send(_("Button `{name}` doesn't appear to exist.").format(name=name))

    @buttons.command(name="view")
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def button_roles_view(self, ctx: Context) -> None:
        """
        View current buttons setup for role assign in this server.
        """
        if ctx.guild.id not in self.settings:
            await ctx.send(_("There are no button roles in this server."))
            return
        pages = []
        colour_index = {
            1: "blurple",
            2: "grey",
            3: "green",
            4: "red",
        }
        async with ctx.typing():

            for name, button_data in self.settings[ctx.guild.id]["buttons"].items():
                msg = _("Button Roles in {guild}\n").format(guild=ctx.guild.name)
                role = ctx.guild.get_role(button_data["role_id"])
                emoji = discord.PartialEmoji.from_str(button_data["emoji"])
                style = colour_index[button_data["style"]]
                msg += _(
                    "**Role:** {role}\n**Label:** {label}\n**Style:** {style}\n**Emoji:** {emoji}\n"
                ).format(role=role.mention, label=button_data["label"], style=style, emoji=emoji)
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
                        message = None
                    msg += _("[Button Message]({message})\n").format(
                        role=role.mention if role else _("None"),
                        emoji=emoji,
                        message=message if message else _("None"),
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
