from __future__ import annotations

import logging
from typing import Any, List, Optional, Union

import discord

from redbot.core import commands
from redbot.vendored.discord.ext import menus
from redbot.core.i18n import Translator


log = logging.getLogger("red.Trusty-cogs.serverstats")

_ = Translator("serverstats", __file__)


class AvatarPages(menus.ListPageSource):
    def __init__(self, members: List[discord.Member]):
        super().__init__(members, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, member: discord.Member) -> discord.Embed:
        em = discord.Embed(title=_("**Avatar**"), colour=member.colour)
        url = str(member.avatar_url_as(static_format="png"))
        if member.is_avatar_animated():
            url = str(member.avatar_url_as(format="gif"))
        em.set_image(url=url)
        try:
            em.set_author(
                name=f"{member} {f'~ {member.nick}' if member.nick else ''}",
                icon_url=url,
                url=url,
            )
        except AttributeError:
            em.set_author(name=f"{member}", icon_url=url, url=url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class GuildPages(menus.ListPageSource):
    def __init__(self, guilds: List[discord.Guild]):
        super().__init__(guilds, per_page=1)
        self.guild: Optional[discord.Guild] = None

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, guild: discord.Guild):
        self.guild = guild
        em = await menu.cog.guild_embed(guild)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class ListPages(menus.ListPageSource):
    def __init__(self, pages: List[Union[discord.Embed, str]]):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page: Union[discord.Embed, str]):
        return page


class BaseMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 60,
        message: discord.Message = None,
        page_start: int = 0,
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
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

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

    def _skip_non_guild_buttons(self) -> bool:
        if self.ctx.author.id not in self.bot.owner_ids:
            return True
        if isinstance(self.source, GuildPages):
            return False
        return True

    @menus.button(
        "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.First(1),
    )
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(
        "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
        position=menus.Last(0),
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

    @menus.button("\N{OUTBOX TRAY}", skip_if=_skip_non_guild_buttons)
    async def leave_guild_button(self, payload):
        await self.cog.confirm_leave_guild(self.ctx, self.source.guild)

    @menus.button("\N{INBOX TRAY}", skip_if=_skip_non_guild_buttons)
    async def make_guild_invite_button(self, payload):
        invite = await self.cog.get_guild_invite(self.source.guild)
        if invite:
            await self.ctx.send(str(invite))
        else:
            await self.ctx.send(
                _("I cannot find or create an invite for `{guild}`").format(
                    guild=self.source.guild.name
                )
            )
