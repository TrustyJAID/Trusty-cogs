from __future__ import annotations

from typing import Any, List, Optional

import discord
from red_commons.logging import getLogger

# from discord.ext.commands.errors import BadArgument
from redbot.core import bank
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.vendored.discord.ext import menus

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class ReactRolePages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.guild.me).embed_links:
            em = discord.Embed(description=page, colour=await menu.bot.get_embed_colour(menu.ctx))
            em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class ButtonRolePages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.guild.me).embed_links:
            if len(page) > 4000:
                em = discord.Embed(colour=await menu.bot.get_embed_colour(menu.ctx))
                count = 0
                for pages in pagify(page, page_length=1024):
                    if count < 4:
                        em.description += pages
                    else:
                        em.add_field(name=_("Button Role Info Continued"), value=pages)
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            else:
                em = discord.Embed(
                    description=page, colour=await menu.bot.get_embed_colour(menu.ctx)
                )
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class SelectOptionPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.guild.me).embed_links:
            if len(page) > 4000:
                em = discord.Embed(colour=await menu.bot.get_embed_colour(menu.ctx))
                count = 0
                for pages in pagify(page, page_length=1024):
                    if count < 4:
                        em.description += pages
                    else:
                        em.add_field(name=_("Select Option Info Continued"), value=pages)
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            else:
                em = discord.Embed(
                    description=page, colour=await menu.bot.get_embed_colour(menu.ctx)
                )
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class SelectMenuPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.guild.me).embed_links:
            if len(page) > 4000:
                em = discord.Embed(colour=await menu.bot.get_embed_colour(menu.ctx))
                count = 0
                for pages in pagify(page, page_length=1024):
                    if count < 4:
                        em.description += pages
                    else:
                        em.add_field(name=_("Select Menu Info Continued"), value=pages)
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            else:
                em = discord.Embed(
                    description=page, colour=await menu.bot.get_embed_colour(menu.ctx)
                )
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class RoleToolsSelectOption(discord.ui.RoleSelect):
    def __init__(self, placeholder: str = _("Select a role")):
        super().__init__(min_values=1, max_values=1, placeholder=placeholder)
        self.current_role: discord.Role

    async def callback(self, interaction: discord.Interaction):
        index = interaction.guild.roles.index(self.values[0])
        await self.view.show_checked_page(index, interaction)


class StickyToggleButton(discord.ui.Button):
    def __init__(
        self,
    ):
        super().__init__(style=discord.ButtonStyle.green, label=_("Sticky"))
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("RoleTools")
        current = await cog.config.role(self.view._source.current_role).sticky()
        await cog.config.role(self.view._source.current_role).sticky.set(not current)
        await self.view.show_page(self.view.current_page, interaction)


class AutoToggleButton(discord.ui.Button):
    def __init__(
        self,
    ):
        super().__init__(style=discord.ButtonStyle.green, label=_("Auto"))
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("RoleTools")
        current = await cog.config.role(self.view._source.current_role).auto()
        await cog.config.role(self.view._source.current_role).auto.set(not current)
        await self.view.show_page(self.view.current_page, interaction)


class SelfAddToggleButton(discord.ui.Button):
    def __init__(
        self,
    ):
        super().__init__(style=discord.ButtonStyle.green, label=_("Selfassignable"))
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("RoleTools")
        current = await cog.config.role(self.view._source.current_role).selfassignable()
        await cog.config.role(self.view._source.current_role).selfassignable.set(not current)
        await self.view.show_page(self.view.current_page, interaction)


class SelfRemToggleButton(discord.ui.Button):
    def __init__(
        self,
    ):
        super().__init__(style=discord.ButtonStyle.green, label=_("Selfremovable"))
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("RoleTools")
        current = await cog.config.role(self.view._source.current_role).selfremovable()
        await cog.config.role(self.view._source.current_role).selfremovable.set(not current)
        await self.view.show_page(self.view.current_page, interaction)


class RolePages(menus.ListPageSource):
    def __init__(self, roles: List[discord.Role]):
        super().__init__(roles, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: BaseMenu, role: discord.Role):
        self.current_role = role
        role_settings = await menu.cog.config.role(role).all()
        menu.update_buttons(role_settings)
        msg = _("Role Settings for {role}\n".format(role=role.name))
        jump_url = "https://discord.com/channels/{guild}/{channel}/{message}"
        em = discord.Embed(title=msg, colour=role.colour)
        mod_roles = await menu.bot.get_mod_roles(menu.ctx.guild)
        admin_roles = await menu.bot.get_admin_roles(menu.ctx.guild)
        required_roles = [menu.ctx.guild.get_role(i) for i in role_settings["required"]]
        exclusive_roles = [menu.ctx.guild.get_role(i) for i in role_settings["exclusive_to"]]
        inclusive_roles = [menu.ctx.guild.get_role(i) for i in role_settings["inclusive_with"]]
        permissions = humanize_list(
            [perm.replace("_", " ").title() for perm, value in role.permissions if value]
        )
        buttons = humanize_list(role_settings["buttons"])
        select_options = humanize_list(role_settings["select_options"])
        require_any = role_settings["require_any"]
        settings = _(
            "{role}\n```md\n"
            "# ID:           {role_id}\n"
            "Colour          {colour}\n"
            "Members         {members}\n"
            "Assignable      {assignable}\n"
            "Mentionable     {mentionable}\n"
            "Position        {position}\n"
            "Hoisted         {hoisted}\n"
            "# RoleTools settings\n"
            "Sticky          {sticky}\n"
            "Auto            {auto}\n"
            "Selfassignable  {selfassign}\n"
            "Selfremovable   {selfrem}\n"
            "# Core Bot settings\n"
            "Mod             {mod}\n"
            "Admin           {admin}\n\n"
            "```"
        ).format(
            role=role.mention,
            role_id=role.id,
            members=len(role.members),
            assignable=role.is_assignable(),
            mentionable=role.mentionable,
            position=role.position,
            hoisted=role.hoist,
            sticky=role_settings["sticky"],
            auto=role_settings["auto"],
            selfassign=role_settings["selfassignable"],
            selfrem=role_settings["selfremovable"],
            colour=str(role.colour),
            mod=role in mod_roles,
            admin=role in admin_roles,
        )
        settings += _("**Created:** {created_at}\n").format(
            created_at=discord.utils.format_dt(role.created_at)
        )
        if cost := role_settings.get("cost"):
            currency_name = await bank.get_currency_name(menu.ctx.guild)
            settings += _("**Cost:** {cost} {currency_name}\n").format(
                cost=cost, currency_name=currency_name
            )
        if buttons:
            settings += _("**Buttons:** {button_names}\n").format(button_names=buttons)
        if select_options:
            settings += _("**Select Options:** {select_names}\n").format(
                select_names=select_options
            )
        if permissions:
            settings += _("**Permissions:** {permissions}\n").format(permissions=permissions)
        if role.managed:
            if getattr(role, "is_bot_managed", lambda: False)():
                bot = role.guild.get_member(role.tags.bot_id)
                settings += _("Bot Role: {bot}").format(bot=bot.mention)
            elif getattr(role, "is_premium_subscriber", lambda: False)():
                settings += _("**Premium Role:** True\n")
            else:
                settings += _("**Managed Role:** True\n")
        if inclusive_roles:
            settings += _("**Inclusive with:** {inclusive}\n").format(
                inclusive=humanize_list([r.mention for r in inclusive_roles if r])
            )
        if exclusive_roles:
            settings += _("**Exclusive to:** {inclusive}\n").format(
                inclusive=humanize_list([r.mention for r in exclusive_roles if r])
            )
        if required_roles:
            settings += _("**Requires{any_of}:** {inclusive}\n").format(
                inclusive=humanize_list([r.mention for r in required_roles if r]),
                any_of="" if not require_any else _(" any of"),
            )
        if role_settings["reactions"]:
            settings += _("**Reaction Roles**\n")
        for reaction in role_settings["reactions"]:
            channel, message, emoji = reaction.split("-")
            if emoji.isdigit():
                emoji = menu.bot.get_emoji(int(emoji))
            if not emoji:
                emoji = _("Emoji from another server")
            link = jump_url.format(guild=menu.ctx.guild.id, channel=channel, message=message)
            settings += _("{emoji} on [message]({link})\n").format(emoji=emoji, link=link)
        embeds = [e for e in pagify(settings, page_length=5500)]
        if len(embeds) > 1:
            command = f"`{menu.ctx.clean_prefix}roletools reactionroles`"
            settings = _("{settings}\nPlease see {command} to see full details").format(
                settings=embeds[0], command=command
            )
        pages = pagify(settings, page_length=1024)
        em.description = ""
        for index, page in enumerate(pages):
            if index < 2:
                # em.add_field(name=_("Role settings for {role}".format(role=role.name)), value=page)
                em.description += page
            else:
                em.add_field(
                    name=_("Role settings for {role} (continued)").format(role=role.name),
                    value=page,
                )
        if role.display_icon:
            if isinstance(role.display_icon, discord.Asset):
                em.set_thumbnail(url=role.display_icon)
            else:
                cdn_fmt = " https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codepoint:x}.png"
                url = cdn_fmt.format(codepoint=ord(str(role.display_icon)))
                log.verbose("RolePages role.display_icon: %s", role.display_icon)
                em.set_thumbnail(url=url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.cog = cog
        self.bot = None
        self.message = message
        self._source = source
        self.ctx = None
        self.author: Optional[discord.Member] = None
        self.current_page = kwargs.get("page_start", 0)
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        if isinstance(source, RolePages):
            self.select_view = RoleToolsSelectOption()
            self.add_item(self.select_view)
            self.auto = AutoToggleButton()
            self.add_item(self.auto)
            self.sticky = StickyToggleButton()
            self.add_item(self.sticky)
            self.selfassignable = SelfAddToggleButton()
            self.add_item(self.selfassignable)
            self.selfremovable = SelfRemToggleButton()
            self.add_item(self.selfremovable)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    def update_buttons(self, data: dict):
        buttons = {
            "sticky": self.sticky,
            "auto": self.auto,
            "selfassignable": self.selfassignable,
            "selfremovable": self.selfremovable,
        }
        for key, button in buttons.items():
            if key in data:
                if data[key]:
                    button.style = discord.ButtonStyle.green
                else:
                    button.style = discord.ButtonStyle.red
            if self.author is not None:
                if self.author.id == self.ctx.guild.owner_id:
                    button.disabled = False
                else:
                    button.disabled = (
                        self.author.guild_permissions.manage_roles
                        and self.source.current_role >= self.author.top_role
                    )
            button.disabled |= not self.source.current_role.is_assignable()

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.bot = self.cog.bot
        self.author = ctx.author
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.ctx = ctx
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id not in (
            *interaction.client.owner_ids,
            getattr(self.author, "id", None),
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class ConfirmView(discord.ui.View):
    """
    This is just a copy of my version from Red to be removed later possibly
    https://github.com/Cog-Creators/Red-DiscordBot/pull/6176
    """

    def __init__(
        self,
        author: Optional[discord.abc.User] = None,
        *,
        timeout: float = 180.0,
        disable_buttons: bool = False,
    ):
        if timeout is None:
            raise TypeError("This view should not be used as a persistent view.")
        super().__init__(timeout=timeout)
        self.result: Optional[bool] = None
        self.author: Optional[discord.abc.User] = author
        self.message: Optional[discord.Message] = None
        self.disable_buttons = disable_buttons

    async def on_timeout(self):
        if self.message is None:
            # we can't do anything here if message is none
            return

        if self.disable_buttons:
            self.confirm_button.disabled = True
            self.dismiss_button.disabled = True
            await self.message.edit(view=self)
        else:
            await self.message.edit(view=None)

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.secondary)
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        # respond to the interaction so the user does not see "interaction failed".
        await interaction.response.defer()
        # call `on_timeout` explicitly here since it's not called when `stop()` is called.
        await self.on_timeout()

    async def interaction_check(self, interaction: discord.Interaction):
        if self.message is None:
            self.message = interaction.message
        if self.author and interaction.user.id != self.author.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
