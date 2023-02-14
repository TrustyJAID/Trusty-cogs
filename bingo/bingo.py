import asyncio
import functools
import logging
import random
import re
import textwrap
from io import BytesIO
from typing import List, Optional, Pattern, Tuple

import aiohttp
import discord
from PIL import Image, ImageColor, ImageDraw, ImageFont
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

from .converter import Stamp

log = logging.getLogger("red.trusty-cogs.bingo")

IMAGE_LINKS: Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?:png|jpg|jpeg)(\?size=[0-9]*)?)", flags=re.I
)


class Bingo(commands.Cog):

    __version__ = "1.0.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(
            tiles=[],
            stamp_colour="#e6d705",
            text_colour="#FFFFFF",
            background_colour="#FFFFFF",
            box_colour="#000000",
            watermark=None,
            icon=None,
            name="",
        )
        self.config.register_member(stamps=[])

    @commands.group(name="bingoset")
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def bingoset(self, ctx: commands.Context):
        """
        Commands for setting bingo settings
        """
        pass

    @bingoset.command(name="stamp")
    async def bingoset_stamp(self, ctx: commands.Context, colour: discord.Colour):
        """
        Set the colour of the "stamp" that fills the box.

        `colour` - must be a hex colour code
        """
        await self.config.guild(ctx.guild).stamp_colour.set(str(colour))
        await ctx.send(f"The Bingo card stamp has been set to {colour}")

    @bingoset.command(name="name")
    async def bingoset_name(self, ctx: commands.Context, *, name: str):
        """
        Set the name of the current bingo card.

        `name` - the name you want to use for the current bingo card.
        """
        await self.config.guild(ctx.guild).name.set(name)
        await ctx.send(f"The Bingo card name has been set to {name}")

    @bingoset.command(name="text")
    async def bingoset_text(self, ctx: commands.Context, colour: discord.Colour):
        """
        Set the colour of the text.

        `colour` - must be a hex colour code
        """
        await self.config.guild(ctx.guild).text_colour.set(str(colour))
        await ctx.send(f"The Bingo card text has been set to {colour}")

    @bingoset.command(name="background")
    async def bingoset_background(self, ctx: commands.Context, colour: discord.Colour):
        """
        Set the colour of the Bingo card background.

        `colour` - must be a hex colour code
        """
        await self.config.guild(ctx.guild).background_colour.set(str(colour))
        await ctx.send(f"The Bingo card background has been set to {colour}")

    @bingoset.command(name="box")
    async def bingoset_box(self, ctx: commands.Context, colour: discord.Colour):
        """
        Set the colour of the Bingo card boxes border.

        `colour` - must be a hex colour code
        """
        await self.config.guild(ctx.guild).box_colour.set(str(colour))
        await ctx.send(f"The Bingo card box colour has been set to {colour}")

    @bingoset.command(name="watermark")
    async def bingoset_watermark(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Add a watermark image to the bingo card
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the bingo watermark.")
            await self.config.guild(ctx.guild).watermark.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            filename = image.filename
            await image.save(cog_data_path(self) / filename)
            await self.config.guild(ctx.guild).watermark.set(filename)
            await ctx.send("Saved the image as a watermark.")
        else:
            if not IMAGE_LINKS.search(image_url):
                await ctx.send("That is not a valid image URL. It must be either jpg or png.")
                return
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    data = await resp.read()
            ext = image_url.split(".")[-1]
            filename = f"{ctx.message.id}.{ext[:3] if 'jpeg' not in ext.lower() else ext[:4]}"
            with open(cog_data_path(self) / filename, "wb") as outfile:
                outfile.write(data)
            await self.config.guild(ctx.guild).watermark.set(filename)
            await ctx.send("Saved the image as a watermark.")

    @bingoset.command(name="icon")
    async def bingoset_icon(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Add an icon image to the bingo card
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the bingo icon.")
            await self.config.guild(ctx.guild).icon.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            filename = image.filename
            await image.save(cog_data_path(self) / filename)
            await self.config.guild(ctx.guild).icon.set(filename)
            await ctx.send("Saved the image as an icon.")
        else:
            if not IMAGE_LINKS.search(image_url):
                await ctx.send("That is not a valid image URL. It must be either jpg or png.")
                return
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    data = await resp.read()
            ext = image_url.split(".")[-1]
            filename = f"{ctx.message.id}.{ext[:3] if 'jpeg' not in ext.lower() else ext[:4]}"
            with open(cog_data_path(self) / filename, "wb") as outfile:
                outfile.write(data)
            await self.config.guild(ctx.guild).icon.set(filename)
            await ctx.send("Saved the image as an icon.")

    @bingoset.command(name="reset")
    async def bingoset_reset(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """
        Reset a users bingo card or reset the whole servers bingo card.
        """
        if member is None:
            await self.config.clear_all_members(guild=ctx.guild)
            await ctx.send("Reseting everyone's bingo card.")
        else:
            await self.config.member(member).clear()
            await ctx.send(
                f"Resetting {member.mention}'s bingo card.",
                allowed_mentions=discord.AllowedMentions(users=False),
            )

    @bingoset.command(name="clear")
    async def bingoset_clear(self, ctx: commands.Context):
        """
        Clear out the current bingo cards tiles.
        """
        await self.config.guild(ctx.guild).tiles.clear()
        await ctx.send("I have reset the servers bingo card tiles.")

    @bingoset.command(name="settings")
    async def bingoset_settings(self, ctx: commands.Context):
        """
        Show the current bingo card settings
        """
        settings = await self.get_card_options(ctx)
        msg = ""
        for k, v in settings.items():
            if k == "watermark":
                v = await self.config.guild(ctx.guild).watermark()
            if k == "icon":
                v = await self.config.guild(ctx.guild).icon()
            name = k.split("_")[0]
            msg += f"{name.title()}: `{v}`\n"
        await ctx.maybe_send_embed(msg)

    @bingoset.command(name="tiles")
    async def bingoset_tiles(self, ctx: commands.Context, *, tiles: str):
        """
        Set the tiles for the servers bingo cards.

        `tiles` - Separate each tile with `;`
        """
        options = set(tiles.split(";"))
        if len(options) < 24:
            await ctx.send("You must provide exactly 24 tile options to make a bingo card.")
            return
        options = sorted(options)
        await self.config.guild(ctx.guild).tiles.set(options)
        await self.config.clear_all_members(guild=ctx.guild)
        card_settings = await self.get_card_options(ctx)
        file = await self.create_bingo_card(options, **card_settings)
        await ctx.send("Here's how your bingo cards will appear", file=file)

    async def check_stamps(self, stamps: List[Tuple[int, int]]) -> bool:
        """
        Checks if the users current stamps warrants a bingo!
        """
        results = {
            "x": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
            "y": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
            "right_diag": 0,
            "left_diag": 0,
        }
        stamps.append([2, 2])  # add the Free Space here
        for stamp in stamps:
            x, y = stamp
            results["x"][x] += 1
            results["y"][y] += 1
            if stamp in [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]:
                results["right_diag"] += 1
            if stamp in [[4, 0], [3, 1], [2, 2], [1, 3], [0, 4]]:
                results["left_diag"] += 1
        if results["right_diag"] == 5 or results["left_diag"] == 5:
            return True
        if any(i == 5 for i in results["x"].values()):
            return True
        if any(i == 5 for i in results["y"].values()):
            return True
        return False

    @commands.command(name="bingo")
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    async def bingo(self, ctx: commands.Context, stamp: Optional[Stamp] = None):
        """
        Generate a Bingo Card

        `stamp` - Select the tile that you would like to stamp. If not
        provided will just show your current bingo card.
        """
        tiles = await self.config.guild(ctx.guild).tiles()
        stamps = await self.config.member(ctx.author).stamps()
        msg = None
        if stamp is not None:
            if stamp in stamps:
                stamps.remove(stamp)
            else:
                stamps.append(stamp)
            await self.config.member(ctx.author).stamps.set(stamps)
        if await self.check_stamps(stamps):
            msg = f"{ctx.author.mention} has a bingo!"

        # perm = self.nth_permutation(ctx.author.id, 24, tiles)
        random.seed(ctx.author.id)
        random.shuffle(tiles)
        card_settings = await self.get_card_options(ctx)
        temp = await self.create_bingo_card(
            tiles, stamps=stamps, guild_name=ctx.guild.name, **card_settings
        )
        await ctx.send(
            content=msg,
            file=temp,
            allowed_mentions=discord.AllowedMentions(users=False),
        )

    async def get_card_options(self, ctx: commands.Context) -> dict:
        ret = {
            "background_colour": await self.config.guild(ctx.guild).background_colour(),
            "text_colour": await self.config.guild(ctx.guild).text_colour(),
            "stamp_colour": await self.config.guild(ctx.guild).stamp_colour(),
            "box_colour": await self.config.guild(ctx.guild).box_colour(),
            "name": await self.config.guild(ctx.guild).name(),
        }
        if watermark := await self.config.guild(ctx.guild).watermark():
            ret["watermark"] = Image.open(cog_data_path(self) / watermark)
        if icon := await self.config.guild(ctx.guild).icon():
            ret["icon"] = Image.open(cog_data_path(self) / icon)
        return ret

    async def create_bingo_card(
        self,
        tiles: List[str],
        name: str = "",
        guild_name: str = "",
        background_colour: str = "#FFFFFF",
        text_colour: str = "#FFFFFF",
        stamp_colour: str = "#E9072B",
        box_colour: str = "#000000",
        watermark: Optional[Image.Image] = None,
        icon: Optional[Image.Image] = None,
        stamps: List[Tuple[int, int]] = [],
    ) -> Optional[discord.File]:
        task = functools.partial(
            self._create_bingo_card,
            options=tiles,
            name=name,
            guild_name=guild_name,
            background_colour=background_colour,
            text_colour=text_colour,
            stamp_colour=stamp_colour,
            box_colour=box_colour,
            watermark=watermark,
            icon=icon,
            stamps=stamps,
        )
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            return await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            log.error("There was an error generating the bingo card")
            return None

    def _create_bingo_card(
        self,
        options: List[str],
        name: str = "",
        guild_name: str = "",
        background_colour: str = "#FFFFFF",
        text_colour: str = "#FFFFFF",
        stamp_colour: str = "#FF0000",
        box_colour: str = "#000000",
        watermark: Optional[Image.Image] = None,
        icon: Optional[Image.Image] = None,
        stamps: List[Tuple[int, int]] = [],
    ):
        base_height, base_width = 1000, 700
        base = Image.new("RGBA", (base_width, base_height), color=background_colour)
        draw = ImageDraw.Draw(base)
        font_path = str(bundled_data_path(self) / "SourceSansPro-SemiBold.ttf")
        font = ImageFont.truetype(font=font_path, size=180)
        font2 = ImageFont.truetype(font=font_path, size=20)
        font3 = ImageFont.truetype(font=font_path, size=30)
        credit_font = ImageFont.truetype(font=font_path, size=10)
        draw.text(
            (690, 975),
            f"Bingo Cog written by TrustyJAID#0001\nBingo card colours and images provided by {guild_name} moderators",
            fill=text_colour,
            stroke_width=1,
            align="right",
            stroke_fill="black",
            anchor="rs",
            font=credit_font,
        )
        if watermark is not None:
            watermark = watermark.convert("RGBA")
            # https://stackoverflow.com/a/72983761
            wm = watermark.copy()
            wm.putalpha(128)
            watermark.paste(wm, watermark)
            # watermark.putalpha(128)

            # https://stackoverflow.com/a/56868633
            x1 = int(0.5 * base.size[0]) - int(0.5 * watermark.size[0])
            y1 = int(0.5 * base.size[1]) - int(0.5 * watermark.size[1])
            x2 = int(0.5 * base.size[0]) + int(0.5 * watermark.size[0])
            y2 = int(0.5 * base.size[1]) + int(0.5 * watermark.size[1])
            base.alpha_composite(watermark, (x1, y1))
        if icon is not None:
            icon = icon.convert("RGBA")
            icon.thumbnail((90, 90), Image.LANCZOS)
            base.paste(icon, (305, 905), icon)

        letter_count = 0
        for letter in "BINGO":
            scale = 130
            letter_x = 85 + (scale * letter_count)
            letter_y = 150
            draw.text(
                (letter_x, letter_y),
                letter,
                fill=text_colour,
                stroke_width=4,
                stroke_fill="black",
                anchor="ms",
                font=font,
            )
            letter_count += 1
        log.info(name)
        draw.text(
            (350, 200),
            name,
            fill=text_colour,
            stroke_width=1,
            stroke_fill="black",
            anchor="ms",
            font=font3,
        )
        count = 0
        for x in range(5):
            for y in range(5):
                scale = 130
                x0 = 25 + (scale * x)
                x1 = x0 + scale
                y0 = 250 + (scale * y)
                y1 = y0 + scale
                if x == 2 and y == 2:
                    text = "Free Space"
                else:
                    try:
                        text = options[count]
                    except IndexError:
                        text = "Free Space"
                    count += 1
                draw.rectangle((x0, y0, x1, y1), outline=box_colour)
                if [x, y] in stamps or [x, y] == [2, 2]:
                    log.info(f"Filling square {x} {y}")
                    colour = list(ImageColor.getrgb(stamp_colour))
                    colour.append(128)
                    nb = base.copy()
                    nd = ImageDraw.Draw(nb)
                    nd.ellipse((x0 + 5, y0 + 5, x1 - 5, y1 - 5), fill=tuple(colour))
                    base.alpha_composite(nb, (0, 0))

                if len(text) > 60:
                    text = text[:57] + "..."

                lines = textwrap.wrap(text, width=13)
                font_height = font2.getsize(text)[1]
                text_x = x0 + int(scale / 2)
                text_y = y0 + (int(scale / 2) - ((len(lines) / 3) * font_height))

                for line in lines:
                    draw.text(
                        (text_x, text_y),
                        line,
                        fill=text_colour,
                        stroke_width=1,
                        stroke_fill="black",
                        anchor="ms",
                        font=font2,
                    )
                    text_y += font_height

        temp = BytesIO()
        base.save(temp, format="png", optimize=True)
        temp.seek(0)
        return discord.File(temp, filename="bingo.png")
