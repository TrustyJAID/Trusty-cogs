from __future__ import annotations

import asyncio
import functools
import logging
from html import unescape
from typing import Any, List, Optional

import discord

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator

from redbot.core.utils.chat_formatting import escape
from redbot.vendored.discord.ext import menus

import tweepy


log = logging.getLogger("red.Trusty-cogs.tweets")
_ = Translator("Tweets", __file__)


class NoTweets(Exception):
    pass


class TweetListPages(menus.ListPageSource):
    def __init__(self, pages: list):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        em = page
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return em


class TweetPages(menus.PageSource):
    def __init__(self, **kwargs):
        self._page: int = 1
        self._index: int = 0
        self._cache: List[tweepy.Status] = []
        self._checks: int = 0
        self._last_page: int = 0
        self._api = kwargs.get("api")
        self._loop = kwargs.get("loop")
        self._username: str = kwargs.get("username")
        self._last_searched: str = ""

    @property
    def index(self) -> int:
        return self._index

    @property
    def last_page(self) -> int:
        return self._last_page

    async def get_page(
        self, page_number, *, skip_next: bool = False, skip_prev: bool = False
    ) -> dict:
        # log.info(f"Cache size is {len(self._cache)}")

        if page_number < self.last_page:
            page = await self.prev()
        if page_number > self.last_page:
            page = await self.next()
        if page_number == self.last_page and self._cache:
            page = self._cache[page_number]
        if skip_next:
            page = await self.next(True)
        if skip_prev:
            page = await self.prev(True)
        if not self._cache:
            raise NoTweets
        # log.info(page)
        self._last_page = page_number
        return page

    async def next(self, skip: bool = False) -> dict:
        """
        Returns the next element from the list

        If all elements have been traversed attempt to pull new data

        If no new data can be found within a reasonable number of calls stop
        """
        self._index += 1
        if self._index > (len(self._cache) - 1) or skip:

            try:
                await self._next_batch(_next=True)
            except Exception:
                # log.debug("Error getting schedule")
                raise
            self._index = 0
        # log.info(f"getting next data {len(self._cache)}")
        return self._cache[self.index]

    async def prev(self, skip: bool = False) -> dict:
        """
        Returns the previous element from the list

        If all elements have been traversed pull new data

        If no new data can be found within a reasonable number of calls stop
        (this one is expected to have more time between calls)
        I wonder if I should traverse weekly instead of daily :blobthink:
        """
        self._index -= 1
        if self._index < 0 or skip:
            # Grab new list from previous day
            try:
                new_data = await self._next_batch(_prev=True)
                self._index = len(new_data) - 1
            except Exception:
                # log.debug("Error getting schedule")
                self._index = 0
                raise
        return self._cache[self.index]

    async def prepare(self) -> None:
        try:
            await self._next_batch()
        except Exception:
            pass

    def is_paginating(self) -> bool:
        return True

    def _get_twitter_statuses(
        self,
    ) -> List[tweepy.Status]:

        msg_list = []
        try:
            statuses = self._api.user_timeline(id=self._username, page=self._page)
            if statuses:
                for status in statuses:
                    msg_list.append(status)

        except tweepy.TweepError:
            raise

        return msg_list

    async def _next_batch(
        self,
        *,
        _next: bool = False,
        _prev: bool = False,
    ) -> List[tweepy.Status]:
        """
        Actually grab the list of games.
        """
        # compare_date = datetime.utcnow().strftime("%Y-%m-%d")
        log.debug("Pulling tweets into the cache")
        if _next:
            self._page += 1
        elif _prev:
            self._page -= 1
        try:
            fake_task = functools.partial(
                self._get_twitter_statuses,
            )
            task = self._loop.run_in_executor(None, fake_task)
            msg_list = await asyncio.wait_for(task, timeout=60)
            # log.debug(next(self._listing))
        except asyncio.TimeoutError:
            log.error("Timeout error pulling tweet statuses")
        except tweepy.TweepError:
            log.debug("Error pulling twitter info")

        self._cache = msg_list
        # return the games as a form of metadata about how the cache is changing
        return msg_list

    async def format_page(self, menu: menus.MenuPages, status: tweepy.Status):
        if not status:
            return discord.Embed(title="Nothing")
        username = status.user.screen_name
        post_url = "https://twitter.com/{}/status/{}".format(status.user.screen_name, status.id)
        em = discord.Embed(
            colour=discord.Colour(value=int(status.user.profile_link_color, 16)),
            url=post_url,
            timestamp=status.created_at,
        )
        em.set_footer(text=f"@{username}")
        if hasattr(status, "retweeted_status"):
            em.set_author(
                name=f"{status.user.name} Retweeted {status.retweeted_status.user.name}",
                url=post_url,
                icon_url=status.user.profile_image_url,
            )
            status = status.retweeted_status
            em.set_footer(text=f"@{username} RT @{status.user.screen_name}")
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    img = status.extended_tweet["entities"]["media"][0]["media_url_https"]
                    em.set_image(url=img)
            else:
                text = status.text
        else:
            em.set_author(
                name=status.user.name, url=post_url, icon_url=status.user.profile_image_url
            )
            if hasattr(status, "extended_entities"):
                em.set_image(url=status.extended_entities["media"][0]["media_url_https"])
            if hasattr(status, "extended_tweet"):
                text = status.extended_tweet["full_text"]
                if "media" in status.extended_tweet["entities"]:
                    img = status.extended_tweet["entities"]["media"][0]["media_url_https"]
                    em.set_image(url=img)
            else:
                text = status.text
        if status.in_reply_to_screen_name:
            try:
                task = self._loop.run_in_executor(
                    None, self._get_reply, [status.in_reply_to_status_id]
                )
                msg_list = await asyncio.wait_for(task, timeout=60)
                if msg_list:
                    # log.debug(reply)
                    reply = msg_list[0]
                    in_reply_to = _("In reply to {name} (@{screen_name})").format(
                        name=reply.user.name, screen_name=reply.user.screen_name
                    )
                    reply_text = unescape(reply.text)
                    if hasattr(reply, "extended_tweet"):
                        reply_text = unescape(reply.extended_tweet["full_text"])
                    if hasattr(reply, "extended_entities") and not em.image:
                        em.set_image(url=reply.extended_entities["media"][0]["media_url_https"])
                    em.add_field(name=in_reply_to, value=reply_text)
            except IndexError:
                log.debug("Error grabbing in reply to tweet.", exc_info=True)

        em.description = escape(unescape(text), formatting=True)
        return em

    def _get_reply(self, ids: List[int]) -> tweepy.Status:
        return self._api.statuses_lookup(ids)


class TweetsMenu(menus.MenuPages, inherit_buttons=False):
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
        try:
            page = await self._source.get_page(self.page_start)
        except NoTweets:
            await channel.send(_("No twitter account with that username could be found."))
            return
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs)

    async def show_page(
        self, page_number: int, *, skip_next: bool = False, skip_prev: bool = False
    ) -> None:
        try:
            page = await self._source.get_page(
                page_number, skip_next=skip_next, skip_prev=skip_prev
            )
        except NoTweets:
            msg = _("No twitter information could be found for {username}.").format(
                username=self.source._username
            )
            await self.message.edit(content=msg, embed=None)
            return
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs)

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