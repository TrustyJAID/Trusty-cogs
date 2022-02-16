from __future__ import annotations

import logging
from typing import List, Optional, Union

import discord
from discord import Interaction
from discord.ext.commands import BadArgument, Converter
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin, roletools
from .converter import RoleHierarchyConverter
from .menus import BaseMenu, SelectMenuPages, SelectOptionPages

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
                # # even if it's your own code
                # ## Especially if it's your own code
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
        async with ctx.cog.config.guild(ctx.guild).select_menus() as select_menus:
            log.debug(argument)
            if argument.lower() in select_menus:
                select_data = select_menus[argument.lower()]
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
    """This class handles setting up Select menu roles"""

    async def initialize_select(self) -> None:
        for guild_id, settings in self.settings.items():
            for select_name, select_data in settings["select_menus"].items():
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

    async def select_option_autocomplete(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).select_options()
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

    async def select_menu_autocomplete(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        select_options = await self.config.guild(guild).select_menus()
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

    @roletools.group(name="select")
    @commands.admin_or_permissions(manage_roles=True)
    async def select(self, ctx: Union[Context, Interaction]) -> None:
        """
        Setup role select menus
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "create": self.create_select_menu,
                "view": self.select_menus_view,
                "delete": self.delete_select_menu,
                "edit": self.edit_with_select,
                "send": self.send_select,
                "viewoptions": self.select_options_view,
                "createoption": self.create_select_option,
                "deleteoption": self.delete_select_option,
            }
            options = ctx.data["options"][0]["options"][0]["options"]
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            kwargs = {}
            if ctx.is_autocomplete and option == "create":
                new_options = await self.select_option_autocomplete(ctx)
                if len(new_options) == 0:
                    new_options.append(
                        {
                            "name": "You need to create some options first.",
                            "value": "This option does not exist",
                        }
                    )
                await ctx.response.autocomplete(new_options[:25])
                return
            if ctx.is_autocomplete and option in ["send", "edit", "delete"]:
                new_options = await self.select_menu_autocomplete(ctx)
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

    @select.command(name="create")
    async def create_select_menu(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        options: commands.Greedy[SelectOptionRoleConverter],
        min_values: Optional[int] = None,
        max_values: Optional[int] = None,
        *,
        placeholder: Optional[str] = None,
    ) -> None:
        """
        Create a select menu

        `<name>` - The name for you to use when you send a message with this menu.
        `[options]...` - The select menu options you designated previously.
        `[min_values]` - The minimum number of items from this menu to be selected.
        `[max_values]` - The maximum number of items from this menu that can be selected.
        (If not provided this will default to the number of options provided.)
        `[placeholder]` - This is the default text on the menu when no option has been
        chosen yet.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        if " " in name:
            msg = _("There cannot be a space in the name of a select menu.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if len(await self.config.guild(ctx.guild).select_options()) < 1:
            msg = _(
                "You must setup some options first with "
                "`{prefix}roletools select options create`."
            ).format(prefix=ctx.clean_prefix)
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if len(options) < 1:
            msg = _("You have not provided any valid select options to use.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if len(name) > 70:
            msg = _("The name should be less than 70 characters long.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if min_values is None:
            min_values = 1
        if max_values is None:
            max_values = len(options)

        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            messages = []
            if name.lower() in select_menus:
                messages = select_menus[name.lower()]["messages"]
            select_menus[name.lower()] = {
                "options": [o.name for o in options],
                "min_values": max(min(25, min_values), 0),
                "max_values": max(min(25, max_values), 0),
                "placeholder": placeholder,
                "name": name.lower(),
                "messages": messages,
            }
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["select_menus"][name.lower()] = {
                "options": [o.name for o in options],
                "min_values": max(min(25, min_values), 0),
                "max_values": max(min(25, max_values), 0),
                "placeholder": placeholder,
                "name": name.lower(),
                "messages": messages,
            }
        select_menus = SelectRole(
            name=name,
            custom_id=f"RTSelect-{name.lower()}-{ctx.guild.id}",
            min_values=min_values,
            max_values=max_values,
            options=options,
            placeholder=placeholder,
        )
        view = SelectRoleView(self)
        view.add_item(select_menus)
        self.views.append(view)
        msg_str = _("Here is how your select menu will look.")
        if is_slash:
            msg = await ctx.send(msg_str, view=view)
        else:
            msg = await ctx.followup.send(msg_str, view=view)
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            select_menus[name.lower()]["messages"].append(f"{msg.channel.id}-{msg.id}")

    @select.command(name="delete", aliases=["del", "remove"])
    async def delete_select_menu(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        """
        Delete a saved select menu.

        `<name>` - the name of the select menu you want to delete.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            if name.lower() in select_menus:
                del select_menus[name.lower()]
                msg = _("Select Option `{name}` has been deleted.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
                try:
                    del self.settings[ctx.guild.id]["select_menus"][name.lower()]
                except KeyError:
                    pass
            else:
                msg = _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)

    @select.command(name="createoption", aliases=["addoption"])
    async def create_select_option(
        self,
        ctx: Union[Context, Interaction],
        name: str,
        role: RoleHierarchyConverter,
        label: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[Union[discord.PartialEmoji, str]] = None,
    ) -> None:
        """
        Create a select menu option

        `<name>` - The name of the button for use later in setup.
        `<role>` - The role this button will assign or remove.
        `[label]` - The optional label for the option, max of 25 characters.
        `[description]` - The description for the option, max of 50 characters.
        `[emoji]` - The optional emoji used in the button.

        Note: If no label and no emoji are provided the roles name will be used instead.
        This name will not update if the role name is changed.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            try:
                role = await RoleHierarchyConverter().convert(ctx, role.mention)
            except commands.BadArgument as e:
                await ctx.response.send_message(e, ephemeral=True)
                return
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        if " " in name:
            msg = _("There cannot be a space in the name of a select option.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if len(name) > 70:
            msg = _("The name should be less than 70 characters long.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
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
            label = label[:100]

        async with self.config.guild(ctx.guild).select_options() as select_options:
            select_options[name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "description": description[:100] if description else None,
                "name": name.lower(),
            }
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["select_options"][name.lower()] = {
                "role_id": role.id,
                "label": label,
                "emoji": emoji_id,
                "description": description[:100] if description else None,
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
            description=description[:100] if description else None,
            emoji=emoji_id,
        )
        select_menus = discord.ui.Select(
            min_values=1,
            max_values=1,
            options=[option],
        )
        view = SelectRoleView(self)
        view.add_item(select_menus)
        msg = _("Here is how your select option will look.")
        if is_slash:
            await ctx.followup.send(msg, view=view)
        else:
            await ctx.send(msg, view=view)

    @select.command(name="deleteoption", aliases=["deloption", "removeoption", "remoption"])
    async def delete_select_option(self, ctx: Union[Context, Interaction], *, name: str) -> None:
        """
        Delete a saved option.

        `<name>` - the name of the button you want to delete.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        async with self.config.guild(ctx.guild).select_options() as select_options:
            if name in select_options:
                role_id = select_options[name]["role_id"]
                del select_options[name]
                async with self.config.role_from_id(role_id).select_options() as role_select:
                    if name in role_select:
                        role_select.remove(name)
                msg = _("Select Option `{name}` has been deleted.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
            else:
                msg = _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)

    @select.command(name="send")
    async def send_select(
        self,
        ctx: Union[Context, Interaction],
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
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()
            _menus = []
            for menu in menus.split(" "):
                if menu:
                    _menus.append(await SelectRoleConverter().convert(fake_ctx, menu))
            menus = _menus

        new_view = SelectRoleView(self)
        # for button in s:
        # new_view.add_item(button)
        # log.debug(options)
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
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
        if is_slash:
            await ctx.followup.send(_("Message sent."))

    @select.command(name="edit")
    async def edit_with_select(
        self,
        ctx: Union[Context, Interaction],
        message: discord.Message,
        menus: commands.Greedy[SelectRoleConverter],
    ) -> None:
        """
        Edit a bots message to include Role Buttons

        `<message>` - The existing message to add role buttons to. Must be a bots message.
        `[menus]...` - The names of the select menus you want to include up to a maximum of 5.
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
            _menus = []
            for menu in menus.split(" "):
                if menu:
                    _menus.append(await SelectRoleConverter().convert(fake_ctx, menu))
            menus = _menus

        if message.author.id != ctx.guild.me.id:
            msg = _("I cannot edit someone elses message to include buttons.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        if not menus:
            msg = _("You need to specify at least one menu setup previously.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
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
        if is_slash:
            await ctx.followup.send(_("Message edited."))

    @select.command(name="view", aliases=["list"])
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True)
    async def select_menus_view(self, ctx: Union[Context, Interaction]) -> None:
        """
        View current select menus setup for role assign in this server.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()

        if ctx.guild.id not in self.settings:
            msg = _("There are no select menus in this server.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        pages = []
        for name, select_data in self.settings[ctx.guild.id]["select_menus"].items():
            msg = _("Select Menus in {guild}\n").format(guild=ctx.guild.name)
            options = select_data["options"]
            min_values = select_data["min_values"]
            max_values = select_data["max_values"]
            placeholder = select_data["placeholder"]

            msg += _(
                "**Name:** {name}\n**Options:** {options}\n**Placeholder:** {placeholder}\n"
                "**Min Values:** {min_values}\n**Max Values:** {max_values}\n"
            ).format(
                name=name,
                options=humanize_list(options),
                placeholder=placeholder,
                min_values=min_values,
                max_values=max_values,
            )
            for messages in select_data["messages"]:
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
                msg += _("[Menu Message]({message})\n").format(
                    message=message,
                )
            pages.append(msg)
        await BaseMenu(
            source=SelectMenuPages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @select.command(name="viewoptions", aliases=["listoptions", "viewoption", "listoption"])
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True)
    async def select_options_view(self, ctx: Union[Context, Interaction]) -> None:
        """
        View current select menus setup for role assign in this server.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            await ctx.response.defer()

        if ctx.guild.id not in self.settings:
            msg = _("There are no select menu options in this server.")
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
            return
        pages = []
        for name, select_data in self.settings[ctx.guild.id]["select_options"].items():
            msg = _("Select Options in {guild}\n").format(guild=ctx.guild.name)
            role = ctx.guild.get_role(select_data["role_id"])
            label = select_data["label"]
            emoji = select_data["emoji"]
            if emoji is not None:
                emoji = discord.PartialEmoji.from_str(emoji)
            description = select_data["description"]

            msg += _(
                "**Name:** {name}\n**Role:** {role}\n**Emoji:** {emoji}\n"
                "**Label:** {label}\n**description:** {description}\n"
            ).format(
                name=name,
                role=role.mention if role else _("Missing Role"),
                emoji=emoji,
                label=label,
                description=description,
            )
            pages.append(msg)
        await BaseMenu(
            source=SelectOptionPages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)
