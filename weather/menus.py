from __future__ import annotations

from typing import Any, List, Optional, Union

import aiohttp
import discord
from red_commons.logging import getLogger

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.vendored.discord.ext import menus

from .api import APIError, Geocoding, OneCall, Units

log = getLogger("red.Trusty-cogs.weather")
_ = Translator("Weather", __file__)


class WeatherPages(menus.ListPageSource):
    def __init__(
        self,
        pages: List[Geocoding],
        units: Units,
        lang: Optional[str],
        forecast: Optional[bool] = False,
        *,
        api_version: str,
    ):
        super().__init__(pages, per_page=1)
        self.units = units
        self.lang = lang
        self.forecast = forecast if forecast is not None else False
        self.hourly = False
        self.select_options = [
            discord.SelectOption(label=page.location, value=i) for i, page in enumerate(pages)
        ]
        self._last_we = None
        self._last_coords = None
        self.api_version = api_version

    async def format_page(self, view: BaseMenu, page: Geocoding):
        log.verbose("WeatherPages page: %s", page)
        if self._last_coords != page:
            try:
                we = await OneCall.get(
                    appid=view.appid,
                    lat=page.lat,
                    lon=page.lon,
                    units=self.units,
                    lang=self.lang,
                    name=page.name,
                    state=page.state,
                    country=page.country,
                    session=view.session,
                    api_version=self.api_version,
                )
            except APIError as e:
                return _("Error retriving weather data: {error}").format(error=e)
        else:
            we = self._last_we
        if self._last_coords is None:
            self._last_coords = page
            self._last_we = we
        if await view.ctx.embed_requested():
            return we.embed(include_forecast=self.forecast, include_hourly=self.hourly)
        else:
            return we.text(include_forecast=self.forecast, include_hourly=self.hourly)


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
        await self.view.show_checked_page(self.view.current_page + 1, interaction=interaction)


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
        await self.view.show_checked_page(self.view.current_page - 1, interaction=interaction)


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
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction=interaction)


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
        await self.view.show_page(0, interaction=interaction)


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
        await self.view.show_page(0, skip_next=True, interaction=interaction)


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
        await self.view.show_page(0, skip_prev=True, interaction=interaction)


class ForecastButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label=_("Forecast"), emoji="\N{CALENDAR}")

    async def callback(self, interaction: discord.Interaction):
        self.view.source.forecast = not self.view.source.forecast
        if self.view.source.hourly and self.view.source.forecast:
            self.view.source.hourly = False
            self.view.hourly_button.disabled = False
        if self.view.source.forecast:
            self.disabled = True
        await self.view.show_page(self.view.current_page, interaction=interaction)


class HourlyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label=_("Hourly"), emoji="\N{CLOCK FACE ONE OCLOCK}")

    async def callback(self, interaction: discord.Interaction):
        self.view.source.hourly = not self.view.source.hourly
        if self.view.source.forecast and self.view.source.hourly:
            self.view.source.forecast = False
            self.view.forecast_button.disabled = False
        if self.view.source.hourly:
            self.disabled = True
        await self.view.show_page(self.view.current_page, interaction=interaction)


class CurrentButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label=_("Current"))

    async def callback(self, interaction: discord.Interaction):
        self.view.source.hourly = False
        self.view.source.forecast = False
        self.view.forecast_button.disabled = False
        self.view.hourly_button.disabled = False
        await self.view.show_page(self.view.current_page, interaction=interaction)


class SelectMenu(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            placeholder=_("Select a Page"), min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        self.view.current_page = index
        await self.view.show_page(self.view.current_page, interaction)


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        appid: str,
        session: aiohttp.ClientSession,
        cog: Optional[commands.Cog] = None,
        page_start: int = 0,
        timeout: int = 180,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self._source = source
        self.ctx: commands.Context = None
        self.message: discord.Message = None
        self.page_start = page_start
        self.current_page = page_start
        self.appid = appid
        self.session = session
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
        self.select_options = getattr(self.source, "select_options", [])
        self.select_menu: Optional[SelectMenu] = self.get_select_menu()
        if self.select_menu:
            self.add_item(self.select_menu)
        self.forecast_button = ForecastButton()
        self.hourly_button = HourlyButton()
        self.current_button = CurrentButton()
        if self.source.forecast:
            self.forecast_button.disabled = True

        if self.source.hourly:
            self.hourly_button.disabled = True
        self.add_item(self.forecast_button)
        self.add_item(self.hourly_button)
        self.add_item(self.current_button)

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: Any):
        log.exception(error)

    @property
    def source(self):
        return self._source

    def disable_pagination(self):
        if not self.source.is_paginating():
            self.forward_button.disabled = True
            self.back_button.disabled = True
            self.first_item.disabled = True
            self.last_item.disabled = True
            if self.select_menu:
                self.select_menu.disabled = True
        else:
            self.forward_button.disabled = False
            self.back_button.disabled = False
            self.first_item.disabled = False
            self.last_item.disabled = False
            if self.select_menu:
                self.select_menu.disabled = False

    def get_select_menu(self):
        # handles modifying the select menu if more than 25 pages are provided
        # this will show the previous 12 and next 13 pages in the select menu
        # based on the currently displayed page. Once you reach close to the max
        # pages it will display the last 25 pages.
        if not self.select_options:
            return None
        if len(self.select_options) > 25:
            minus_diff = None
            plus_diff = 25
            if 12 < self.current_page < len(self.select_options) - 25:
                minus_diff = self.current_page - 12
                plus_diff = self.current_page + 13
            elif self.current_page >= len(self.select_options) - 25:
                minus_diff = len(self.select_options) - 25
                plus_diff = None
            options = self.select_options[minus_diff:plus_diff]
        else:
            options = self.select_options[:25]
        return SelectMenu(options)

    async def start(self, ctx: commands.Context):
        await self.source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self.disable_pagination()
        if self.select_menu and len(self.select_options) > 25 and self.source.is_paginating():
            self.remove_item(self.select_menu)
            self.select_menu = self.get_select_menu()
            if self.select_menu:
                self.add_item(self.select_menu)
        await interaction.response.edit_message(**kwargs, view=self)

    async def send_initial_message(self, ctx: commands.Context) -> discord.Message:
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        self.disable_pagination()
        return await ctx.send(**kwargs, view=self)

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
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
