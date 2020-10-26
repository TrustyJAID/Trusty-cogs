from __future__ import annotations

import logging
from typing import Any, List
from datetime import datetime

import discord

from redbot.core import commands
from redbot.vendored.discord.ext import menus
from redbot.core.i18n import Translator

from .twitch_models import TwitchFollower


log = logging.getLogger("red.Trusty-cogs.twitch")

_ = Translator("Twitch", __file__)


class TwitchFollowersPages(menus.ListPageSource):
    def __init__(self, followers: List[TwitchFollower], total_follows: int):
        super().__init__(followers, per_page=1)

    async def format_page(self, menu: menus.MenuPages, follower: TwitchFollower):
        user_id = follower.from_id
        followed_at = follower.followed_at

        profile = await menu.cog.get_profile_from_id(user_id)
        em = profile.make_user_embed()
        em.timestamp = datetime.strptime(followed_at, "%Y-%m-%dT%H:%M:%SZ")
        prof_url = "https://twitch.tv/{}".format(profile.login)
        return {"content": prof_url, "embed": em}


class TwitchClipsPages(menus.ListPageSource):
    def __init__(self, clips: List[str]):
        super().__init__(clips, per_page=1)

    async def format_page(self, menu: menus.MenuPages, clip: str):
        return clip

    async def twitch_menu(
        self,
        ctx: Context,
        post_list: list,
        total_followers=0,
        message: Optional[discord.Message] = None,
        page=0,
        timeout: int = 30,
    ):
        """menu control logic for this taken from
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        user_id = post_list[page].from_id
        followed_at = post_list[page].followed_at

        profile = await self.get_profile_from_id(user_id)
        em = None
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = await self.make_user_embed(profile)
            em.timestamp = datetime.strptime(followed_at, "%Y-%m-%dT%H:%M:%SZ")

        prof_url = "https://twitch.tv/{}".format(profile.login)


class BaseMenu(menus.MenuPages, inherit_buttons=False):
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
            source,
            clear_reactions_after=clear_reactions_after,
            delete_message_after=delete_message_after,
            timeout=timeout,
            message=message,
            **kwargs,
        )
        self.cog = cog

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
