import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional, Pattern

import aiohttp
import discord
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.vendored.discord.ext import menus

from .constants import BASE_URL, HEADSHOT_URL, TEAMS
from .errors import NoSchedule
from .game import Game
from .helper import DATE_RE
from .standings import Standings
from .player import Player

_ = Translator("Hockey", __file__)
log = logging.getLogger("red.trusty-cogs.hockey")


class GamesMenu(menus.MenuPages, inherit_buttons=False):
    def __init__(
        self,
        source: menus.PageSource,
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

    async def show_page(self, page_number, *, skip_next=False, skip_prev=False):
        try:
            page = await self._source.get_page(
                page_number, skip_next=skip_next, skip_prev=skip_prev
            )
        except NoSchedule:
            team = ""
            if self.source.team:
                team = _("for {teams} ").format(teams=humanize_list(self.source.team))
            msg = _("No schedule could be found {team}in dates between {last_searched}").format(
                team=team, last_searched=self.source._last_searched
            )
            await self.message.edit(content=msg, embed=None)
            return
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs)

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        try:
            page = await self._source.get_page(0)
        except (IndexError, NoSchedule):

            return await channel.send(self.format_error())
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    def format_error(self):
        team = ""
        if self.source.team:
            team = _("for {teams} ").format(teams=humanize_list(self.source.team))
        msg = _("No schedule could be found {team}in dates between {last_searched}").format(
            team=team, last_searched=self.source._last_searched
        )
        return msg

    async def show_checked_page(self, page_number: int) -> None:
        try:
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
        # log.info(f"Moving to next page, {self.current_page + 1}")
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.First(0),
    )
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0, skip_prev=True)

    @menus.button(
        "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
        position=menus.Last(1),
    )
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(0, skip_next=True)

    @menus.button("\N{CROSS MARK}")
    async def stop_pages(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        self.stop()
        await self.message.delete()

    @menus.button("\N{TEAR-OFF CALENDAR}")
    async def choose_date(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        send_msg = await self.ctx.send(
            _("Enter the date you would like to see `YYYY-MM-DD` format is accepted.")
        )

        def check(m: discord.Message):
            return m.author == self.ctx.author and DATE_RE.search(m.clean_content)

        try:
            msg = await self.ctx.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await send_msg.delete()
            return
        search = DATE_RE.search(msg.clean_content)
        if search:
            date_str = f"{search.group(1)}-{search.group(3)}-{search.group(4)}"
            date = datetime.strptime(date_str, "%Y-%m-%d")
            # log.debug(date)
            self.source.date = date
            try:
                await self.source.prepare()
            except NoSchedule:
                return await self.ctx.send(self.format_error())
            await self.show_page(0)

    @menus.button("\N{FAMILY}")
    async def choose_teams(self, payload: discord.RawReactionActionEvent) -> None:
        """stops the pagination session."""
        send_msg = await self.ctx.send(_("Enter the team you would like to filter for."))

        def check(m: discord.Message):
            return m.author == self.ctx.author

        try:
            msg = await self.ctx.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await send_msg.delete()
            return
        potential_teams = msg.clean_content.split()
        teams: List[str] = []
        for team, data in TEAMS.items():
            if "Team" in teams:
                continue
            nick = data["nickname"]
            short = data["tri_code"]
            pattern = fr"{short}\b|" + r"|".join(fr"\b{i}\b" for i in team.split())
            if nick:
                pattern += r"|" + r"|".join(fr"\b{i}\b" for i in nick)
            # log.debug(pattern)
            reg: Pattern = re.compile(fr"\b{pattern}", flags=re.I)
            for pot in potential_teams:
                find = reg.findall(pot)
                if find:
                    teams.append(team)
            self.source.team = teams
        try:
            await self.source.prepare()
        except NoSchedule:
            return await self.ctx.send(self.format_error())
        await self.show_page(0)


class StandingsPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)
        self.pages = pages

    def is_paginating(self):
        return False

    async def format_page(self, menu: menus.MenuPages, page):
        return await Standings.all_standing_embed(self.pages)


class TeamStandingsPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        return await Standings.make_team_standings_embed(page)


class ConferenceStandingsPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        return await Standings.make_conference_standings_embed(page)


class DivisionStandingsPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        return await Standings.make_division_standings_embed(page)


class LeaderboardPages(menus.ListPageSource):
    def __init__(self, pages: list, style: str):
        super().__init__(pages, per_page=1)
        self.style = style

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        em = discord.Embed(timestamp=datetime.utcnow())
        description = ""
        for msg in page:
            description += msg
        em.description = description
        em.set_author(
            name=menu.ctx.guild.name + _(" Pickems {style} Leaderboard").format(style=self.style),
            icon_url=menu.ctx.guild.icon_url,
        )
        em.set_thumbnail(url=menu.ctx.guild.icon_url)
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class PlayerPages(menus.ListPageSource):
    def __init__(self, pages: list, season: str):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.season = season

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        player = await Player.from_id(page)
        log.debug(player)
        player = await player.get_full_stats(self.season)
        em = player.get_embed()
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
