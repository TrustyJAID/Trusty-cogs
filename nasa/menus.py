from __future__ import annotations

from typing import Any, List, Optional

import discord
from red_commons.logging import getLogger

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.vendored.discord.ext import menus

from .models import (
    Collection,
    EPICData,
    Event,
    ManifestPhoto,
    NASAAstronomyPictureOfTheDay,
    NASATLEFeed,
    NearEarthObject,
    NEOFeed,
    PhotoManifest,
    RoverPhoto,
    TLEMember,
)

log = getLogger("red.Trusty-cogs.NASACog")
_ = Translator("NASA", __file__)


class NEOFeedPages(menus.ListPageSource):
    def __init__(self, feed: NEOFeed):
        self.feed = feed
        super().__init__(self.feed.near_earth_objects, per_page=1)
        self.select_options = [
            discord.SelectOption(label=page.name[:100], value=i)
            for i, page in enumerate(self.feed.near_earth_objects)
        ]

    async def format_page(self, view: BaseMenu, page: NearEarthObject):
        em = page.embed()
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class TLEPages(menus.ListPageSource):
    def __init__(self, feed: NASATLEFeed):
        self.feed = feed
        super().__init__(self.feed.member, per_page=1)
        self.select_options = [
            discord.SelectOption(label=page.name[:100], value=i)
            for i, page in enumerate(self.feed.member)
        ]

    async def format_page(self, view: BaseMenu, page: TLEMember):
        em = page.embed()
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class NASAImagesCollection(menus.ListPageSource):
    def __init__(self, collection: Collection):
        self.collection = collection
        super().__init__(collection.items, per_page=1)
        self.select_options = [
            discord.SelectOption(label=page.data[0].title[:100], value=i)
            for i, page in enumerate(collection.items)
        ]

    async def format_page(self, view: BaseMenu, page):
        url = None
        if page.data[0].media_type == "video":
            media_links = []
            try:
                media_links = await view.cog.request(page.href, include_api_key=False)
            except Exception:
                log.exception("Error getting video response data")
                pass
            for link in media_links:
                if link.endswith("orig.mp4"):
                    url = link.replace(" ", "%20")
        em = discord.Embed(
            title=page.data[0].title,
            description=page.data[0].description,
            timestamp=page.data[0].date_created,
            url=url,
        )
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        embeds = []
        for link in page.links:
            if link.rel != "preview":
                continue
            e = em.copy()
            e.set_image(url=link.href.replace(" ", "%20"))
            embeds.append(e)

        return {"embeds": embeds}


class MarsRoverManifest(menus.ListPageSource):
    def __init__(self, manifest: PhotoManifest):
        self.manifest = manifest
        super().__init__(manifest.photos, per_page=10)
        self.select_options = [
            discord.SelectOption(
                label=f"Page {i+1}",
                value=i,
            )
            for i in range(0, self._max_pages)
        ]

    async def format_page(self, view: BaseMenu, photos: List[ManifestPhoto]):
        description = ""
        for photo in photos:
            description += (
                f"Sol: {photo.sol} - Earth Date: {photo.earth_date}\n"
                f"Number of Photos: {photo.total_photos} - Cameras: {humanize_list(photo.cameras)}\n\n"
            )
        em = discord.Embed(title=self.manifest.name, description=description)
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class MarsRoverPhotos(menus.ListPageSource):
    def __init__(self, photos: List[RoverPhoto]):
        super().__init__(photos, per_page=1)
        self.select_options = [
            discord.SelectOption(
                label=f"Page {i+1}",
                description=f"{page.rover.name} - {page.camera.full_name}",
                value=i,
            )
            for i, page in enumerate(photos)
        ]

    async def format_page(self, view: BaseMenu, photo: RoverPhoto):
        em = photo.embed()
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class NASAEventPages(menus.ListPageSource):
    def __init__(self, events: List[Event]):
        super().__init__(events, per_page=1)
        self.select_options = [
            discord.SelectOption(label=page.title[:100], value=i) for i, page in enumerate(events)
        ]

    async def format_page(self, view: BaseMenu, event: Event):
        em = event.embed()
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class NASAapod(menus.ListPageSource):
    def __init__(self, pages: List[NASAAstronomyPictureOfTheDay]):
        super().__init__(pages, per_page=1)
        self.select_options = [
            discord.SelectOption(label=page.title[:100], value=i) for i, page in enumerate(pages)
        ]

    async def format_page(self, view: BaseMenu, page: NASAAstronomyPictureOfTheDay):
        em = page.embed()
        em.set_footer(text=f"Page {view.current_page + 1}/{self.get_max_pages()}")
        return em


class EPICPages(menus.ListPageSource):
    def __init__(self, pages: List[EPICData], enhanced: bool = False):
        super().__init__(pages, per_page=1)
        self.enhanced = enhanced
        self.select_options = [
            discord.SelectOption(label=page.identifier, value=i) for i, page in enumerate(pages)
        ]

    async def format_page(self, view: BaseMenu, page: EPICData):
        return page.embed(self.enhanced)


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

    async def on_timeout(self):
        await self.message.edit(view=None)

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
