from __future__ import annotations
import discord
import logging

from typing import Union, Optional, List

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


class SelectRoleOption(discord.SelectOption):
    def __init__(
        self,
        name: str,
        label: Optional[str],
        value: str,
        role_id: int,
        description: Optional[str],
        emoji: Optional[Union[discord.PartialEmoji, str]],
    ):
        super().__init__(label=label, emoji=emoji, description=description, value=value)
        self.role_id = role_id
        self.name = name


class SelectRole(discord.ui.Select):
    def __init__(
        self,
        name: str,
        custom_id: str,
        min_values: int,
        max_values: int,
        placeholder: Optional[str],
        options: List[SelectRoleOption],
    ):
        super().__init__(
            options=options,
            min_values=min_values,
            max_values=max_values,
            placeholder=placeholder,
            custom_id=custom_id,
        )
        self.name = name

    async def callback(self, interaction: discord.Interaction):
        log.debug("Receiving selection press")
        role_ids = []
        for option in self.values:
            if option.startswith("RTSelect"):
                role_ids.append(int(option.split("-")[-1]))

        guild = interaction.message.guild
        added_roles = []
        removed_roles = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role is None:
                continue
            if interaction.user.bot:
                    # how? This is what happens when you copy/paste code lol
                    ## even if it's your own code
                    ### Especially if it's your own code
                    continue
            config = self.view.cog.config
            if role not in interaction.user.roles:
                if not await config.role(role).selfassignable():
                    continue

                if await self.view.cog.check_guild_verification(interaction.user, guild):
                    log.debug("Ignoring user due to verification check.")
                    continue
                if getattr(interaction.user, "pending", False):
                    continue
                log.debug(f"Adding role to {interaction.user.name} in {guild}")
                await self.view.cog.give_roles(interaction.user, [role], _("Role Selection"))
                added_roles.append(role)
            elif role in interaction.user.roles:
                if not await config.role(role).selfremovable():
                    continue
                log.debug(f"Removing role from {interaction.user.name} in {guild}")
                await self.view.cog.remove_roles(interaction.user, [role], _("Role Selection"))
                removed_roles.append(role)
        msg = ""
        if added_roles:
            msg += _("I have given you the following roles: {roles}\n").format(
                roles=humanize_list([i.mention for i in added_roles])
            )
        if removed_roles:
            msg += _("I have removed the following roles from you: {roles}\n").format(
                roles=humanize_list([i.mention for i in removed_roles])
            )
        if msg:
            await interaction.response.send_message(msg, ephemeral=True)


class SelectRoleView(discord.ui.View):
    def __init__(self, cog: commands.Cog):
        self.cog = cog
        super().__init__(timeout=None)
        pass


class SelectOptionRoleConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> SelectRoleOption:
        async with ctx.cog.config.guild(ctx.guild).select_options() as select_options:
            log.debug(argument)
            if argument.lower() in select_options:
                select_data = select_options[argument.lower()]
                role_id = select_data["role_id"]
                emoji = select_data["emoji"]
                log.debug(emoji)
                if emoji and len(emoji) > 20:
                    emoji = discord.PartialEmoji.from_str(emoji)
                label = select_data["label"]
                description = select_data["description"]
                select_role = SelectRoleOption(
                    name=argument.lower(),
                    label=label,
                    value=f"RTSelect-{argument.lower()}-{role_id}",
                    role_id=role_id,
                    description=description,
                    emoji=emoji,
                )
                return select_role
            else:
                raise BadArgument(
                    _("Select Option with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )


class SelectRoleConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> SelectRole:
        async with ctx.cog.config.guild(ctx.guild).select_roles() as select_roles:
            log.debug(argument)
            if argument.lower() in select_roles:
                select_data = select_roles[argument.lower()]
                options = []
                all_option_data = await ctx.cog.config.guild(ctx.guild).select_options()
                for option_name in select_data["options"]:
                    try:
                        option_data = all_option_data[option_name]
                        role_id = option_data["role_id"]
                        description = option_data["description"]
                        emoji = option_data["emoji"]
                        if emoji is not None:
                            emoji = discord.PartialEmoji.from_str(emoji)
                        label = option_data["label"]
                        option = SelectRoleOption(
                            name=option_name,
                            label=label,
                            value=f"RTSelect-{option_name}-{role_id}",
                            role_id=role_id,
                            description=description,
                            emoji=emoji,
                        )
                        options.append(option)
                    except KeyError:
                        log.exception("Somehow this errored")
                        continue
                return SelectRole(
                    name=argument.lower(),
                    custom_id=f"RTSelect-{argument.lower()}-{ctx.guild.id}",
                    min_values=select_data["min_values"],
                    max_values=select_data["max_values"],
                    placeholder=select_data["placeholder"],
                    options=options,
                )
            else:
                raise BadArgument(
                    _("Select Option with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )


class RoleToolsSelect(RoleToolsMixin):
    """This class handles setting up Select view roles"""

    async def initialize_select(self):
        for guild_id, settings in self.settings.items():
            for select_name, select_data in settings["select_roles"].items():
                log.debug(f"Adding Option {select_name}")
                view = SelectRoleView(self)
                options = []
                for option_name in select_data["options"]:
                    try:
                        option_data = settings["select_options"][option_name]
                        role_id = option_data["role_id"]
                        description = option_data["description"]
                        emoji = option_data["emoji"]
                        if emoji is not None:
                            emoji = discord.PartialEmoji.from_str(option_data["emoji"])
                        label = option_data["label"]
                        option = SelectRoleOption(
                            name=option_name,
                            label=label,
                            value=f"RT-{option_name}-{role_id}",
                            role_id=role_id,
                            description=description,
                            emoji=emoji,
                        )
                        options.append(option)
                    except KeyError:
                        continue

                select = SelectRole(
                    name=select_name,
                    custom_id=f"RTSelect-{select_name}-{guild_id}",
                    min_values=select_data["min_values"],
                    max_values=select_data["max_values"],
                    placeholder=select_data["placeholder"],
                    options=options,
                )
                view.add_item(select)
                self.bot.add_view(view)
                self.views.append(view)

    @roletools.group(name="select")
    async def select(self, ctx: Context) -> None:
        """
        Setup role buttons
        """
        pass

    @select.command(name="create")
    async def create_select_view(
        self,
        ctx: Context,
        name: str,
        options: commands.Greedy[SelectOptionRoleConverter],
        min_values: Optional[int] = None,
        max_values: Optional[int] = None,
        *,
        placeholder: Optional[str] = None,
    ):
        """
        Create a select view

        `<name>` - The name for you to use when you send a message with this view.
        `[options]...` - The select view options you designated previously.
        `[min_values]` - The minimum number of items from this view to be selected.
        `[max_values]` - The maximum number of items from this view that can be selected.
        (If not provided this will default to the number of options provided.)
        `[placeholder]` - This is the default text on the view when no option has been
        chosen yet.
        Note: If no label and no emoji are provided the roles name will be used instead.
        This name will not update if the role name is changed.
        """
        if len(await self.config.guild(ctx.guild).select_options()) < 1:
            await ctx.send(
                _(
                    "You must setup some options first with `{prefix}roletools select options create`."
                ).format(prefix=ctx.clean_prefix)
            )
            return
        if len(options) < 1:
            await ctx.send(_("You have not provided any valid select views to use."))
            return
        if len(name) > 70:
            await ctx.send(_("The name should be less than 70 characters long."))
            return
        if min_values is None:
            min_values = 1
        if max_values is None:
            max_values = len(options)

        async with self.config.guild(ctx.guild).select_roles() as select_roles:
            messages = []
            if name.lower() in select_roles:
                messages = select_roles[name.lower()]["messages"]
            select_roles[name.lower()] = {
                "options": [o.name for o in options],
                "min_values": max(min(25, min_values), 0),
                "max_values": max(min(25, max_values), 0),
                "placeholder": placeholder,
                "name": name.lower(),
                "messages": messages,
            }
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["select_roles"][name.lower()] = {
                "options": [o.name for o in options],
                "min_values": max(min(25, min_values), 0),
                "max_values": max(min(25, max_values), 0),
                "placeholder": placeholder,
                "name": name.lower(),
                "messages": messages,
            }
        select_roles = SelectRole(
            name=name,
            custom_id=f"RTSelect-{name.lower()}-{ctx.guild.id}",
            min_values=min_values,
            max_values=max_values,
            options=options,
            placeholder=placeholder,
        )
        view = SelectRoleView(self)
        view.add_item(select_roles)
        self.views.append(view)
        msg = await ctx.send(_("Here is how your select view will look."), view=view)
        async with self.config.guild(ctx.guild).select_roles() as select_roles:
            select_roles[name.lower()]["messages"].append(f"{msg.channel.id}-{msg.id}")

    @select.command(name="delete", aliases=["del", "remove"])
    async def delete_select_view(self, ctx: Context, *, name: str):
        """
        Delete a saved select view.

        `<name>` - the name of the select view you want to delete.
        """
        async with self.config.guild(ctx.guild).select_roles() as select_roles:
            if name.lower() in select_roles:
                del select_roles[name.lower()]
                await ctx.send(_("Select Option `{name}` has been deleted.").format(name=name))
                try:
                    del self.settings[ctx.guild.id]["select_roles"][name.lower()]
                except KeyError:
                    pass
            else:
                await ctx.send(
                    _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                )

    @select.group(name="options", aliases=["option"])
    async def options(self, ctx: Context) -> None:
        """
        Commands for managing RoleTools select view options
        """
        pass

    @options.command(name="create", aliases=["add"])
    async def create_select_option(
        self,
        ctx: Context,
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
    ):
        """
        Create a select view option

        `<name>` - The name of the button for use later in setup.
        `<role>` - The role this button will assign or remove.
        `[label]` - The optional label for the option, max of 25 characters.
        `[description]` - The description for the option, max of 50 characters.
        `[emoji]` - The optional emoji used in the button.

        Note: If no label and no emoji are provided the roles name will be used instead.
        This name will not update if the role name is changed.
        """
        if " " in name:
            await ctx.send(_("There cannot be a space in the name of a select option."))
            return
        if len(name) > 70:
            await ctx.send(_("The name should be less than 70 characters long."))
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

        if label:
            label = label[:25]

        async with self.config.guild(ctx.guild).select_options() as select_options:
            select_options[name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "description": description[:50] if description else None,
                "name": name.lower(),
            }
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["select_options"][name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "description": description[:50] if description else None,
                "name": name.lower(),
            }
        async with self.config.role(role).select_options() as role_select:
            if name.lower() not in role_select:
                role_select.append(name.lower())
        option = SelectRoleOption(
            name=name.lower(),
            label=label,
            value=f"RTSelect-{name.lower()}-{role.id}",
            role_id=role.id,
            description=description[:50] if description else None,
            emoji=emoji_id,
        )
        select_roles = discord.ui.Select(
            min_values=1,
            max_values=1,
            options=[option],
        )
        view = SelectRoleView(self)
        view.add_item(select_roles)
        await ctx.send(_("Here is how your select option will look."), view=view)

    @options.command(name="delete", aliases=["del", "remove"])
    async def delete_select_option(self, ctx: Context, *, name: str):
        """
        Delete a saved button.

        `<name>` - the name of the button you want to delete.
        """
        async with self.config.guild(ctx.guild).select_options() as select_options:
            if name in select_options:
                role_id = select_options[name]["role_id"]
                del select_options[name]
                async with self.config.role_from_id(role_id).select_options() as role_select:
                    if name in role_select:
                        role_select.remove(name)
                await ctx.send(_("Select Option `{name}` has been deleted.").format(name=name))
            else:
                await ctx.send(
                    _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                )

    @select.command(name="send")
    async def send_select(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        views: commands.Greedy[SelectRoleConverter],
        *,
        message: str,
    ):
        """
        Send a select view to a specified channel for role assignment

        `<channel>` - the channel to send the button role buttons to.
        `[views]...` - The names of the select views you want included in the
        message up to a maximum of 5.
        `<message>` - The message to be included with the select view.
        """
        new_view = SelectRoleView(self)
        # for button in s:
        # new_view.add_item(button)
        # log.debug(options)
        if not views:
            await ctx.send(_("You need to specify at least one view setup previously."))
            return
        for select in views:
            new_view.add_item(select)
        self.views.append(new_view)
        msg = await channel.send(content=message, view=new_view)
        message_key = f"{msg.channel.id}-{msg.id}"
        async with self.config.guild(ctx.guild).select_roles() as select_roles:
            for select in views:
                select_roles[select.name.lower()]["messages"].append(message_key)
                self.settings[ctx.guild.id]["select_roles"][select.name.lower()][
                    "messages"
                ].append(message_key)
