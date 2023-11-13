from typing import Any, List, NamedTuple, Optional, Union

import discord
import mendeleev
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.vendored.discord.ext import menus

from .data import IMAGES, LATTICES, UNITS

log = getLogger("red.trusty-cogs.elements")

ELEMENTS = mendeleev.get_all_elements()


class ElementConverter(discord.app_commands.Transformer):
    """Converts a given argument to an element object"""

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> mendeleev.models.Element:
        result = None
        if argument.isdigit():
            try:
                result = mendeleev.element(int(argument))
            except Exception:
                raise commands.BadArgument("`{}` is not a valid element!".format(argument))
        else:
            try:
                result = mendeleev.element(argument.title())
            except Exception:
                raise commands.BadArgument("`{}` is not a valid element!".format(argument))
        if not result:
            raise commands.BadArgument("`{}` is not a valid element!".format(argument))
        return result

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> mendeleev.models.Element:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        all_choices = [
            discord.app_commands.Choice(
                name=f"{element.atomic_number} - {element.name}", value=str(element.atomic_number)
            )
            for element in ELEMENTS
        ]
        choices = [i for i in all_choices if current.lower() in i.name.lower()]
        return choices[:25]


class Measurements(NamedTuple):
    name: str
    units: str
    key: str


class MeasurementConverter(discord.app_commands.Transformer):
    """Converts a given measurement type into usable strings"""

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> Optional[Measurements]:
        log.trace("MeasurementConverter is being hit")
        result = None
        if argument.lower() in UNITS:
            value = argument.lower()
            name = UNITS[value]["name"]
            units = UNITS[value]["units"]
            result = Measurements(key=value, name=name, units=units)
        elif argument.replace(" ", "_").lower() in UNITS:
            value = argument.replace(" ", "_").lower()
            name = UNITS[value]["name"]
            units = UNITS[value]["units"]
            result = Measurements(key=value, name=name, units=units)
        else:
            for k, v in UNITS.items():
                if argument.lower() in v["name"].lower():
                    result = Measurements(key=k, name=v["name"], units=v["units"])
                elif argument.lower() in k:
                    result = Measurements(key=k, name=v["name"], units=v["units"])
        if not result:
            raise commands.BadArgument("`{}` is not a valid measurement!".format(argument))
        return result

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> Optional[Measurements]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        choices = [
            discord.app_commands.Choice(name=d["name"], value=k)
            for k, d in UNITS.items()
            if current.lower() in d["name"].lower()
        ]
        return choices[:25]


def get_xray_wavelength(element: mendeleev.models.Element) -> str:
    try:
        ka = 1239.84 / (
            13.6057 * ((element.atomic_number - 1) ** 2) * ((1 / 1**2) - (1 / 2**2))
        )
    except Exception:
        ka = ""
    try:
        kb = 1239.84 / (
            13.6057 * ((element.atomic_number - 1) ** 2) * ((1 / 1**2) - (1 / 3**2))
        )
    except Exception:
        kb = ""
    try:
        la = 1239.84 / (
            13.6057 * ((element.atomic_number - 7.4) ** 2) * ((1 / 1**2) - (1 / 2**3))
        )
    except Exception:
        la = ""
    try:
        lb = 1239.84 / (
            13.6057 * ((element.atomic_number - 7.4) ** 2) * ((1 / 1**2) - (1 / 2**4))
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
        row: Optional[int] = None,
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


class _NavigateButton(discord.ui.Button):
    def __init__(
        self, style: discord.ButtonStyle, emoji: Union[str, discord.PartialEmoji], direction: int
    ):
        super().__init__(style=style, emoji=emoji)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        if self.direction == 0:
            self.view.current_page = 0
        elif self.direction == self.view.source.get_max_pages():
            self.view.current_page = self.view.source.get_max_pages() - 1
        else:
            self.view.current_page += self.direction
        kwargs = await self.view.get_page(self.view.current_page)
        await interaction.response.edit_message(**kwargs)


class SelectMenu(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="Select an Element", min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        self.view.current_page = index
        await self.view.show_page(self.view.current_page, interaction)


class BaseView(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        timeout: int = 180,
        page_start: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self._source = source
        self.page_start = page_start
        self.current_page = page_start
        self.forward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=1,
        )
        self.backward_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
            direction=-1,
        )
        self.first_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=0,
        )
        self.last_button = _NavigateButton(
            discord.ButtonStyle.grey,
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
            direction=self.source.get_max_pages(),
        )
        self.select_options = [
            discord.SelectOption(label=f"{x.atomic_number} - {x.name}", value=num)
            for num, x in enumerate(self.source.entries)
        ]
        self.stop_button = StopButton(discord.ButtonStyle.red)
        self.add_item(self.stop_button)
        self.add_item(self.first_button)
        self.add_item(self.backward_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_button)
        self.select_menu = self._get_select_menu()
        self.add_item(self.select_menu)

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    def _get_select_menu(self):
        # handles modifying the select menu if more than 25 pages are provided
        # this will show the previous 12 and next 13 pages in the select menu
        # based on the currently displayed page. Once you reach close to the max
        # pages it will display the last 25 pages.
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
        await self.send_initial_message(ctx)

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """
        self.ctx = ctx
        page = await self._source.get_page(self.page_start)
        kwargs = await self._get_kwargs_from_page(page)
        self.message = await ctx.send(**kwargs, view=self)
        self.author = ctx.author
        return self.message

    async def _get_kwargs_from_page(self, page: int):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if len(self.select_options) > 25:
            self.remove_item(self.select_menu)
            self.select_menu = self._get_select_menu()
            self.add_item(self.select_menu)
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
        await interaction.response.edit_message(**kwargs, view=self)

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
            getattr(self.author, "id", None),
        ):
            await interaction.response.send_message(
                content=("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class Elements(commands.Cog):
    """Display information from the periodic table of elements"""

    __version__ = "1.1.1"
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

    @commands.hybrid_command(name="element", aliases=["ptable", "elements"])
    @commands.bot_has_permissions(embed_links=True)
    async def element(
        self,
        ctx: commands.Context,
        element: Optional[
            discord.app_commands.Transform[mendeleev.models.Element, ElementConverter]
        ] = None,
        measurement: Optional[
            discord.app_commands.Transform[Measurements, MeasurementConverter]
        ] = None,
    ) -> None:
        """
        Display information about an element

        `element` can be the name, symbol or atomic number of the element
        `measurement` can be any of the Elements data listed here
        https://mendeleev.readthedocs.io/en/stable/data.html#electronegativities
        """

        if measurement is None or element is None:
            async with ctx.typing():
                page_start = 0
                if element is not None:
                    page_start = element.atomic_number - 1

                source = ElementPages(ELEMENTS)
            await BaseView(
                source=source,
                cog=self,
                page_start=page_start,
            ).start(ctx)
            return
        else:
            async with ctx.typing():
                extra_1 = ""
                extra_2 = ""
                name = measurement.name
                units = measurement.units
                data = getattr(element, measurement.key, "")
                if measurement.key == "lattice_structure":
                    extra_1, extra_2 = LATTICES[element.lattice_structure]
                if measurement.key == "xrf":
                    extra_2 = get_xray_wavelength(element)

                msg = f" {element.name}:{name} {data} {extra_1} {extra_2} {units}\n"
            await ctx.send(msg)
