from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

import aiohttp
import discord
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import checks, commands
from redbot.core.utils.views import SetApiView, SimpleMenu

BASE_URL = "https://api.imgflip.com/"
SEARCH_URL = BASE_URL + "get_memes"
CAPTION_URL = BASE_URL + "caption_image"

log = getLogger("red.trusty-cogs.ImgFlip")


@dataclass
class Box:
    text: str
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    color: Optional[str] = None
    outline_color: Optional[str] = None


@dataclass
class Meme:
    id: int
    name: Optional[str]
    url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    box_count: Optional[int]

    def __str__(self):
        if self.name:
            return f"{self.name} ({self.id})"
        return f"{self.id}"

    @classmethod
    def from_json(cls, data: dict) -> Meme:
        return cls(
            id=int(data["id"]),
            name=data["name"],
            url=data["url"],
            width=data["width"],
            height=data["height"],
            box_count=data["box_count"],
        )

    async def caption_image(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        text0: str,
        text1: str,
        font: Optional[Literal["arial", "impact"]] = None,
        max_font_size: Optional[int] = None,
        no_watermark: Optional[bool] = None,
    ):
        try:
            form_data = aiohttp.FormData()
            form_data.add_field("template_id", self.id)
            form_data.add_field("username", username)
            form_data.add_field("password", password)
            form_data.add_field("text0", text0)
            form_data.add_field("text1", text1)
            if font is not None:
                form_data.add_field("font", font)
            if max_font_size is not None:
                form_data.add_field("max_font_size", max_font_size)
            if no_watermark is not None:
                form_data.add_field("no_watermark", no_watermark)

            async with session.post(CAPTION_URL, data=form_data) as r:
                result = await r.json()
            if not result["success"]:
                raise ImgFlipAPIError(result["error_message"])
        except Exception as e:
            log.error("Error grabbing meme", exc_info=True)
            raise ImgFlipAPIError(e)
        return result["data"]["url"]

    async def caption_image_boxes(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        boxes: List[Box],
        font: Optional[Literal["arial", "impact"]] = None,
        max_font_size: Optional[int] = None,
        no_watermark: Optional[bool] = None,
    ) -> str:
        log.trace(boxes)
        try:
            form_data = aiohttp.FormData()
            form_data.add_field("template_id", self.id)
            form_data.add_field("username", username)
            form_data.add_field("password", password)
            if font is not None:
                form_data.add_field("font", font)
            if max_font_size is not None:
                form_data.add_field("max_font_size", max_font_size)
            if no_watermark is not None:
                form_data.add_field("no_watermark", no_watermark)
            i = 0
            for box in boxes:
                for k, v in box.__dict__.items():
                    if v is not None:
                        form_data.add_field(f"boxes[{i}][{k}]", v)
                i += 1

            async with session.post(CAPTION_URL, data=form_data) as r:
                result = await r.json()
            if not result["success"]:
                raise ImgFlipAPIError(result["error_message"])
        except Exception as e:
            log.error("Error grabbing meme", exc_info=True)
            raise ImgFlipAPIError(e)
        return result["data"]["url"]


class Memes(discord.app_commands.Transformer):
    def __init__(self):
        self.meme_list: Dict[str, Meme] = {}
        self.choice_list: List[discord.app_commands.Choice] = []

    async def get_memes(self, session: aiohttp.ClientSession):
        async with session.get(SEARCH_URL) as resp:
            results = await resp.json()
        for meme in results["data"]["memes"]:
            self.meme_list[meme["id"]] = Meme.from_json(meme)
            self.choice_list.append(
                discord.app_commands.Choice(name=meme["name"], value=meme["id"])
            )

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        if not self.meme_list:
            cog: Optional[Imgflip] = interaction.client.get_cog("Imgflip")
            if cog is None:
                return []
            await self.get_memes(cog.session)
        return [i for i in self.choice_list if current.lower() in i.name.lower()][:25]

    async def transform(self, interaction: discord.Interaction, argument: str):
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def convert(self, ctx: commands.Context, argument: str) -> Meme:
        result = None
        if not self.meme_list:
            cog: Optional[Imgflip] = ctx.bot.get_cog("Imgflip")
            if cog is None:
                raise BadArgument()
                # this shouldn't happen
            await self.get_memes(cog.session)
        if not argument.isdigit():
            for memes in self.meme_list.values():
                if argument.lower() in memes.name.lower():
                    result = memes
            if result is None:
                raise BadArgument('Meme "{}" not found'.format(argument))
        else:
            result = self.meme_list.get(str(argument))

        if result is None:
            result = Meme(
                id=int(argument), name=None, url=None, width=None, height=None, box_count=None
            )
        return result


class ImgFlipAPIError(Exception):
    """ImgFlip API Error"""

    pass


class Imgflip(commands.Cog):
    """
    Generate memes from imgflip.com API
    """

    __author__ = ["Twentysix", "TrustyJAID"]
    __version__ = "3.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Red-TrustyCogs-imgflip"})

    async def cog_unload(self):
        if not self.session.closed:
            await self.session.close()

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

    @commands.command(alias=["listmemes"])
    @commands.bot_has_permissions(embed_links=True)
    async def getmemes(self, ctx: commands.Context) -> None:
        """List memes with names that can be used"""
        await ctx.typing()
        pages = await self.get_memes()
        menu = SimpleMenu(pages, use_select_menu=True)
        await menu.start(ctx)

    async def get_memes(self) -> List[discord.Embed]:
        async with self.session.get(SEARCH_URL) as r:
            results = await r.json()
        pages = []
        text = ""
        count = 0
        embed = discord.Embed()
        templates = (
            "\nFind a meme at <https://imgflip.com/memetemplates> - "
            "click `Blank Template` and get the Template ID for more!"
        )
        embed.add_field(name="Details", value=templates)
        for meme in results["data"]["memes"]:
            if count == 10:
                embed.description = text
                pages.append(embed)
                embed = embed.copy()
                count = 0
                text = ""
            url = meme["url"]
            name = meme["name"]
            meme_id = meme["id"]
            text += f"- [{name}]({url})\n - Template ID: `{meme_id}`\n"
            count += 1
        embed.description = text
        pages.append(embed)
        return pages

    @commands.hybrid_command()
    async def meme(
        self,
        ctx: commands.Context,
        meme: discord.app_commands.Transform[Meme, Memes],
        *,
        text: str,
    ) -> None:
        """Create custom memes from imgflip

        - `<meme>` can be the name of the meme to use or the ID from imgflip
        - `<text>` is lines of text separated by `|`
        > You can customize the colour and outline colour by adding `colour=#ff00ff`
        > or `outline_colour=#f1c40f` to your text. Both `color` and `colour` are acceptable.
        > You can also customize the font with `font=arial` or `font=impact`.
        > By default imgflip will use impact.

        Do `[p]getmemes` to see which meme names will work

        You can get meme ID's from https://imgflip.com/memetemplates
        click blank template and use the Template ID in place of meme_name
        """
        async with ctx.typing():
            user_pass = await self.bot.get_shared_api_tokens("imgflip")
            username = user_pass.get("username")
            password = user_pass.get("password")
            if not username or not password:
                await ctx.send(
                    "You need to set a username and password first with "
                    f"`{ctx.prefix}{self.imgflip_set.qualified_name}`"
                )
                return
            search_text: List[str] = re.split(r"\|", text)
            mod_search = re.compile(
                r"(?P<font>font=(arial|impact))|(?P<colours>(?P<outline>outline_)?colou?r=(?P<colour>#[0-9A-Fa-f]{3,6}))"
            )
            boxes = []
            font: Literal["impact", "arial"] = "impact"
            for text in search_text:
                colour = "#ffffff"
                outline_colour = "#000000"
                new_text = text
                for match in mod_search.finditer(text):
                    if match.group("colours"):
                        if match.group("outline"):
                            outline_colour = match.group("colour")
                        else:
                            colour = match.group("colour")
                    if match.group("font"):
                        font: Literal["arial", "impact"] = match.group("font")  # type: ignore
                    new_text = new_text.replace(match.group(), "").strip()

                log.debug("colour=%s outline_colour=%s font=%s", colour, outline_colour, font)
                boxes.append(Box(text=new_text, color=colour, outline_color=outline_colour))
            try:
                url = await meme.caption_image_boxes(
                    self.session, username=username, password=password, boxes=boxes, font=font
                )
            except ImgFlipAPIError as e:
                await ctx.send(
                    f"Something went wrong generating an image for the meme `{meme}`. `{e}`"
                )
                return

        await ctx.send(url)

    @commands.command(name="imgflipset", aliases=["memeset"])
    @checks.is_owner()
    async def imgflip_set(self, ctx: commands.Context) -> None:
        """Command for setting required access information for the API"""
        keys = {"username": "", "password": ""}
        view = SetApiView("imgflip", keys)
        msg = await ctx.send(
            "Set your Username and Password for <https://imgflip.com>.", view=view
        )
        await view.wait()
        await msg.edit(view=None)
