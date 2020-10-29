from __future__ import annotations

import logging
from typing import Any, List, Optional

import discord

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator

from redbot.core.utils.chat_formatting import pagify
from redbot.vendored.discord.ext import menus


log = logging.getLogger("red.Trusty-cogs.roletools")
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
        settings = _(
            "__Sticky:__ **{sticky}**\n__Auto:__ **{auto}**\n"
            "__Self Assignable:__ **{selfassign}**\n"
            "__Self Removable:__ **{selfrem}**\n"
            "__Colour: __ **{colour}**\n"
            "__Is Mod:__ **{mod}**\n"
            "__Is Admin:__ **{admin}**\n"
        ).format(
            sticky=role_settings["sticky"],
            auto=role_settings["auto"],
            selfassign=role_settings["selfassignable"],
            selfrem=role_settings["selfremovable"],
            colour=str(role.colour),
            mod=role in mod_roles,
            admin=role in admin_roles,
        )
        reaction_roles = ""
        for reaction in role_settings["reactions"]:
            channel, message, emoji = reaction.split("-")
            if emoji.isdigit():
                emoji = menu.bot.get_emoji(int(emoji))
            if not emoji:
                emoji = _("Emoji from another server")
            link = jump_url.format(guild=menu.ctx.guild.id, channel=channel, message=message)
            reaction_roles += _("{emoji} on [message]({link})\n").format(emoji=emoji, link=link)
        for page in pagify(reaction_roles, page_length=1024):
            em.add_field(name=_("Reaction Roles"), value=page)

        em.description = f"{role.mention}\n{settings}"
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class BaseMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog
        self.page_start = page_start

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.current_page = self.page_start
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def update(self, payload):
        """|coro|

        Updates the menu after an event has been received.

        Parameters
        -----------
        payload: :class:`discord.RawReactionActionEvent`
            The reaction event that triggered this update.
        """
        button = self.buttons[payload.emoji]
        if not self._running:
            return

        try:
            if button.lock:
                async with self._lock:
                    if self._running:
                        await button(self, payload)
            else:
                await button(self, payload)
        except Exception as exc:
            log.debug("Ignored exception on reaction event", exc_info=exc)

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

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self._author_id):
            return False
        return payload.emoji in self.buttons

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

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
        skip_if=_skip_single_arrows,
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
        skip_if=_skip_single_arrows,
    )
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
        skip_if=_skip_double_triangle_buttons,
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        await self.message.delete()
