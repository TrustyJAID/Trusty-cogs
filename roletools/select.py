from __future__ import annotations

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin
from .components import RoleToolsView, SelectRole, SelectRoleOption
from .converter import (
    RoleHierarchyConverter,
    SelectMenuFlags,
    SelectOptionFlags,
    SelectOptionRoleConverter,
)
from .menus import BaseMenu, SelectMenuPages, SelectOptionPages

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsSelect(RoleToolsMixin):
    """This class handles setting up Select menu roles"""

    async def initialize_select(self) -> None:
        for guild_id, settings in self.settings.items():
            if guild_id not in self.views:
                log.trace("Adding guild ID %s to views in selects", guild_id)
                self.views[guild_id] = {}
            for select_name, select_data in settings["select_menus"].items():
                log.verbose("Adding Option %s", select_name)
                options = []
                disabled = []
                for option_name in select_data["options"]:
                    try:
                        option_data = settings["select_options"][option_name]
                        role_id = option_data["role_id"]
                        description = option_data["description"]
                        emoji = option_data["emoji"]
                        if emoji is not None:
                            emoji = discord.PartialEmoji.from_str(option_data["emoji"])
                        label = option_data["label"]
                        if not label:
                            label = "\u200b"
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
                        log.info(
                            "Select Option named %s no longer exists, adding to select menus disalbe list.",
                            option_name,
                        )
                        disabled.append(option_name)

                guild = self.bot.get_guild(guild_id)
                for message_id in set(select_data.get("messages", [])):
                    # we need a new instance of this object per message
                    select = SelectRole(
                        name=select_name,
                        custom_id=f"RTSelect-{select_name}-{guild_id}",
                        min_values=select_data["min_values"],
                        max_values=select_data["max_values"],
                        placeholder=select_data["placeholder"],
                        options=options,
                        disabled=disabled,
                    )
                    if guild is not None:
                        select.update_options(guild)
                    if message_id not in self.views[guild_id]:
                        log.trace("Creating view for select %s", select_name)
                        self.views[guild_id][message_id] = RoleToolsView(self)
                    if select.custom_id not in {
                        c.custom_id for c in self.views[guild_id][message_id].children
                    }:
                        try:
                            self.views[guild_id][message_id].add_item(select)
                        except ValueError:
                            log.error(
                                "There was an error adding select %s on message https://discord.com/channels/%s/%s",
                                select.name,
                                guild_id,
                                message_id.replace("-", "/"),
                            )

    @roletools.group(name="select", aliases=["selects"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def select(self, ctx: Context) -> None:
        """
        Setup role select menus
        """

    @select.command(name="create", usage="<name> [options...] [extras]")
    async def create_select_menu(
        self,
        ctx: Context,
        name: str,
        options: commands.Greedy[SelectOptionRoleConverter],
        *,
        extras: SelectMenuFlags,
    ) -> None:
        """
        Create a select menu

        - `<name>` - The name for you to use when you send a message with this menu.
        - `[options]...` - The select menu options you designated previously.
        - `[extras]`
         - `min:` - The minimum number of items from this menu to be selected.
         - `max:` - The maximum number of items from this menu that can be selected.
         (If not provided this will default to the number of options provided.)
         - `placeholder:` - This is the default text on the menu when no option has been
        chosen yet.
        Example:
            `[p]roletools select create myrolemenu role1 role2 role3 placeholder: Pick your role!`
        """
        await ctx.typing()
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        if " " in name:
            msg = _("There cannot be a space in the name of a select menu.")
            await ctx.send(msg)
            return
        if len(await self.config.guild(ctx.guild).select_options()) < 1:
            msg = _("You must setup some options first with " "`{prefix}{command}`.").format(
                prefix=ctx.clean_prefix, command=self.create_select_option.qualified_name
            )
            await ctx.send(msg)
            return
        if len(options) < 1:
            msg = _("You have not provided any valid select options to use.")
            await ctx.send(msg)
            return
        if len(name) > 70:
            msg = _("The name should be less than 70 characters long.")
            await ctx.send(msg)
            return
        min_values = extras.min_values
        max_values = extras.max_values
        if min_values is None:
            min_values = 1
        if max_values is None:
            max_values = len(options)
        messages = []
        custom_id = f"RTSelect-{name.lower()}-{ctx.guild.id}"
        select_menu_settings = {
            "options": [o.name for o in options],
            "min_values": max(min(25, min_values), 0),
            "max_values": max(min(25, max_values), 0),
            "placeholder": extras.placeholder,
            "name": name.lower(),
            "messages": messages,
        }

        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            if name.lower() in select_menus:
                select_menu_settings["messages"] = select_menus[name.lower()]["messages"]
            select_menus[name.lower()] = select_menu_settings
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        self.settings[ctx.guild.id]["select_menus"][name.lower()] = select_menu_settings
        select_menus = SelectRole(
            name=name,
            custom_id=custom_id,
            min_values=min_values,
            max_values=max_values,
            options=options,
            placeholder=extras.placeholder,
        )
        for message_id in select_menu_settings["messages"]:
            # fix old menus with the new one when interacted with
            replacement_view = self.views.get(ctx.guild.id, {}).get(message_id, None)
            if replacement_view is None:
                continue
            for item in replacement_view.children:
                if item.custom_id == custom_id:
                    replacement_view.remove_item(item)
            replacement_view.add_item(select_menus)

        select_menus.update_options(ctx.guild)
        view = RoleToolsView(self, timeout=180.0)
        view.add_item(select_menus)

        msg_str = _("Here is how your select menu will look.")
        msg = await ctx.send(msg_str, view=view)

    @select.command(name="delete", aliases=["del", "remove"])
    async def delete_select_menu(self, ctx: Context, *, name: str) -> None:
        """
        Delete a saved select menu.

        `<name>` - the name of the select menu you want to delete.
        """
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        async with self.config.guild(ctx.guild).select_menus() as select_menus:
            if name.lower() in select_menus:
                for view in self.views[ctx.guild.id].values():
                    children_names = [i.name for i in view.children]
                    if all(
                        i in children_names for i in select_menus[name.lower()].get("options", [])
                    ):
                        view.disabled = True

                del select_menus[name.lower()]
                msg = _("Select Option `{name}` has been deleted.").format(name=name)
                await ctx.send(msg)
                try:
                    del self.settings[ctx.guild.id]["select_menus"][name.lower()]
                except KeyError:
                    pass
            else:
                msg = _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                await ctx.send(msg)

    @select.command(name="createoption", aliases=["addoption"], usage="<name> <role> [extras]")
    async def create_select_option(
        self,
        ctx: Context,
        name: str,
        role: RoleHierarchyConverter,
        *,
        extras: SelectOptionFlags,
    ) -> None:
        """
        Create a select menu option

        - `<name>` - The name of the select option for use later in setup.
        - `<role>` - The role this select option will assign or remove.
        - `[extras]`
         - `label:` - The optional label for the option, max of 25 characters.
         - `description:` - The description for the option, max of 50 characters.
         - `emoji:` - The optional emoji used in the select option.

        Note: If no label and no emoji are provided the roles name will be used instead.
        This name will not update if the role name is changed.

        Example:
            `[p]roletools select createoption role1 @role label: Super Fun Role emoji: 😀`
        """
        if " " in name:
            msg = _("There cannot be a space in the name of a select option.")
            await ctx.send(msg)
            return
        if len(name) > 70:
            msg = _("The name should be less than 70 characters long.")
            await ctx.send(msg)
            return
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
        label = extras.label or "\u200b"
        # ensure that there's at least an emoji on this
        if not emoji_id and not extras.label:
            label = f"@{role.name}"

        option_settings = {
            "role_id": role.id,
            "label": label,
            "emoji": emoji_id,
            "description": extras.description,
            "name": name.lower(),
        }

        async with self.config.guild(ctx.guild).select_options() as select_options:
            select_options[name.lower()] = option_settings
        if ctx.guild.id not in self.settings:
            self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
        self.settings[ctx.guild.id]["select_options"][name.lower()] = option_settings
        async with self.config.role(role).select_options() as role_select:
            if name.lower() not in role_select:
                role_select.append(name.lower())
        option = SelectRoleOption(
            name=name.lower(),
            label=label,
            value=f"RTSelect-{name.lower()}-{role.id}",
            role_id=role.id,
            description=extras.description,
            emoji=emoji_id,
        )
        select_menus = discord.ui.Select(
            min_values=1,
            max_values=1,
            options=[option],
        )

        async def test_callback(interaction: discord.Interaction):
            await interaction.response.send_message(
                _("This is an example select option and does not actually work."), ephemeral=True
            )

        select_menus.callback = test_callback

        view = discord.ui.View()  # RoleToolsView(self)
        view.add_item(select_menus)
        msg = _("Here is how your select option will look.")
        await ctx.send(msg, view=view)
        await self.confirm_selfassignable(ctx, [role])

    @select.command(name="deleteoption", aliases=["deloption", "removeoption", "remoption"])
    async def delete_select_option(self, ctx: Context, *, name: str) -> None:
        """
        Delete a saved option.

        `<name>` - the name of the select option you want to delete.
        """
        if ctx.guild.id not in self.views:
            self.views[ctx.guild.id] = {}
        async with self.config.guild(ctx.guild).select_options() as select_options:
            if name in select_options:
                role_id = select_options[name]["role_id"]
                custom_id = f"RTSelect-{name.lower()}-{role_id}"
                for view in self.views[ctx.guild.id].values():
                    for child in view.children:
                        if not isinstance(child, SelectRole):
                            continue
                        options = [i.value for i in child.options]
                        if custom_id in options:
                            child.disabled_options.append(name.lower())
                            # log.debug(f"Adding {custom_id} to view")
                if name in self.settings.get(ctx.guild.id, {}).get("select_options", {}):
                    del self.settings[ctx.guild.id]["select_options"][name]
                del select_options[name]
                async with self.config.role_from_id(role_id).select_options() as role_select:
                    if name in role_select:
                        role_select.remove(name)
                msg = _("Select Option `{name}` has been deleted.").format(name=name)
                await ctx.send(msg)
            else:
                msg = _("Select Option `{name}` doesn't appear to exist.").format(name=name)
                await ctx.send(msg)

    @select.command(name="view", aliases=["list"])
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True)
    async def select_menus_view(self, ctx: Context) -> None:
        """
        View current select menus setup for role assign in this server.
        """
        no_pages = _("There are no select menus in this server.")
        if ctx.guild.id not in self.settings:
            await ctx.send(no_pages)
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
            for messages in set(select_data["messages"]):
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
        if not pages:
            await ctx.send(no_pages)
            return
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
    async def select_options_view(self, ctx: Context) -> None:
        """
        View current select menus setup for role assign in this server.
        """
        no_options = _("There are no select menu options in this server.")
        if ctx.guild.id not in self.settings:
            await ctx.send(no_options)
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
        if not pages:
            await ctx.send(no_options)
            return
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

    @select.command(name="cleanup")
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True)
    async def select_cleanup(self, ctx: commands.Context):
        """
        Check each select menu that has registered a message still exists and remove buttons with
        missing messages.

        # Note: This will also potentially cause problems if the button exists in a thread
        it will not be found if the thread is archived and subsequently removed.
        """
        guild = ctx.guild
        async with ctx.typing():
            async with self.config.guild(guild).select_menus() as select_menus:
                for name, select_menu_settings in (
                    self.settings[guild.id].get("select_menus", {}).items()
                ):
                    messages = set(select_menu_settings["messages"])
                    for message_ids in select_menu_settings["messages"]:
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
                                "Removing %s message reference on %s select menu %s since it can't be found.",
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
                    select_menus[name]["messages"] = list(messages)
                    self.settings[guild.id]["select_menus"][name]["messages"] = list(messages)
        await ctx.send(_("I am finished deleting old select menu message references."))
