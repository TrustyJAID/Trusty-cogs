import asyncio
import functools
import random
import re
import sys
import textwrap
from io import BytesIO
from typing import List, Optional, Pattern, Tuple

import aiohttp
import discord
from PIL import Image, ImageColor, ImageDraw, ImageFont
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

from .converter import Stamp

log = getLogger("red.trusty-cogs.bingo")

IMAGE_LINKS: Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?:png|jpg|jpeg)(\?size=[0-9]*)?)", flags=re.I
)


class Bingo(commands.Cog):
    __version__ = "1.2.2"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(
            tiles=[],
            stamp_colour="#e6d705",
            text_colour="#FFF8E7",
            textborder_colour="#333333",
            background_colour="#010028",
            box_colour="#FFF8E7",
            watermark=None,
            icon=None,
            background_tile=None,
            name="",
            bingo="BINGO",
            seed=0,
        )
        self.config.register_member(stamps=[])

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete. Information saved is a set of points on a bingo card and
        does not represent end user data.
        """
        return

    @commands.group(name="bingoset")
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def bingoset(self, ctx: commands.Context):
        """
        Commands for setting bingo settings
        """
        pass

    @bingoset.command(name="stamp")
    async def bingoset_stamp(self, ctx: commands.Context, colour: Optional[discord.Colour] = None):
        """
        Set the colour of the "stamp" that fills the box.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).stamp_colour.clear()
        else:
            await self.config.guild(ctx.guild).stamp_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).stamp_colour()
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
    async def bingoset_text(self, ctx: commands.Context, colour: Optional[discord.Colour] = None):
        """
        Set the colour of the text.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).text_colour.clear()
        else:
            await self.config.guild(ctx.guild).text_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).text_colour()
        await ctx.send(f"The Bingo card text has been set to {colour}")

    @bingoset.command(name="background")
    async def bingoset_background(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = None
    ):
        """
        Set the colour of the Bingo card background.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).background_colour.clear()
        else:
            await self.config.guild(ctx.guild).background_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).background_colour()
        await ctx.send(f"The Bingo card background has been set to {colour}")

    @bingoset.command(name="box")
    async def bingoset_box(self, ctx: commands.Context, colour: Optional[discord.Colour] = None):
        """
        Set the colour of the Bingo card boxes border.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).box_colour.clear()
        else:
            await self.config.guild(ctx.guild).box_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).box_colour()
        await ctx.send(f"The Bingo card box colour has been set to {colour}")

    @bingoset.command(name="bingo")
    async def bingoset_bingo(self, ctx: commands.Context, bingo: str):
        """
        Set the "BINGO" of the board.

        `bingo` - The word to use for bingo. Must be exactly 5 characters.
        """
        if len(set(list(bingo))) != 5:
            await ctx.send(
                "The 'BINGO' must be exactly 5 characters and contain no identical characters."
            )
            return
        await self.config.guild(ctx.guild).bingo.set(bingo.upper())
        await ctx.send(f"The 'BINGO' has been set to `{bingo.upper()}`")

    @bingoset.command(name="watermark")
    async def bingoset_watermark(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Add a watermark image to the bingo card

        `[image_url]` - Must be an image url with `.jpg` or `.png` extension.
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the bingo watermark.")
            await self.config.guild(ctx.guild).watermark.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            ext = image.filename.split(".")[-1]
            filename = f"{ctx.guild.id}-watermark.{ext}"
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
            filename = f"{ctx.guild.id}-watermark.{ext}"
            with open(cog_data_path(self) / filename, "wb") as outfile:
                outfile.write(data)
            await self.config.guild(ctx.guild).watermark.set(filename)
            await ctx.send("Saved the image as a watermark.")

    @bingoset.command(name="icon")
    async def bingoset_icon(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Add an icon image to the bingo card

        `[image_url]` - Must be an image url with `.jpg` or `.png` extension.
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the bingo icon.")
            await self.config.guild(ctx.guild).icon.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            ext = image.filename.split(".")[-1]
            filename = f"{ctx.guild.id}-icon.{ext}"
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
            filename = f"{ctx.guild.id}-icon.{ext}"
            with open(cog_data_path(self) / filename, "wb") as outfile:
                outfile.write(data)
            await self.config.guild(ctx.guild).icon.set(filename)
            await ctx.send("Saved the image as an icon.")

    @bingoset.command(name="bgtile")
    async def bingoset_bgtile(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Set the background image (tiled).

        This will override the background colour if set as it will attempt
        to tile the image over the entire background.

        `[image_url]` - Must be an image url with `.jpg` or `.png` extension.
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the bingo background image.")
            await self.config.guild(ctx.guild).background_tile.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            ext = image.filename.split(".")[-1]
            filename = f"{ctx.guild.id}-bgtile.{ext}"
            await image.save(cog_data_path(self) / filename)
            await self.config.guild(ctx.guild).background_tile.set(filename)
            await ctx.send("Saved the image as an background tile.")
            return
        else:
            if not IMAGE_LINKS.search(image_url):
                await ctx.send("That is not a valid image URL. It must be either jpg or png.")
                return
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    data = await resp.read()
            ext = image_url.split(".")[-1]
            filename = f"{ctx.guild.id}-bgtile.{ext}"
            with open(cog_data_path(self) / filename, "wb") as outfile:
                outfile.write(data)
            await self.config.guild(ctx.guild).background_tile.set(filename)
            await ctx.send("Saved the image as the background tile.")

    @bingoset.command(name="reset")
    async def bingoset_reset(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """
        Reset a users bingo card or reset the whole servers bingo card.
        """
        if member is None:
            await self.config.clear_all_members(guild=ctx.guild)
            await ctx.send("Resetting everyone's bingo card.")
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

    @bingoset.command(name="seed")
    async def bingoset_seed(self, ctx: commands.Context, seed: int):
        """
        Set an additional seed to the randomness of players cards.

        `seed` - A number that is added to the player ID used to
        seed their card.

        Use this to shuffle everyone's card while keeping the exact
        same tiles for a game of bingo. Default is 0.
        """
        if seed >= sys.maxsize >> 1 or seed <= (-1 * sys.maxsize >> 1):
            await ctx.send("That seed is too large, choose a smaller number.")
            return
        await self.config.guild(ctx.guild).seed.set(seed)
        await ctx.send("I have saved the additional seed to the players cards.")

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
            if k == "background_tile":
                v = await self.config.guild(ctx.guild).background_tile()
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
        seed = int(await self.config.guild(ctx.guild).seed()) + ctx.author.id
        random.seed(seed)
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
            "textborder_colour": await self.config.guild(ctx.guild).textborder_colour(),
            "stamp_colour": await self.config.guild(ctx.guild).stamp_colour(),
            "box_colour": await self.config.guild(ctx.guild).box_colour(),
            "name": await self.config.guild(ctx.guild).name(),
            "bingo": await self.config.guild(ctx.guild).bingo(),
        }
        if watermark := await self.config.guild(ctx.guild).watermark():
            ret["watermark"] = Image.open(cog_data_path(self) / watermark)
        if icon := await self.config.guild(ctx.guild).icon():
            ret["icon"] = Image.open(cog_data_path(self) / icon)
        if background_tile := await self.config.guild(ctx.guild).background_tile():
            ret["background_tile"] = Image.open(cog_data_path(self) / background_tile)
        return ret

    async def create_bingo_card(
        self,
        tiles: List[str],
        name: str,
        guild_name: str,
        bingo: str,
        background_colour: str,
        text_colour: str,
        textborder_colour: str,
        stamp_colour: str,
        box_colour: str,
        watermark: Optional[Image.Image] = None,
        icon: Optional[Image.Image] = None,
        background_tile: Optional[Image.Image] = None,
        stamps: List[Tuple[int, int]] = [],
    ) -> Optional[discord.File]:
        task = functools.partial(
            self._create_bingo_card,
            options=tiles,
            name=name,
            guild_name=guild_name,
            bingo=bingo,
            background_colour=background_colour,
            text_colour=text_colour,
            textborder_colour=textborder_colour,
            stamp_colour=stamp_colour,
            box_colour=box_colour,
            watermark=watermark,
            icon=icon,
            background_tile=background_tile,
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
        name: str,
        guild_name: str,
        bingo: str,
        background_colour: str,
        text_colour: str,
        textborder_colour: str,
        stamp_colour: str,
        box_colour: str,
        watermark: Optional[Image.Image] = None,
        icon: Optional[Image.Image] = None,
        background_tile: Optional[Image.Image] = None,
        stamps: List[Tuple[int, int]] = [],
    ):
        base_height, base_width = 1000, 700
        base = Image.new("RGBA", (base_width, base_height), color=background_colour)
        draw = ImageDraw.Draw(base)
        if background_tile:
            # https://stackoverflow.com/a/69807463
            bg_x, bg_y = background_tile.size
            for i in range(0, base_width, bg_x):
                for j in range(0, base_height, bg_y):
                    base.paste(background_tile, (i, j))
        font_path = str(bundled_data_path(self) / "SourceSansPro-SemiBold.ttf")
        font = ImageFont.truetype(font=font_path, size=180)
        font2 = ImageFont.truetype(font=font_path, size=20)
        font3 = ImageFont.truetype(font=font_path, size=30)
        credit_font = ImageFont.truetype(font=font_path, size=10)
        draw.text(
            (690, 975),
            f"Bingo Cog written by @trustyjaid\nBingo card colours and images provided by {guild_name} moderators",
            fill=text_colour,
            stroke_width=1,
            align="right",
            stroke_fill=textborder_colour,
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
        for letter in bingo:
            scale = 130
            letter_x = 85 + (scale * letter_count)
            letter_y = 150
            draw.text(
                (letter_x, letter_y),
                letter,
                fill=text_colour,
                stroke_width=4,
                stroke_fill=textborder_colour,
                anchor="ms",
                font=font,
            )
            letter_count += 1
        log.trace("_create_bingo_card name: %s", name)
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
                    log.info("Filling square %s %s", x, y)
                    colour = list(ImageColor.getrgb(stamp_colour))
                    colour.append(128)
                    nb = base.copy()
                    nd = ImageDraw.Draw(nb)
                    nd.ellipse((x0 + 5, y0 + 5, x1 - 5, y1 - 5), fill=tuple(colour))
                    base.alpha_composite(nb, (0, 0))

                if len(text) > 60:
                    text = text[:57] + "..."

                lines = textwrap.wrap(text, width=13)
                font_height = font2.getbbox(text)[3] - font2.getbbox(text)[1]
                text_x = x0 + int(scale / 2)
                if len(lines) > 1:
                    text_y = y0 + (int(scale / 2) - ((len(lines) / 3) * font_height))
                else:
                    text_y = y0 + (int(scale / 2))

                for line in lines:
                    draw.text(
                        (text_x, text_y),
                        line,
                        fill=text_colour,
                        stroke_width=1,
                        stroke_fill=textborder_colour,
                        anchor="ms",
                        font=font2,
                    )
                    text_y += font_height

        temp = BytesIO()
        base.save(temp, format="webp", optimize=True)
        temp.seek(0)
        return discord.File(temp, filename="bingo.webp")
