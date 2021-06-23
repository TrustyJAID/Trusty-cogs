from __future__ import annotations

import logging
from typing import Any, List, Optional

import discord

# from discord.ext.commands.errors import BadArgument
from redbot.core import bank
from redbot.core.commands import commands
from redbot.core.i18n import Translator

from redbot.core.utils.chat_formatting import pagify, humanize_list
from redbot.vendored.discord.ext import menus


log = logging.getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class ReactRolePages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        if menu.ctx.channel.permissions_for(menu.ctx.me).embed_links:
            em = discord.Embed(
                description=page, colour=await menu.ctx.bot.get_embed_colour(menu.ctx)
            )
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
        if menu.ctx.channel.permissions_for(menu.ctx.me).embed_links:
            if len(page) > 2000:
                em = discord.Embed(colour=await menu.ctx.bot.get_embed_colour(menu.ctx))
                count = 0
                for pages in pagify(page, page_length=1024):
                    if count < 2:
                        em.description += pages
                    else:
                        em.add_field(name=_("Button Role Info Continued"), value=pages)
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            else:
                em = discord.Embed(
                    description=page, colour=await menu.ctx.bot.get_embed_colour(menu.ctx)
                )
                em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
            return em
        else:
            return page


class RolePages(menus.ListPageSource):
    def __init__(self, roles: List[discord.Role]):
        super().__init__(roles, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, role: discord.Role):
        role_settings = await menu.cog.config.role(role).all()
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
        settings = _(
            "{role}\n```md\n"
            "# ID:           {role_id}\n"
            "Colour          {colour}\n"
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
            sticky=role_settings["sticky"],
            auto=role_settings["auto"],
            selfassign=role_settings["selfassignable"],
            selfrem=role_settings["selfremovable"],
            colour=str(role.colour),
            mod=role in mod_roles,
            admin=role in admin_roles,
        )
        if cost := role_settings.get("cost"):
            currency_name = await bank.get_currency_name(menu.ctx.guild)
            settings += _("**Cost:** {cost} {currency_name}\n").format(
                cost=cost, currency_name=currency_name
            )
        if buttons:
            settings += _("**Buttons:** {button_names}").format(button_names=buttons)
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
            settings += _("**Requires:** {inclusive}\n").format(
                inclusive=humanize_list([r.mention for r in required_roles if r])
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
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
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
        self.current_page = kwargs.get("page_start", 0)

    @property
    def source(self):
        return self._source

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.bot = ctx.bot
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx, ctx.channel)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.ctx = ctx
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await channel.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs)

    async def show_checked_page(self, page_number: int) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number)
            elif page_number >= max_pages:
                await self.show_page(0)
            elif page_number < 0:
                await self.show_page(max_pages - 1)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id not in (*self.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages == 1

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_first_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the first page"""
        await self.show_page(0)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_previous_page(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_next_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the next page"""
        log.debug(f"Changing to page {self.current_page + 1}")
        await self.show_checked_page(self.current_page + 1)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
    )
    async def go_to_last_page(self, button: discord.ui.Button, interaction: discord.Interaction):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @discord.ui.button(style=discord.ButtonStyle.red, emoji="\N{CROSS MARK}", row=1)
    async def stop_pages(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        """stops the pagination session."""
        self.stop()
        await self.message.delete()
