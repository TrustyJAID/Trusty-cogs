from __future__ import annotations

import asyncio
import functools
import logging
from html import unescape
from typing import Any, List, Optional

import discord
import tweepy

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import escape
from redbot.vendored.discord.ext import menus

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
                text = await menu.cog.replace_short_url(status)
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
                text = await menu.cog.replace_short_url(status)
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
                    reply_text = unescape(await menu.cog.replace_short_url(reply))
                    if hasattr(reply, "extended_tweet"):
                        reply_text = unescape(reply.extended_tweet["full_text"])
                    if hasattr(reply, "extended_entities") and not em.image:
                        em.set_image(url=reply.extended_entities["media"][0]["media_url_https"])
                    em.add_field(name=in_reply_to, value=reply_text)
            except IndexError:
                log.debug("Error grabbing in reply to tweet.", exc_info=True)

        em.description = escape(unescape(text), formatting=True)
        return {"embed": em, "content": str(post_url)}

    def _get_reply(self, ids: List[int]) -> tweepy.Status:
        return self._api.lookup_statuses(ids)

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
        await self.view.message.delete()


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
        await self.view.show_checked_page(self.view.current_page + 1)


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
        await self.view.show_checked_page(self.view.current_page - 1)


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
        await self.view.show_page(self.view._source.get_max_pages() - 1)


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
        await self.view.show_page(0)


class SkipForwardkButton(discord.ui.Button):
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
        await self.view.show_page(0, skip_next=True)


class SkipBackButton(discord.ui.Button):
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
        await self.view.show_page(0, skip_prev=True)


class TweetsMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.cog = cog
        self.page_start = page_start
        self.ctx = None
        self.message = None
        self._source = source
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = SkipBackButton(discord.ButtonStyle.grey, 0)
        self.last_item = SkipForwardkButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.stop_button)

    @property
    def source(self):
        return self._source


    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        await self._source._prepare_once()
        self.message = await self.send_initial_message(ctx, ctx.channel)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
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
        self.current_page = self.page_start
        try:
            page = await self._source.get_page(self.page_start)
        except NoTweets:
            await channel.send(_("No twitter account with that username could be found."))
            return
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs, view=self)

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
        await self.message.edit(**kwargs, view=self)

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

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: Optional[commands.Cog] = None,
        page_start: Optional[int] = 0,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout
        )
        self.cog = cog
        self._source = source
        self.ctx: commands.Context = None
        self.message: discord.Message = None
        self.page_start = page_start
        self.current_page = page_start
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.add_item(self.stop_button)

    @property
    def source(self):
        return self._source


    async def start(self, ctx: commands.Context):
        await self.source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx, ctx.channel)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await self.message.edit(**kwargs, view=self)

    async def send_initial_message(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        return await channel.send(**kwargs, view=self)

    async def update(self, payload: discord.RawReactionActionEvent) -> None:
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

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.message.id != self.message.id:
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
