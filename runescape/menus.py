from __future__ import annotations

import asyncio
from typing import Any, List, Optional

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number
from redbot.vendored.discord.ext import menus

from .wikiapi import Exchange, FiltersEndpoint, WikiAPI, WikiAPIError, plot_exchange

log = getLogger("red.Trusty-cogs.runescape")
_ = Translator("Runescape but this doesn't really matter", __file__)


class GESinglePages(menus.ListPageSource):
    def __init__(self, pages: List[Exchange], api: WikiAPI):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.api = api
        self.current_item: Exchange = self.pages[0]
        self.current_endpoint: FiltersEndpoint = self.current_item._endpoint

    async def format_page(self, view: BaseMenu, page: Exchange):
        self.current_item = page
        em = discord.Embed(title=page.name, url=page.url)
        em.add_field(name="Current", value=humanize_number(page.price))
        if page.volume:
            em.add_field(name="Volume", value=page.volume)
        em.add_field(name="Last Updated", value=discord.utils.format_dt(page.datetime, "R"))
        em.set_thumbnail(url=page.image)
        page_num = f"Page {view.current_page + 1}/{self.get_max_pages()}"
        wiki_url = page._game.wiki_url
        em.set_footer(text=f"{page_num} all data courtesy of {wiki_url}")
        return {"embeds": [em], "attachments": []}


class GEChartPages(menus.ListPageSource):
    def __init__(self, pages: List[List[Exchange]], api: WikiAPI):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.api = api
        self.current_item: Exchange = self.pages[0][-1]
        self.current_endpoint = self.current_item._endpoint

    async def plot(self, items: List[Exchange]):
        return await asyncio.to_thread(plot_exchange, items)

    async def format_page(self, view: BaseMenu, pages: List[Exchange]):
        page = pages[-1]
        self.current_item = page
        em = discord.Embed(title=page.name, url=page.url)
        em.add_field(name="Current", value=humanize_number(page.price))
        if page.volume:
            em.add_field(name="Volume", value=page.volume)
        em.add_field(name="Last Updated", value=discord.utils.format_dt(page.datetime, "R"))
        em.set_thumbnail(url=page.image)
        plot = await self.plot(pages)
        em.set_image(url=f"attachment://{plot.filename}")
        page_num = f"Page {view.current_page + 1}/{self.get_max_pages()}"
        wiki_url = page._game.wiki_url
        em.set_footer(text=f"{page_num} all data courtesy of {wiki_url}")
        return {"embeds": [em], "attachments": [plot]}


class FiltersButton(discord.ui.Button):
    def __init__(self, endpoint: FiltersEndpoint):
        super().__init__(label=endpoint.get_name())
        self.endpoint = endpoint
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for b in self.view.filters_buttons.values():
            if b.endpoint is self.endpoint:
                b.disabled = True
            else:
                b.disabled = False
        item_name = self.view.source.current_item.name
        game = self.view.source.current_item._game
        data = await self.view.source.api.exchange_method(self.endpoint)(game, name=item_name)
        new_source = GEChartPages([data], self.view.source.api)
        self.view._source = new_source
        await self.view.show_checked_page(0, interaction)


class SearchModal(discord.ui.Modal):
    def __init__(self, view: BaseMenu):
        super().__init__(title="Search")
        self.view = view
        self.search_text = discord.ui.TextInput(
            label="Search",
            placeholder="Search for an item(s). e.g. fractured staff of armadyl|bond",
        )
        self.add_item(self.search_text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        api = self.view.source.api
        game = self.view.source.current_item._game
        try:
            if len(self.search_text.value.split("|")) > 1:
                data = await api.latest(game=game, name=self.search_text.value)
                source = GESinglePages(data, api)
            else:
                data = await api.last90d(game=game, name=self.search_text.value)
                source = GEChartPages([data], api)
        except WikiAPIError as e:
            await interaction.followup.send(e, ephemeral=True)
            return

        self.view._source = source
        for b in self.view.filters_buttons.values():
            if b.endpoint is source.current_endpoint:
                b.disabled = True
            else:
                b.disabled = False
        await self.view.show_checked_page(0, interaction)


class SearchButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Search")
        self.view: BaseMenu

    async def callback(self, interaction: discord.Interaction):
        modal = SearchModal(self.view)
        await interaction.response.send_modal(modal)


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        self.view: BaseMenu
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
        self.view: BaseMenu
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
        self.view: BaseMenu
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
        self.view: BaseMenu
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
        self.view: BaseMenu
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        timeout: int = 180,
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
        if isinstance(source, (GEChartPages, GESinglePages)):
            self.search_button = SearchButton()
            self.add_item(self.search_button)
            self.filters_buttons = {}
            for f in FiltersEndpoint:
                # the sample endpoint basically contains data in all
                # and the latest endpoint is only 1 point of data
                # so we can skip these two for now but the logic is here
                # to allow those endpoints easily
                if f in (FiltersEndpoint.latest, FiltersEndpoint.sample):
                    continue
                self.filters_buttons[f] = FiltersButton(f)
                if self.source.current_endpoint is f:
                    self.filters_buttons[f].disabled = True
                self.add_item(self.filters_buttons[f])

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        self.bot = self.cog.bot
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx)

    def check_paginating(self):
        if not self.source.is_paginating():
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
        else:
            self.forward_button.disabled = False
            self.back_button.disabled = False
            self.first_item.disabled = False
            self.last_item.disabled = False

    async def _get_kwargs_from_page(self, page):
        self.check_paginating()
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
        self.author = ctx.author
        if self.ctx is None:
            self.ctx = ctx
        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        if "attachments" in kwargs:
            kwargs["files"] = kwargs.pop("attachments")
        self.message = await ctx.send(**kwargs, view=self)
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = self.source.pages.index(page)
        kwargs = await self._get_kwargs_from_page(page)
        if interaction.response.is_done():
            await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)
        # await self.message.edit(**kwargs)

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
            self.author.id,
        ):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
