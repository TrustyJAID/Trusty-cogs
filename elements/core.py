import logging
from typing import List, Tuple

import aiohttp
import discord
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from mendeleev import element as ELEMENTS
from redbot.core import commands
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .data import IMAGES, LATTICES, UNITS

log = logging.getLogger("red.trusty-cogs.elements")


class ElementConverter(Converter):
    """Converts a given argument to an element object"""

    async def convert(self, ctx: commands.Context, argument: str) -> ELEMENTS:
        result = None
        if argument.isdigit():
            if int(argument) > 118 or int(argument) < 1:
                raise BadArgument("`{}` is not a valid element!".format(argument))
            result = ELEMENTS(int(argument))
        else:
            try:
                result = ELEMENTS(argument.title())
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


class Elements(commands.Cog):
    """Display information from the periodic table of elements"""

    __version__ = "1.0.2"
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

    @staticmethod
    def get_lattice_string(element: ELEMENTS) -> str:
        if element.lattice_structure:
            name, link = LATTICES[element.lattice_structure]
            return "[{}]({})".format(name, link)
        else:
            return ""

    @staticmethod
    def get_xray_wavelength(element: ELEMENTS) -> str:
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
            return await ctx.send(embed=await self.element_embed(element))
        else:
            msg = f"{element.name}: "
            for m in measurement:
                extra_1 = ""
                extra_2 = ""
                data = getattr(element, m[0], "")
                if m[0] == "lattice_structure":
                    extra_1, extra_2 = LATTICES[element.lattice_structure]
                if m[0] == "xrf":
                    extra_2 = self.get_xray_wavelength(element)

                msg += f"{m[1]} {data} {extra_1} {extra_2} {m[2]}\n"
            await ctx.send(msg)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def elements(self, ctx: commands.Context, *elements: ElementConverter) -> None:
        """
        Display information about multiple elements

        `elements` can be the name, symbol or atomic number of the element
        separated by spaces
        """
        if not elements:
            elements = [ELEMENTS(e) for e in range(1, 119)]
        await menu(ctx, [await self.element_embed(e) for e in elements], DEFAULT_CONTROLS)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def ptable(self, ctx: commands.Context) -> None:
        """Display a menu of all elements"""
        embeds = [await self.element_embed(ELEMENTS(e)) for e in range(1, 119)]
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    async def element_embed(self, element: ELEMENTS) -> discord.Embed:
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
            "lattice_structure": ("Crystal Lattice", self.get_lattice_string(element)),
        }
        for attr, name in attributes.items():
            x = getattr(element, attr, "")
            if x:
                embed.add_field(name=name[0], value=f"{x} {name[1]}")
        embed.add_field(name="X-ray Fluorescence", value=self.get_xray_wavelength(element))
        discovery = (
            f"{element.discoverers} ({element.discovery_year}) in {element.discovery_location}"
        )
        embed.add_field(name="Discovery", value=discovery)

        return embed
