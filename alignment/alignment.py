from __future__ import annotations

import asyncio
import functools
import random
import re
import textwrap
from io import BytesIO
from typing import Optional, Pattern

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

from .converter import Alignment, AlignmentFlags, GoodVsEvil, LawVsChaos

log = getLogger("red.trusty-cogs.alignment")

IMAGE_LINKS: Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?:png|jpg|jpeg)(\?size=[0-9]*)?)", flags=re.I
)


class Alignments(commands.Cog):
    __version__ = "1.0.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(
            stamp_colour="#e6d705",
            text_colour="#FFF8E7",
            textborder_colour="#333333",
            background_colour="#010028",
            box_colour="#FFF8E7",
            watermark=None,
            background_tile=None,
        )

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.command(name="alignment")
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True, read_message_history=True)
    async def alignment(self, ctx: commands.Context, *, alignments: AlignmentFlags):
        """
        Generate a Alignment Card

        `alignments` - Who or what is the specific alignment?
        - `lg:` Lawful Good.
        - `ln:` Lawful Neutral.
        - `le:` Lawful Evil.
        - `ng:` Neutral Good.
        - `nn:` Neutral Neutral.
        - `ne:` Neutral Evil.
        - `cg:` Chaotic Good.
        - `cn:` Chaotic Neutral.
        - `ce:` Chaotic Evil.
        """
        msg = None
        log.debug(alignments)
        # perm = self.nth_permutation(ctx.author.id, 24, tiles)
        users = set()
        alignments = await alignments.to_table()
        empty_alignments = []
        existing_users = set()
        for al, slot in alignments.items():
            if slot["text"] is None:
                empty_alignments.append(al)
            if slot["user_id"]:
                existing_users.add(slot["user_id"])
        async for message in ctx.channel.history(limit=50):
            if message.author not in users and message.author.id not in existing_users:
                users.add(message.author)
            if len(users) > 9:
                break

        for user in users:
            if len(empty_alignments) < 1:
                continue
            al = empty_alignments.pop(empty_alignments.index(random.choice(empty_alignments)))
            b = BytesIO()
            await user.display_avatar.save(b)
            image = Image.open(b).convert("RGBA")
            alignments[al]["text"] = user.display_name
            alignments[al]["image"] = image

        card_settings = await self.get_card_options(ctx)
        temp = await self.create_alignment_card(
            alignments, guild_name=ctx.guild.name, **card_settings
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
            "box_colour": await self.config.guild(ctx.guild).box_colour(),
        }
        if watermark := await self.config.guild(ctx.guild).watermark():
            ret["watermark"] = Image.open(cog_data_path(self) / watermark)
        if background_tile := await self.config.guild(ctx.guild).background_tile():
            ret["background_tile"] = Image.open(cog_data_path(self) / background_tile)
        return ret

    @commands.group(name="alignmentset")
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def alignmentset(self, ctx: commands.Context):
        """
        Commands for setting alignment settings
        """
        pass

    @alignmentset.command(name="text")
    async def alignmentset_text(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = None
    ):
        """
        Set the colour of the text.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).text_colour.clear()
        else:
            await self.config.guild(ctx.guild).text_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).text_colour()
        await ctx.send(f"The Alignment card text colour has been set to {colour}")

    @alignmentset.command(name="textborder")
    async def alignmentset_textborder(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = None
    ):
        """
        Set the colour of the text border.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).textborder_colour.clear()
        else:
            await self.config.guild(ctx.guild).textborder_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).textborder_colour()
        await ctx.send(f"The Alignment card text border colour has been set to {colour}")

    @alignmentset.command(name="background")
    async def alignmentset_background(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = None
    ):
        """
        Set the colour of the Alignment card background.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).background_colour.clear()
        else:
            await self.config.guild(ctx.guild).background_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).background_colour()
        await ctx.send(f"The Alignment card background has been set to {colour}.")

    @alignmentset.command(name="box")
    async def alignmentset_box(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = None
    ):
        """
        Set the colour of the Alignment card boxes border.

        `colour` - must be a hex colour code
        """
        if colour is None:
            await self.config.guild(ctx.guild).box_colour.clear()
        else:
            await self.config.guild(ctx.guild).box_colour.set(str(colour))
        colour = await self.config.guild(ctx.guild).box_colour()
        await ctx.send(f"The Alignment card box colour has been set to {colour}")

    @alignmentset.command(name="watermark")
    async def alignmentset_watermark(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Add a watermark image to the alignment card

        `[image_url]` - Must be an image url with `.jpg` or `.png` extension.
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the alignment watermark.")
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

    @alignmentset.command(name="bgtile")
    async def alignmentset_bgtile(self, ctx: commands.Context, image_url: Optional[str] = None):
        """
        Set the background image (tiled).

        This will override the background colour if set as it will attempt
        to tile the image over the entire background.

        `[image_url]` - Must be an image url with `.jpg` or `.png` extension.
        """
        if image_url is None and not ctx.message.attachments:
            await ctx.send("I have cleared the alignment background image.")
            await self.config.guild(ctx.guild).background_tile.clear()
            return
        elif image_url is None and ctx.message.attachments:
            image = ctx.message.attachments[0]
            ext = image.filename.split(".")[-1]
            filename = f"{ctx.guild.id}-bgtile.{ext}"
            await image.save(cog_data_path(self) / filename)
            await self.config.guild(ctx.guild).background_tile.set(filename)
            await ctx.send("Saved the image as an background tile.")
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

    @alignmentset.command(name="settings")
    async def alignmentset_settings(self, ctx: commands.Context):
        """
        Show the current alignment card settings
        """
        settings = await self.get_card_options(ctx)
        msg = ""
        for k, v in settings.items():
            if k == "watermark":
                v = await self.config.guild(ctx.guild).watermark()
            name = k.split("_")[0]
            msg += f"{name.title()}: `{v}`\n"
        await ctx.maybe_send_embed(msg)

    async def create_alignment_card(
        self,
        tiles: dict,
        guild_name: str,
        background_colour: str,
        text_colour: str,
        textborder_colour: str,
        box_colour: str,
        watermark: Optional[Image.Image] = None,
        background_tile: Optional[Image.Image] = None,
    ) -> Optional[discord.File]:
        task = functools.partial(
            self._create_alignment_card,
            options=tiles,
            guild_name=guild_name,
            background_colour=background_colour,
            text_colour=text_colour,
            textborder_colour=textborder_colour,
            box_colour=box_colour,
            watermark=watermark,
            background_tile=background_tile,
        )
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            return await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            log.error("There was an error generating the alignment card")
            return None

    def _create_alignment_card(
        self,
        options: dict,
        guild_name: str,
        background_colour: str,
        text_colour: str,
        textborder_colour: str,
        box_colour: str,
        watermark: Optional[Image.Image] = None,
        background_tile: Optional[Image.Image] = None,
    ):
        base_height, base_width = 650, 570
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
            (545, 615),
            f"Alignment Cog written by @trustyjaid\nAlignment card colours and images provided by {guild_name} moderators",
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
            watermark.thumbnail(
                (int(base.size[0] * 0.75), int(base.size[1] * 0.75)), Image.LANCZOS
            )
            # watermark.putalpha(128)

            # https://stackoverflow.com/a/56868633
            x1 = int(0.5 * base.size[0]) - int(0.5 * watermark.size[0])
            y1 = int(0.5 * base.size[1]) - int(0.5 * watermark.size[1])
            x2 = int(0.5 * base.size[0]) + int(0.5 * watermark.size[0])
            y2 = int(0.5 * base.size[1]) + int(0.5 * watermark.size[1])
            base.alpha_composite(watermark, (x1, y1))

        draw.text(
            (285, 50),
            f"{guild_name} Alignment Chart",
            fill=text_colour,
            stroke_width=1,
            stroke_fill=textborder_colour,
            anchor="ms",
            font=font3,
        )
        count = 0
        for x in range(4):
            # Lawful/Chaotic
            for y in range(4):
                # Good/Evil
                scale = 130
                x0 = 25 + (scale * x)
                x1 = x0 + scale
                y0 = 75 + (scale * y)
                y1 = y0 + scale
                try:
                    if y == 0:
                        align = LawVsChaos(x - 1)
                    elif x == 0:
                        align = GoodVsEvil(y - 1)
                    else:
                        align = Alignment(LawVsChaos(x - 1), GoodVsEvil(y - 1))
                except ValueError:
                    align = "Alignment"
                    pass
                bg_img = None
                table_input = {}
                if x == 0 or y == 0:
                    text = str(align)
                else:
                    try:
                        key = getattr(align, "short", None)
                        table_input = options.get(key, None)
                        if table_input is not None:
                            text = table_input["text"]
                            bg_img = table_input["image"]
                        else:
                            text = ""
                    except (IndexError, AttributeError):
                        text = ""
                    count += 1
                log.debug(f"{text=}")
                if bg_img and table_input:
                    log.info("Adding avatar background")
                    bg_img = bg_img.resize((130, 130), Image.LANCZOS)
                    bg_img.putalpha(128)
                    base.paste(bg_img, (x0, y0, x1, y1))

                draw.rectangle((x0, y0, x1, y1), outline=box_colour)
                if text is None:
                    text = ""
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
        return discord.File(temp, filename="alignment.webp")
