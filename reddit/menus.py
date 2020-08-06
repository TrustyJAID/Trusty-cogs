from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator
from apraw.models import Submission, Subreddit

import discord
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape, humanize_number
from redbot.vendored.discord.ext import menus

from .helpers import BASE_URL, make_embed_from_submission

log = logging.getLogger("red.Trusty-cogs.reddit")


class RedditMenu(menus.AsyncIteratorPageSource):
    def __init__(self, submissions: AsyncGenerator[Submission, Subreddit], subreddit: Subreddit):
        super().__init__(submissions, per_page=1)
        self._subreddit = subreddit
        self.over_18 = False

    async def format_page(self, menu: menus.MenuPages, submission: Submission):
        em = None
        self.over_18 = submission.over_18
        if submission.over_18 and not menu.ctx.channel.is_nsfw():
            return None
        return await make_embed_from_submission(menu.ctx.channel, self._subreddit, submission)


class BaseMenu(menus.MenuPages, inherit_buttons=False):
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

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(0)
        if page.over_18 and not channel.is_nsfw():
            for i in range(1, 10):
                page = await self._source.get_page(i)
                if not page.over_18:
                    self.current_page = i
                    break
            if page.over_18:
                return await channel.send("This is not a NSFW channel.")
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        if page.over_18 and not self.message.channel.is_nsfw():
            await self.message.edit(content="This post is NSFW.", embed=None)
            return
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
