import logging
from typing import Any, List, Optional, Tuple

import discord
import mendeleev
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.vendored.discord.ext import menus

from .data import IMAGES, LATTICES, UNITS

log = logging.getLogger("red.trusty-cogs.elements")


class ElementConverter(Converter):
    """Converts a given argument to an element object"""

    async def convert(self, ctx: commands.Context, argument: str) -> mendeleev.models.Element:
        result = None
        if argument.isdigit():
            try:
                result = mendeleev.element(int(argument))
            except Exception:
                raise BadArgument("`{}` is not a valid element!".format(argument))
        else:
            try:
                result = mendeleev.element(argument.title())
            except Exception:
                raise BadArgument("`{}` is not a valid element!".format(argument))
        if not result:
            raise BadArgument("`{}` is not a valid element!".format(argument))
        return result


class MeasurementConverter(Converter):
    """Converts a given measurement type into usable strings"""

    async def convert(self, ctx: commands.Context, argument: str) -> List[Tuple[str, str, str]]:
        result = []
        if argument.lower() in UNITS:
            result.append(
                (
                    argument.lower(),
                    UNITS[argument.lower()]["name"],
                    UNITS[argument.lower()]["units"],
                )
            )
        else:
            for k, v in UNITS.items():
                if argument.lower() in v["name"].lower():
                    result.append((k, v["name"], v["units"]))
                elif argument.lower() in k:
                    result.append((k, v["name"], v["units"]))
        if not result:
            raise BadArgument("`{}` is not a valid measurement!".format(argument))
        return result


def get_xray_wavelength(element: mendeleev.models.Element) -> str:
    try:
        ka = 1239.84 / (
            13.6057 * ((element.atomic_number - 1) ** 2) * ((1 / 1 ** 2) - (1 / 2 ** 2))
        )
    except Exception:
        ka = ""
    try:
        kb = 1239.84 / (
            13.6057 * ((element.atomic_number - 1) ** 2) * ((1 / 1 ** 2) - (1 / 3 ** 2))
        )
    except Exception:
        kb = ""
    try:
        la = 1239.84 / (
            13.6057 * ((element.atomic_number - 7.4) ** 2) * ((1 / 1 ** 2) - (1 / 2 ** 3))
        )
    except Exception:
        la = ""
    try:
        lb = 1239.84 / (
            13.6057 * ((element.atomic_number - 7.4) ** 2) * ((1 / 1 ** 2) - (1 / 2 ** 4))
        )
    except Exception:
        lb = ""

    data = "Kα {:.2}".format(ka) if ka else ""
    extra_1 = "Kβ {:.2}".format(kb) if kb else ""
    extra_2 = "Lα {:.2}".format(la) if la else ""
    extra_3 = "Lβ {:.2}".format(lb) if lb else ""
    return ", ".join(x for x in [data, extra_1, extra_2, extra_3] if x)


def get_lattice_string(element: mendeleev.models.Element) -> str:
    if element.lattice_structure:
        name, link = LATTICES[element.lattice_structure]
        return "[{}]({})".format(name, link)
    else:
        return ""


def element_embed(element: mendeleev.models.Element) -> discord.Embed:
    embed = discord.Embed()
    embed_title = (
        f"[{element.name} ({element.symbol})"
        f" - {element.atomic_number}](https://en.wikipedia.org/wiki/{element.name})"
    )
    embed.description = ("{embed_title}\n\n{desc}\n\n{sources}\n\n{uses}").format(
        embed_title=embed_title,
        desc=element.description,
        sources=element.sources,
        uses=element.uses,
    )
    if element.name in IMAGES:
        embed.set_thumbnail(url=IMAGES[element.name]["image"])
    if element.cpk_color:
        embed.colour = int(element.cpk_color.replace("#", ""), 16)
    attributes = {
        "atomic_weight": ("Atomic Weight", ""),
        "melting_point": ("Melting Point", "K"),
        "boiling_point": ("Boiling Point", "K"),
        "density": ("Density", "g/cm³"),
        "abundance_crust": ("Abundance in the Crust", "mg/kg"),
        "abundance_sea": ("Abundance in the Sea", "mg/L"),
        "name_origin": ("Name Origin", ""),
        "lattice_structure": ("Crystal Lattice", get_lattice_string(element)),
    }
    for attr, name in attributes.items():
        x = getattr(element, attr, "")
        if x:
            embed.add_field(name=name[0], value=f"{x} {name[1]}")
    embed.add_field(name="X-ray Fluorescence", value=get_xray_wavelength(element))
    discovery = f"{element.discoverers} ({element.discovery_year}) in {element.discovery_location}"
    embed.add_field(name="Discovery", value=discovery)

    return embed


class ElementPages(menus.ListPageSource):
    def __init__(self, pages: List[mendeleev.models.Element]):
        super().__init__(pages, per_page=1)

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, element: mendeleev.models.Element):
        return element_embed(element)


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
        if not interaction.response.is_done():
            await interaction.response.defer()


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
        if not interaction.response.is_done():
            await interaction.response.defer()


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
        if not interaction.response.is_done():
            await interaction.response.defer()


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
        if not interaction.response.is_done():
            await interaction.response.defer()


class BaseView(discord.ui.View):
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
            timeout=timeout,
        )
        self._source = source
        self.cog = cog
        self.page_start = page_start
        self.current_page = page_start
        self.message = message
        self.ctx = kwargs.get("ctx", None)
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

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        await self.send_initial_message(ctx, ctx.channel)

    async def send_initial_message(self, ctx, channel):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        if self.ctx is None:
            self.ctx = ctx
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await channel.send(**kwargs, view=self)
        return self.message

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
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
                content=("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        if interaction.user.id not in (*self.ctx.bot.owner_ids, self.ctx.author.id):
            await interaction.response.send_message(
                content=("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class Elements(commands.Cog):
    """Display information from the periodic table of elements"""

    __version__ = "1.1.0"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def element(
        self,
        ctx: commands.Context,
        element: ElementConverter,
        measurement: MeasurementConverter = None,
    ) -> None:
        """
        Display information about an element

        `element` can be the name, symbol or atomic number of the element
        `measurement` can be any of the Elements data listed here
        https://mendeleev.readthedocs.io/en/stable/data.html#electronegativities
        """
        if not measurement:
            return await ctx.send(embed=element_embed(element))
        else:
            msg = f"{element.name}: "
            for m in measurement:
                extra_1 = ""
                extra_2 = ""
                data = getattr(element, m[0], "")
                if m[0] == "lattice_structure":
                    extra_1, extra_2 = LATTICES[element.lattice_structure]
                if m[0] == "xrf":
                    extra_2 = get_xray_wavelength(element)

                msg += f"{m[1]} {data} {extra_1} {extra_2} {m[2]}\n"
            await ctx.send(msg)

    @commands.command(aliases=["ptable"])
    @commands.bot_has_permissions(embed_links=True)
    async def elements(self, ctx: commands.Context, *elements: ElementConverter) -> None:
        """
        Display information about multiple elements

        `elements` can be the name, symbol or atomic number of the element
        separated by spaces
        """
        if not elements:
            elements = mendeleev.get_all_elements()
        source = ElementPages(elements)
        await BaseView(
            source=source,
            cog=self,
        ).start(ctx)
