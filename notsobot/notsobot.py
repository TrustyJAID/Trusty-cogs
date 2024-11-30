# https://github.com/NotSoSuper/NotSoBot

import asyncio
import os
import random
import re
import sys
import textwrap
import uuid
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import quote

import aiohttp
import discord
import jpglitch
import numpy as np
import PIL
import wand
import wand.color
import wand.drawing
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence
from pyfiglet import figlet_format
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

from .converter import ImageFinder, TenorAPI
from .vw import macintoshplus

log = getLogger("red.trusty-cogs.NotSoBot")

try:
    import aalib

    AALIB_INSTALLED = True
except Exception:
    AALIB_INSTALLED = False

code = "```py\n{0}\n```"


def posnum(num):
    if num < 0:
        return -(num)
    else:
        return num


def find_coeffs(pa, pb):
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    A = np.matrix(matrix, dtype=np.float)
    B = np.array(pb).reshape(8)
    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)


class DataProtocol(asyncio.SubprocessProtocol):
    def __init__(self, exit_future):
        self.exit_future = exit_future
        self.output = bytearray()

    def pipe_data_received(self, fd, data):
        self.output.extend(data)

    def process_exited(self):
        try:
            self.exit_future.set_result(True)
        except Exception:
            pass

    def pipe_connection_lost(self, fd, exc):
        try:
            self.exit_future.set_result(True)
        except Exception:
            pass

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        try:
            self.exit_future.set_result(True)
        except Exception:
            pass


class NotSoBot(commands.Cog):
    """
    Rewrite of many NotSoBot commands to work on RedBot V3
    """

    __author__ = ["NotSoSuper", "TrustyJAID"]
    __version__ = "2.6.0"

    def __init__(self, bot):
        self.bot = bot
        self.image_cache = {}
        self.search_cache = {}
        self.youtube_cache = {}
        self.twitch_cache = []
        self.api_count = 0
        self.emoji_map = {
            "a": "\N{REGIONAL INDICATOR SYMBOL LETTER A}",
            "b": "\N{REGIONAL INDICATOR SYMBOL LETTER B}",
            "c": "\N{REGIONAL INDICATOR SYMBOL LETTER C}",
            "d": "\N{REGIONAL INDICATOR SYMBOL LETTER D}",
            "e": "\N{REGIONAL INDICATOR SYMBOL LETTER E}",
            "f": "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
            "g": "\N{REGIONAL INDICATOR SYMBOL LETTER G}",
            "h": "\N{REGIONAL INDICATOR SYMBOL LETTER H}",
            "i": "\N{REGIONAL INDICATOR SYMBOL LETTER I}",
            "j": "\N{REGIONAL INDICATOR SYMBOL LETTER J}",
            "k": "\N{REGIONAL INDICATOR SYMBOL LETTER K}",
            "l": "\N{REGIONAL INDICATOR SYMBOL LETTER L}",
            "m": "\N{REGIONAL INDICATOR SYMBOL LETTER M}",
            "n": "\N{REGIONAL INDICATOR SYMBOL LETTER N}",
            "o": "\N{REGIONAL INDICATOR SYMBOL LETTER O}",
            "p": "\N{REGIONAL INDICATOR SYMBOL LETTER P}",
            "q": "\N{REGIONAL INDICATOR SYMBOL LETTER Q}",
            "r": "\N{REGIONAL INDICATOR SYMBOL LETTER R}",
            "s": "\N{REGIONAL INDICATOR SYMBOL LETTER S}",
            "t": "\N{REGIONAL INDICATOR SYMBOL LETTER T}",
            "u": "\N{REGIONAL INDICATOR SYMBOL LETTER U}",
            "v": "\N{REGIONAL INDICATOR SYMBOL LETTER V}",
            "w": "\N{REGIONAL INDICATOR SYMBOL LETTER W}",
            "x": "\N{REGIONAL INDICATOR SYMBOL LETTER X}",
            "y": "\N{REGIONAL INDICATOR SYMBOL LETTER Y}",
            "z": "\N{REGIONAL INDICATOR SYMBOL LETTER Z}",
            "1": "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}",
            "2": "\N{DIGIT TWO}\N{COMBINING ENCLOSING KEYCAP}",
            "3": "\N{DIGIT THREE}\N{COMBINING ENCLOSING KEYCAP}",
            "4": "\N{DIGIT FOUR}\N{COMBINING ENCLOSING KEYCAP}",
            "5": "\N{DIGIT FIVE}\N{COMBINING ENCLOSING KEYCAP}",
            "6": "\N{DIGIT SIX}\N{COMBINING ENCLOSING KEYCAP}",
            "7": "\N{DIGIT SEVEN}\N{COMBINING ENCLOSING KEYCAP}",
            "8": "\N{DIGIT EIGHT}\N{COMBINING ENCLOSING KEYCAP}",
            "9": "\N{DIGIT NINE}\N{COMBINING ENCLOSING KEYCAP}",
            "0": "\N{DIGIT ZERO}\N{COMBINING ENCLOSING KEYCAP}",
            "$": "\N{HEAVY DOLLAR SIGN}",
            "!": "\N{HEAVY EXCLAMATION MARK SYMBOL}",
            "?": "\N{BLACK QUESTION MARK ORNAMENT}",
            " ": "　",
        }
        self.retro_regex = re.compile(
            r"((https)(\:\/\/|)?u2?\.photofunia\.com\/.\/results\/.\/.\/.*(\.jpg\?download))"
        )
        self.image_mimes = ["image/png", "image/pjpeg", "image/jpeg", "image/x-icon"]
        self.gif_mimes = ["image/gif"]
        self.tenor: Optional[TenorAPI] = None

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

    async def on_red_api_tokens_update(self, service_name: str, api_tokens: Dict[str, str]):
        if service_name != "tenor":
            return

        if "api_key" in api_tokens:
            if self.tenor is not None:
                self.tenor._token = api_tokens["api_key"]
                return
            self.tenor = TenorAPI(api_tokens["api_key"], str(self.bot.user))

    async def cog_load(self):
        asyncio.create_task(self.load_tenor())

    async def load_tenor(self):
        await self.bot.wait_until_red_ready()
        tokens = await self.bot.get_shared_api_tokens("tenor")
        if "api_key" in tokens:
            self.tenor = TenorAPI(tokens["api_key"], str(self.bot.user))

    async def cog_unload(self):
        if self.tenor:
            await self.tenor.session.close()

    def random_filename(self, image=False, ext: str = "png"):
        h = str(uuid.uuid4().hex)
        if image:
            return "{0}.{1}".format(h, ext)
        return h

    async def get_text(self, url: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    try:
                        text = await resp.text()
                        return text
                    except Exception:
                        return False
        except asyncio.TimeoutError:
            return False

    async def truncate(self, channel, msg):
        if len(msg) == 0:
            return
        split = [msg[i : i + 1999] for i in range(0, len(msg), 1999)]
        try:
            for s in split:
                await channel.send(s)
                await asyncio.sleep(0.21)
        except Exception as e:
            await channel.send(e)

    async def safe_send(self, ctx, text, file, file_size):
        if not ctx.channel.permissions_for(ctx.me).send_messages:
            return
        if not ctx.channel.permissions_for(ctx.me).attach_files:
            await ctx.send("I don't have permission to attach files.")
            return
        BASE_FILESIZE_LIMIT = 8388608
        if ctx.guild and file_size < ctx.guild.filesize_limit:
            await ctx.send(content=text, file=file)
        elif not ctx.guild and file_size < BASE_FILESIZE_LIMIT:
            await ctx.send(content=text, file=file)
        else:
            await ctx.send("The contents of this command is too large to upload!")

    @staticmethod
    async def determine_mime_type(image_header: str):
        if ("GIF89a" or "GIF87a") in image_header:
            return "image/gif"
        elif "\x89PNG" in image_header:
            return "image/png"
        elif "\xFF\xD8\xFF" in image_header:
            return "image/jpeg"
        elif "\x00\x00\x01\x00" in image_header:
            return "image/x-icon"
        else:
            return None

    async def get_headers(self, url: str) -> Dict[str, str]:
        headers = {}
        if "imgur.com" in url:
            tokens = await self.bot.get_shared_api_tokens("imgur")
            if "client_id" in tokens:
                client_id = tokens["client_id"]
                headers["Authorization"] = f"Client-ID {client_id}"
        return headers

    async def bytes_download(
        self, url: Union[discord.Asset, discord.Attachment, str]
    ) -> Tuple[Union[BytesIO, bool], Union[str, bool]]:
        if isinstance(url, discord.Asset) or isinstance(url, discord.Attachment):
            log.debug("Pulling data from discord")
            try:
                b = BytesIO()
                await url.save(b)
                mime = getattr(url, "content_type", "None")
                if mime == "None":
                    b.seek(0)
                    image_header = b.read()[:20]
                    mime = await self.determine_mime_type(str(image_header))
                return b, mime
            except discord.HTTPException:
                return False, False

        try:
            async with aiohttp.ClientSession() as session:
                headers = await self.get_headers(url)
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        mime = resp.headers.get("Content-type", "").lower()
                        b = BytesIO(data)
                        b.seek(0)
                        return b, mime
                    else:
                        log.error(
                            "%s HTTP Response Error downloading image from %s", resp.status, url
                        )
                        return False, False
        except asyncio.TimeoutError:
            return False, False
        except Exception:
            log.error("Error downloading to bytes", exc_info=True)
            return False, False

    def do_magik(self, scale, img):
        img.seek(0)
        try:
            list_imgs = []
            count = 0
            i = wand.image.Image(file=img)
            i.transform_colorspace("cmyk")
            i.format = "png"
            if i.size >= (3000, 3000):
                return ":warning: `Image exceeds maximum resolution >= (3000, 3000).`", 0
            count += 1
            i.transform(resize="800x800")
            i.liquid_rescale(
                width=int(i.width * 0.5),
                height=int(i.height * 0.5),
                delta_x=int(0.5 * scale) if scale else 1,
                rigidity=0,
            )
            i.liquid_rescale(
                width=int(i.width * 1.5),
                height=int(i.height * 1.5),
                delta_x=scale if scale else 2,
                rigidity=0,
            )
            magikd = BytesIO()
            i.save(file=magikd)
            file_size = magikd.tell()
            magikd.seek(0)
            list_imgs.append(magikd)
            filename = self.random_filename(True, "png")
            file = discord.File(list_imgs[0], filename=filename)
            return file, file_size
        except Exception:
            log.error("Error processing magik", exc_info=True)

    @commands.command(aliases=["imagemagic", "imagemagick", "magic", "magick", "cas", "liquid"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def magik(self, ctx, urls: ImageFinder = None, scale: int = 2, scale_msg: str = ""):
        """
        Apply magik to an image.
        """
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        async with ctx.typing():
            b, mime = await self.bytes_download(urls[0])
            if mime == "None":
                b.seek(0)
                image_header = b.read()[:20]
                mime = await self.determine_mime_type(str(image_header))
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            if mime in self.gif_mimes:
                task = loop.run_in_executor(None, self.do_gmagik, b, 1)
            else:
                task = loop.run_in_executor(None, self.do_magik, scale, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, TypeError):
                return await ctx.send(
                    "That image is either too large or given image format is unsupported."
                )
            if type(file) == str:
                await ctx.send(file)
                return

            await self.safe_send(ctx, scale_msg, file, file_size)

    def do_gmagik(self, image, frame_delay):
        final = BytesIO()
        is_gif = False
        image.seek(0)
        with wand.image.Image() as new_image:
            with wand.image.Image(file=image) as img:
                if len(getattr(img, "sequence", [])) > 1:
                    is_gif = True
                if is_gif:
                    log.verbose("Is gif")
                    for change in img.sequence:
                        change.transform(resize="512x512")
                        change.liquid_rescale(
                            width=int(change.width * 0.5),
                            height=int(change.height * 0.5),
                            delta_x=1,
                            rigidity=0,
                        )
                        change.liquid_rescale(
                            width=int(change.width * 1.5),
                            height=int(change.height * 1.5),
                            delta_x=2,
                            rigidity=0,
                        )
                        # change.sample(200, 200)
                        # i.save(filename=image)
                        new_image.sequence.append(change)
                    # for i in range(len(img.sequence)):
                    # with img.sequence[i] as change:
                else:
                    log.verbose("Is not gif")
                    for x in range(0, 30):
                        if x == 0:
                            log.debug("Cloning initial image")
                            i = img.clone().convert("gif")
                        else:
                            i = new_image.sequence[-1].clone()
                        i.transform(resize="512x512")
                        i.liquid_rescale(
                            width=int(i.width * 0.75),
                            height=int(i.height * 0.75),
                            delta_x=1,
                            rigidity=0,
                        )
                        i.liquid_rescale(
                            width=int(i.width * 1.25),
                            height=int(i.height * 1.25),
                            delta_x=2,
                            rigidity=0,
                        )
                        i.resize(img.width, img.height)
                        new_image.sequence.append(i)
            new_image.format = "gif"
            new_image.dispose = "background"
            new_image.type = "optimize"
            new_image.save(file=final)
            file_size = final.tell()
            final.seek(0)
        filename = self.random_filename(True, "gif")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def gmagik(self, ctx, urls: ImageFinder = None, frame_delay: int = 1):
        """Attempt to do magik on a gif"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        msg = await ctx.send("ok, processing (this might take a while for big gifs)")
        async with ctx.typing():
            if frame_delay > 60:
                frame_delay = 60
            elif frame_delay < 0:
                frame_delay = 1
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            if mime in self.gif_mimes:
                task = loop.run_in_executor(None, self.do_gmagik, b, frame_delay)
            else:
                task = loop.run_in_executor(None, self.do_magik, 2, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=120)
            except asyncio.TimeoutError:
                return await ctx.send("That image is too large.")
            except Exception:
                log.exception("Error running gmagik")
                await ctx.send(":warning: Gmagik failed...")
                return
            await self.safe_send(ctx, None, file, file_size)
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def caption(
        self,
        ctx,
        urls: Optional[ImageFinder] = None,
        text: str = "Caption",
        color: str = "white",
        size: int = 40,
        x: int = 0,
        y: int = 0,
    ):
        """
        Add caption to an image

        `[urls]` are the image urls or users or previous images in chat to add a caption to.
        `[text=Caption]` is the text to caption on the image.
        `[color=white]` is the color of the text.
        `[size=40]` is the size of the text
        `[x=0]` is the height the text starts at between 0 and 100% where 0 is the top and 100 is the bottom of the image.
        `[y=0]` is the width the text starts at between 0 and 100% where 0 is the left and 100 is the right of the image.
        """
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        if url is None:
            await ctx.send(
                "Error: Invalid Syntax\n`.caption <image_url> <text>**"
                " <color>* <size>* <x>* <y>*`\n`* = Optional`\n`** = Wrap text in quotes`"
            )
            return
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            is_gif = mime in self.gif_mimes
            font_path = f"{str(bundled_data_path(self))}{os.sep}arial.ttf"
            try:
                color = wand.color.Color(color)
            except ValueError:
                await ctx.send(":warning: **That is not a valid color!**")
                return
            font = wand.font.Font(path=font_path, size=size, color=color)
            if x > 100:
                x = 100
            if x < 0:
                x = 0
            if y > 100:
                y = 100
            if y < 0:
                y = 0

            def make_caption_image(b, text, color, font, x, y, is_gif):
                final = BytesIO()
                b.seek(0)
                with wand.image.Image(file=b) as img:
                    i = img.clone()
                    x = int(i.height * (x * 0.01))
                    y = int(i.width * (y * 0.01))
                    if not is_gif:
                        i.caption(str(text), left=x, top=y, font=font)
                    else:
                        with wand.image.Image() as new_image:
                            for frame in img.sequence:
                                frame.caption(str(text), left=x, top=y, font=font)
                                new_image.sequence.append(frame)
                            new_image.save(file=final)
                    i.save(file=final)
                file_size = final.tell()
                final.seek(0)
                filename = f"caption.{'png' if not is_gif else 'gif'}"
                file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(
                None, make_caption_image, b, text, color, font, x, y, is_gif
            )
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("That image is too large.")
            await ctx.send(file=file)

    def trigger_image(self, path: BytesIO, t_path: BytesIO) -> Tuple[discord.File, int]:
        final = BytesIO()
        with wand.image.Image(width=512, height=680) as img:
            img.format = "gif"
            img.dispose = "background"
            img.type = "optimize"
            with wand.image.Image(file=path) as top_img:
                top_img.transform(resize="640x640!")
                with wand.image.Image(file=t_path) as trigger:
                    with wand.image.Image(width=512, height=660) as temp_img:
                        i = top_img.clone()
                        t = trigger.clone()
                        temp_img.composite(i, -60, -60)
                        temp_img.composite(t, 0, 572)
                        img.composite(temp_img)
                    with wand.image.Image(width=512, height=660) as temp_img:
                        i = top_img.clone()
                        t = trigger.clone()
                        temp_img.composite(i, -45, -50)
                        temp_img.composite(t, 0, 572)
                        img.sequence.append(temp_img)
                    with wand.image.Image(width=512, height=660) as temp_img:
                        i = top_img.clone()
                        t = trigger.clone()
                        temp_img.composite(i, -50, -45)
                        temp_img.composite(t, 0, 572)
                        img.sequence.append(temp_img)
                    with wand.image.Image(width=512, height=660) as temp_img:
                        i = top_img.clone()
                        t = trigger.clone()
                        temp_img.composite(i, -45, -65)
                        temp_img.composite(t, 0, 572)
                        img.sequence.append(temp_img)
            # img.optimize_layers()
            # img.optimize_transparency()
            for frame in img.sequence:
                frame.delay = 2
            img.save(file=final)
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "gif")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def triggered(self, ctx, urls: ImageFinder = None):
        """Generate a Triggered GIF for a user or image"""
        if urls is None:
            urls = [ctx.author.display_avatar.replace(format="png").url]
        avatar = urls[0]
        async with ctx.typing():
            img, mime = await self.bytes_download(str(avatar))
            img_path = cog_data_path(self) / "triggered.jpg"
            if not os.path.isfile(img_path) or os.path.getsize(img_path) == 0:
                url = "https://i.imgur.com/zDAY2yo.jpg"
                trig, mime = await self.bytes_download(url)
                if trig is not False:
                    with img_path.open("wb") as outfile:
                        outfile.write(trig.read())
                else:
                    await ctx.send(
                        "There was an error downloading the triggered template. "
                        "If you are the bot owner check your logs for instructions to fix this."
                    )
                    log.info("Please visit %s and save this image at `%s`.", url, img_path)
                    return
            with img_path.open("rb") as infile:
                trig = BytesIO(infile.read())
            if img is False or trig is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            try:
                loop = asyncio.get_running_loop()
                task = loop.run_in_executor(None, self.trigger_image, img, trig)
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("Error creating trigger image")
            await self.safe_send(ctx, None, file, file_size)

    @commands.command(aliases=["aes"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def aesthetics(self, ctx, *, text: str):
        """Returns inputed text in aesthetics"""
        final = ""
        pre = " ".join(text)
        for char in pre:
            if not ord(char) in range(33, 127):
                final += char
                continue
            final += chr(ord(char) + 65248)
        await self.truncate(ctx.message.channel, final)

    def do_ascii(self, text):
        try:
            i = Image.new("RGB", (2000, 1000))
            img = ImageDraw.Draw(i)
            txt = figlet_format(text, font="starwars")
            img.text((20, 20), figlet_format(text, font="starwars"), fill=(0, 255, 0))
            size = img.textbbox((0, 0), figlet_format(text, font="starwars"))
            text_width, text_height = (size[2] - size[0], size[3] - size[1])
            imgs = Image.new("RGB", (text_width + 30, text_height))
            ii = ImageDraw.Draw(imgs)
            ii.text((20, 20), figlet_format(text, font="starwars"), fill=(0, 255, 0))
            size = ii.textbbox((0, 0), figlet_format(text, font="starwars"))
            text_width, text_height = (size[2] - size[0], size[3] - size[1])
            final = BytesIO()
            imgs.save(final, "png")
            file_size = final.tell()
            final.seek(0)
            filename = self.random_filename(True, "png")
            file = discord.File(final, filename=filename)
            return file, txt, file_size
        except Exception:
            log.exception("Error making ascii text")
            return False, False, False

    @commands.command(aliases=["expand"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def ascii(self, ctx, *, text: str):
        """Convert text into ASCII"""
        if len(text) > 1000:
            await ctx.send("Text is too long!")
            return
        if text == "donger" or text == "dong":
            text = "8====D"
        async with ctx.typing():
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_ascii, text)
            try:
                file, txt, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("That image is too large.")
            if file is False:
                await ctx.send(":no_entry: go away with your invalid characters.")
                return
            if len(txt) >= 1999:
                # await self.gist(ctx, text, txt)
                msg = None
            elif len(txt) <= 600:
                msg = "```fix\n{0}```".format(txt)
            else:
                msg = None

            await self.safe_send(ctx, msg, file, file_size)

    def generate_ascii(self, image):
        font = ImageFont.truetype(str(cog_data_path(self)) + "/FreeMonoBold.ttf", 15)
        image_width, image_height = image.size
        aalib_screen_width = int(image_width / 24.9) * 10
        aalib_screen_height = int(image_height / 41.39) * 10
        screen = aalib.AsciiScreen(width=aalib_screen_width, height=aalib_screen_height)

        im = image.convert("L").resize(screen.virtual_size)
        screen.put_image((0, 0), im)
        y = 0
        how_many_rows = len(screen.render().splitlines())
        new_img_width, font_size = font.getsize(screen.render().splitlines()[0])
        img = Image.new("RGBA", (new_img_width, how_many_rows * 15), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        for lines in screen.render().splitlines():
            draw.text((0, y), lines, (0, 0, 0), font=font)
            y += 15
        imagefit = ImageOps.fit(img, (image_width, image_height), Image.ANTIALIAS)

        final = BytesIO()
        img.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        # file = discord.File(final, filename="iascii.png")
        return final, file_size

    async def check_font_file(self):
        try:
            ImageFont.truetype(cog_data_path(self) / "FreeMonoBold.ttf", 15)
        except Exception:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://github.com/opensourcedesign/fonts"
                    "/raw/master/gnu-freefont_freemono/FreeMonoBold.ttf"
                ) as resp:
                    data = await resp.read()
                with open(cog_data_path(self) / "FreeMonoBold.ttf", "wb") as save_file:
                    save_file.write(data)

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.check(lambda ctx: AALIB_INSTALLED)
    @commands.bot_has_permissions(attach_files=True)
    async def iascii(self, ctx, urls: ImageFinder = None):
        """Generate an ascii art image of last image in chat or from URL"""
        if not AALIB_INSTALLED:
            await ctx.send("aalib couldn't be found on this machine!")
            return
        await self.check_font_file()
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if mime not in self.image_mimes and not isinstance(url, discord.Asset):
                return await ctx.send("That is not a valid image!")
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            im = Image.open(b)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.generate_ascii, im)
            try:
                temp, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "That image is either too large or image filetype is unsupported."
                )
            filename = self.random_filename(True, "png")
            file = discord.File(temp, filename)
            await self.safe_send(ctx, None, file, file_size)

    def do_gascii(self, b):
        img_list = []
        temp = BytesIO()
        try:
            image = Image.open(b)
            gif_list = [frame.copy() for frame in ImageSequence.Iterator(image)]
            count = 0
            for frame in gif_list[:20]:
                im = frame.copy()
                new_im, size = self.generate_ascii(im)
                img = Image.open(new_im)
                img_list.append(img)
                count += 1
            temp = BytesIO()
            img.save(temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0)
            file_size = temp.tell()
            temp.seek(0)
            filename = self.random_filename(True, "gif")
            file = discord.File(temp, filename=filename)
            return file, file_size
        except Exception:
            raise

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.check(lambda ctx: AALIB_INSTALLED)
    @commands.bot_has_permissions(attach_files=True)
    async def gascii(self, ctx, urls: ImageFinder = None):
        """Gif to ASCII"""
        if not AALIB_INSTALLED:
            await ctx.send("aalib couldn't be found on this machine!")
            return
        await self.check_font_file()
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            result = loop.run_in_executor(None, self.do_gascii, b)
            try:
                file, file_size = await asyncio.wait_for(result, timeout=60)
            except asyncio.TimeoutError:
                return
            except Exception:
                log.exception("Error Running gascii")
                return await ctx.send("There was an error performing gascii.")
            await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def rip(self, ctx, name: str = None, *, text: str = None):
        """Generate tombstone image with name and optional text"""
        if name is None:
            name = ctx.message.author.name
        if len(ctx.message.mentions) >= 1:
            name = ctx.message.mentions[0].name
        # b, mime = await self.bytes_download()
        img_path = cog_data_path(self) / "rip.jpg"
        if not os.path.isfile(img_path) or os.path.getsize(img_path) == 0:
            url = "https://i.imgur.com/xNWxZHn.jpg"
            img, mime = await self.bytes_download(url)
            if img is not False:
                with img_path.open("wb") as outfile:
                    outfile.write(img.read())
            else:
                await ctx.send(
                    "There was an error downloading the triggered template. "
                    "If you are the bot owner check your logs for instructions to fix this."
                )
                log.info("Please visit %s and save this image at `%s`.", url, img_path)
                return
        with img_path.open("rb") as infile:
            image = BytesIO(infile.read())
        if not text:
            text = f"{name}'s\n Hopes and Dreams"
        else:
            text = f"{name}\n{text}"

        def make_rip(image, text):
            img = Image.open(image).convert("RGB")
            draw = ImageDraw.Draw(img)
            font_path = f"{str(bundled_data_path(self))}{os.sep}arial.ttf"
            font1 = ImageFont.truetype(font_path, 35)
            text = "\n".join(line for line in textwrap.wrap(text, width=15))
            size = draw.multiline_textbbox((0, 0), text, font=font1)
            w = size[2] - size[1]
            draw.multiline_text(
                (((400 - w) / 2) - 1, 50), text, fill=(50, 50, 50), font=font1, align="center"
            )
            draw.multiline_text(
                (((400 - w) / 2) + 1, 50), text, fill=(50, 50, 50), font=font1, align="center"
            )
            draw.multiline_text(
                (((400 - w) / 2), 49), text, fill=(50, 50, 50), font=font1, align="center"
            )
            draw.multiline_text(
                (((400 - w) / 2), 51), text, fill=(50, 50, 50), font=font1, align="center"
            )
            draw.multiline_text(
                ((400 - w) / 2, 50), text, fill=(105, 105, 105), font=font1, align="center"
            )
            final = BytesIO()
            img.save(final, "JPEG")
            file_size = final.tell()
            final.seek(0)
            filename = self.random_filename(True, "jpg")
            file = discord.File(final, filename=filename)
            return file, file_size

        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, make_rip, image, text)
        try:
            file, file_size = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return await ctx.send("That image is too large.")
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)  # ImageFinder consumes rest this is so goat'd
    async def merge(self, ctx, vertical: Optional[bool] = True, *, urls: Optional[ImageFinder]):
        """
        Merge/Combine Two Photos

        `[vertical=True]` `true` or `false` to merge vertically.
        `[urls]` The Image URL's you want to merge together. If not supplied
        images are searched from message history.
        """
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        if not urls:
            return await ctx.send("No images found.")
        async with ctx.typing():
            if len(urls) == 1:
                await ctx.send("You need to supply more than 1 image.")
                return
            count = 0
            list_im = []
            for url in urls:
                log.verbose("merge url: %s", url)
                count += 1
                b, mime = await self.bytes_download(str(url))
                if sys.getsizeof(b) == 215:
                    await ctx.send(":no_entry: Image `{0}` is invalid!".format(str(count)))
                    continue
                if not b:
                    continue
                list_im.append(b)

            def make_merge(list_im):
                imgs = [Image.open(i).convert("RGBA") for i in list_im]
                if vertical:
                    # Vertical
                    max_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[1][1]
                    imgs_comb = np.vstack([np.asarray(i.resize(max_shape)) for i in imgs])
                else:
                    # Horizontal
                    min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
                    imgs_comb = np.hstack([np.asarray(i.resize(min_shape)) for i in imgs])
                imgs_comb = Image.fromarray(imgs_comb)
                final = BytesIO()
                imgs_comb.save(final, "png")
                file_size = final.tell()
                final.seek(0)
                filename = self.random_filename(True, "png")
                file = discord.File(final, filename=filename)
                return file, file_size

            if len(list_im) < 2:
                return await ctx.send("You need to supply more than 1 image.")
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, make_merge, list_im)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "That image is either too large or image filetype is unsupported."
                )
            await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    async def emojify(self, ctx, *, txt: str):
        """Replace characters in text with emojis"""
        txt = txt.lower()
        msg = ""
        for s in txt:
            if s in self.emoji_map:
                msg += "{0}".format(self.emoji_map[s])
            else:
                msg += s
        await ctx.send(msg)

    async def get_colour(self, channel):
        try:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()
        except AttributeError:
            return await self.bot.get_embed_colour(channel)

    @commands.command(aliases=["needsmorejpeg", "jpegify", "magik2"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def jpeg(self, ctx, urls: Optional[ImageFinder] = None, quality: int = 1):
        """
        Add more JPEG to an Image

        Needs More JPEG!
        `[urls]` is optional, if not provided will search chat for a valid image.
        `[quality]` is the quality of the new jpeg image to make
        """
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        if quality > 10:
            quality = 10
        elif quality < 1:
            quality = 1
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return

            def make_jpeg(b):
                img = Image.open(b).convert("RGB")
                final = BytesIO()
                img.save(final, "JPEG", quality=quality)
                file_size = final.tell()
                final.seek(0)
                filename = self.random_filename(True, "jpg")
                file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, make_jpeg, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "That image is either too large or image filetype is unsupported."
                )
            await self.safe_send(ctx, None, file, file_size)

    def do_vw(self, b, txt):
        im = Image.open(b)
        k = random.randint(0, 100)
        im = macintoshplus.draw_method1(k, txt, im)
        final = BytesIO()
        im.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command(aliases=["vaporwave", "vape", "vapewave"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def vw(self, ctx, urls: ImageFinder = None, *, txt: str = None):
        """Add vaporwave flavours to an image"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        if txt is None:
            txt = "vapor wave"
        b, mime = await self.bytes_download(url)
        if b is False:
            await ctx.send(":warning: **Command download function failed...**")
            return
        try:
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_vw, b, txt)
            file, file_size = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return await ctx.send("That image is too large.")
        except Exception:
            log.error("Error in vaporwave: ", exc_info=True)
            return await ctx.send("That image cannot be vaporwaved.")
        await self.safe_send(ctx, None, file, file_size)

    @commands.command(aliases=["achievement"])
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def minecraftachievement(self, ctx, *, txt: str):
        """Generate a Minecraft Achievement"""
        img_path = cog_data_path(self) / "achievement.png"
        if not os.path.isfile(img_path) or os.path.getsize(img_path) == 0:
            url = "https://i.imgur.com/JtNJFZy.png"
            img, mime = await self.bytes_download(url)
            if img is not False:
                with img_path.open("wb") as outfile:
                    outfile.write(img.read())
            else:
                await ctx.send(
                    "There was an error downloading the triggered template. "
                    "If you are the bot owner check your logs for instructions to fix this."
                )
                log.info("Please visit %s and save this image at `%s`.", url, img_path)
                return
        with img_path.open("rb") as infile:
            image = BytesIO(infile.read())
        if len(txt) > 20:
            txt = txt[:20] + " ..."

        def make_mc(b, txt):
            image = Image.open(b).convert("RGBA")
            draw = ImageDraw.Draw(image)
            font_path = str(bundled_data_path(self)) + "/Minecraftia.ttf"
            font = ImageFont.truetype(font_path, 17)
            draw.text((60, 30), txt, (255, 255, 255), font=font)
            final = BytesIO()
            image.save(final, "png")
            file_size = final.tell()
            final.seek(0)
            filename = self.random_filename(True, "png")
            file = discord.File(final, filename=filename)
            return file, file_size

        try:
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, make_mc, image, txt)
            file, file_size = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return await ctx.send("That image is too large.")
        except Exception:
            return await ctx.send("I cannot make that minecraft achievement.")
        await self.safe_send(ctx, None, file, file_size)

    @commands.command(aliases=["wm"])
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def watermark(
        self,
        ctx,
        urls: ImageFinder = None,
        mark: str = None,
        x: int = 0,
        y: int = 0,
        transparency: Union[int, float] = 0,
    ):
        """
        Add a watermark to an image

        `[urls]` are the image urls or users or previous images in chat to add a watermark to.
        `[mark]` is the image to use as the watermark. By default the brazzers icon is used.
        `[x=0]` is the height the watermark will be at between 0 and 100% where 0 is the top and 100 is the bottom of the image.
        `[y=0]` is the width the watermark will be at between 0 and 100% where 0 is the left and 100 is the right of the image.
        `[transparency=0]` is a value from 0 to 100 which determines the percentage the watermark will be transparent.
        """
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            if x > 100:
                x = 100
            if x < 0:
                x = 0
            if y > 100:
                y = 100
            if y < 0:
                y = 0
            if transparency > 1 and transparency < 100:
                transparency = transparency * 0.01
            if transparency < 0:
                transparency = 0
            if transparency > 100:
                transparency = 1
            b, mime = await self.bytes_download(url)
            if mime not in self.image_mimes + self.gif_mimes and not isinstance(
                url, discord.Asset
            ):
                return await ctx.send("That is not a valid image.")
            if mark == "brazzers" or mark is None:
                img_path = cog_data_path(self) / "brazzers.png"
                if not os.path.isfile(img_path) or os.path.getsize(img_path) == 0:
                    url = "https://i.imgur.com/YAb1RMZ.png"
                    img, mime = await self.bytes_download(url)
                    if img is not False:
                        with img_path.open("wb") as outfile:
                            outfile.write(img.read())
                    else:
                        await ctx.send(
                            "There was an error downloading the triggered template. "
                            "If you are the bot owner check your logs for instructions to fix this."
                        )
                        log.info("Please visit %s and save this image at `%s`.", url, img_path)
                        return
                with img_path.open("rb") as infile:
                    wmm = BytesIO(infile.read())
                if wmm is False or b is False:
                    await ctx.send(":warning: **Command download function failed...**")
                    return
                wmm.name = self.random_filename(True, "png")
                wm_gif = False
            else:
                wmm, mime = await self.bytes_download(mark)
                wm_gif = mime in self.gif_mimes
                if wmm is False or b is False:
                    await ctx.send(":warning: **Command download function failed...**")
                    return
                wmm.name = self.random_filename(True, "png")
                if wm_gif:
                    wmm.name = self.random_filename(True, "gif")

            def add_watermark(b, wmm, x, y, transparency, wm_gif=False):
                final = BytesIO()
                b.seek(0)
                with wand.image.Image(file=b) as img:
                    is_gif = len(getattr(img, "sequence")) > 1
                    if not is_gif and not wm_gif:
                        log.debug("There are no gifs")
                        with img.clone() as new_img:
                            new_img.transform(resize="65536@")
                            final_x = int(new_img.height * (x * 0.01))
                            final_y = int(new_img.width * (y * 0.01))
                            with wand.image.Image(file=wmm) as wm:
                                new_img.watermark(
                                    image=wm, left=final_x, top=final_y, transparency=transparency
                                )
                            new_img.save(file=final)

                    elif is_gif and not wm_gif:
                        log.debug("The base image is a gif")
                        wm = wand.image.Image(file=wmm)
                        with wand.image.Image() as new_image:
                            with img.clone() as new_img:
                                for frame in new_img.sequence:
                                    frame.transform(resize="65536@")
                                    final_x = int(frame.height * (x * 0.01))
                                    final_y = int(frame.width * (y * 0.01))
                                    frame.watermark(
                                        image=wm,
                                        left=final_x,
                                        top=final_y,
                                        transparency=transparency,
                                    )
                                    new_image.sequence.append(frame)
                            new_image.save(file=final)
                    else:
                        log.debug("The mark is a gif")
                        with wand.image.Image() as new_image:
                            with wand.image.Image(file=wmm) as new_img:
                                for frame in new_img.sequence:
                                    with img.clone() as clone:
                                        if is_gif:
                                            clone = clone.sequence[0]
                                            # we only care about the first frame of the gif in this case
                                        else:
                                            clone = clone.convert("gif")

                                        clone.transform(resize="65536@")
                                        final_x = int(clone.height * (x * 0.01))
                                        final_y = int(clone.width * (y * 0.01))
                                        clone.watermark(
                                            image=frame,
                                            left=final_x,
                                            top=final_y,
                                            transparency=transparency,
                                        )
                                        new_image.sequence.append(clone)
                                        new_image.dispose = "background"
                                        with new_image.sequence[-1] as new_frame:
                                            new_frame.delay = frame.delay

                            new_image.save(file=final)

                size = final.tell()
                final.seek(0)
                filename = f"watermark.{'gif' if is_gif or wm_gif else 'png'}"
                file = discord.File(final, filename=filename)
                return file, size

            try:
                loop = asyncio.get_running_loop()
                task = loop.run_in_executor(
                    None, add_watermark, b, wmm, x, y, transparency, wm_gif
                )
                file, file_size = await asyncio.wait_for(task, timeout=120)
            except asyncio.TimeoutError:
                return await ctx.send("That image is too large.")
            await self.safe_send(ctx, None, file, file_size)

    def do_glitch(self, b, amount, seed, iterations):
        img = Image.open(b)
        is_gif = (hasattr(img, "is_animated")) and (img.is_animated)
        if not is_gif:
            image = img.convert("RGB")
            img_bytes = BytesIO()
            image.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            final = BytesIO()
            image = jpglitch.Jpeg(bytearray(img_bytes.getvalue()), amount, seed, iterations)
            final.name = self.random_filename(True, "jpg")
            image.save_image(final)
            file_size = final.tell()
            final.seek(0)
            file = discord.File(final, filename=final.name)
        else:
            ba = bytearray(b.getvalue())
            for x in range(0, sys.getsizeof(ba)):
                if ba[x] == 33:
                    if ba[x + 1] == 255:
                        end = x
                        break
                    elif ba[x + 1] == 249:
                        end = x
                        break
            for x in range(13, end):
                ba[x] = random.randint(0, 255)
            final = BytesIO(ba)
            file_size = final.tell()
            filename = self.random_filename(True, "gif")
            file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command(aliases=["jpglitch"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def glitch(
        self,
        ctx,
        urls: ImageFinder = None,
        iterations: int = None,
        amount: int = None,
        seed: int = None,
    ):
        """Glitch a gif or png"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            if iterations is None:
                iterations = random.randint(1, 30)
            if amount is None:
                amount = random.randint(1, 20)
            elif amount > 99:
                amount = 99
            if seed is None:
                seed = random.randint(1, 20)
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_glitch, b, amount, seed, iterations)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "The image is either too large or image filetype is unsupported."
                )

            msg = f"Iterations: `{iterations}` | Amount: `{amount}` | Seed: `{seed}`"
            await self.safe_send(ctx, msg, file, file_size)

    @commands.command(aliases=["pixel"])
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def pixelate(self, ctx, urls: ImageFinder = None, pixels: int = 9):
        """Pixelate an image"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            img_urls = urls[0]
            b, mime = await self.bytes_download(url)
            if b is False:
                if len(img_urls) > 1:
                    await ctx.send(":warning: **Command download function failed...**")
                    return
            loop = asyncio.get_running_loop()
            if mime in self.gif_mimes:
                task = loop.run_in_executor(None, self.make_pixel_gif, b, pixels)
            else:
                task = loop.run_in_executor(None, self.make_pixel, b, pixels)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("The image is too large.")
            await self.safe_send(ctx, None, file, file_size)

    def make_pixel(self, b: BytesIO, pixels: int) -> Tuple[discord.File, int]:
        bg = (0, 0, 0)
        img = Image.open(b).convert("RGBA")
        img = img.resize((int(img.size[0] / pixels), int(img.size[1] / pixels)), Image.NEAREST)
        img = img.resize((int(img.size[0] * pixels), int(img.size[1] * pixels)), Image.NEAREST)
        load = img.load()
        for i in range(0, img.size[0], pixels):
            for j in range(0, img.size[1], pixels):
                for r in range(pixels):
                    load[i + r, j] = bg
                    load[i, j + r] = bg
        final = BytesIO()
        img.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    def make_pixel_gif(self, b, pixels):
        try:
            image = Image.open(b).convert("RGBA")
            gif_list = [frame.copy() for frame in ImageSequence.Iterator(image)]
        except IOError:
            return ":warning: Cannot load gif."
        bg = (0, 0, 0)
        img_list = []
        for frame in gif_list:
            img = Image.new("RGBA", frame.size)
            img.paste(frame, (0, 0))
            img = img.resize((int(img.size[0] / pixels), int(img.size[1] / pixels)), Image.NEAREST)
            img = img.resize((int(img.size[0] * pixels), int(img.size[1] * pixels)), Image.NEAREST)
            load = img.load()
            for i in range(0, img.size[0], pixels):
                for j in range(0, img.size[1], pixels):
                    for r in range(pixels):
                        load[i + r, j] = bg
                        load[i, j + r] = bg
            img_list.append(img)
        final = BytesIO()
        img.save(final, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0)
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "gif")
        file = discord.File(final, filename=filename)
        return file, file_size

    def do_waaw(self, b):
        f = BytesIO()
        f2 = BytesIO()
        b.seek(0)
        with wand.image.Image(file=b) as img:
            h1 = img.clone()
            width = int(img.width / 2) if int(img.width / 2) > 0 else 1
            h1.crop(width=width, height=int(img.height), gravity="east")
            h2 = h1.clone()
            h2.flop()
            h1.save(file=f)
            h2.save(file=f2)
        f.seek(0)
        f2.seek(0)
        list_im = [f, f2]
        imgs = [ImageOps.mirror(Image.open(i).convert("RGBA")) for i in list_im]
        min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
        imgs_comb = np.hstack([np.asarray(i.resize(min_shape)) for i in imgs])
        imgs_comb = Image.fromarray(imgs_comb)
        final = BytesIO()
        imgs_comb.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    # Thanks to Iguniisu#9746 for the idea
    @commands.command(aliases=["magik3", "mirror"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def waaw(self, ctx, urls: ImageFinder = None):
        """Mirror an image vertically right to left"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_waaw, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, wand.exceptions.MissingDelegateError):
                return await ctx.send(
                    "The image is either too large or you're missing delegates for this image format."
                )
            await self.safe_send(ctx, None, file, file_size)

    def do_haah(self, b):
        f = BytesIO()
        f2 = BytesIO()
        b.seek(0)
        with wand.image.Image(file=b) as img:
            h1 = img.clone()
            width = int(img.width / 2) if int(img.width / 2) > 0 else 1
            h1.crop(width=width, height=int(img.height), gravity="west")
            h2 = h1.clone()
            h2.flop()
            h1.save(file=f)
            h2.save(file=f2)
        f.seek(0)
        f2.seek(0)
        list_im = [f2, f]
        imgs = [ImageOps.mirror(Image.open(i).convert("RGBA")) for i in list_im]
        min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
        imgs_comb = np.hstack([np.asarray(i.resize(min_shape)) for i in imgs])
        imgs_comb = Image.fromarray(imgs_comb)
        final = BytesIO()
        imgs_comb.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command(aliases=["magik4", "mirror2"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def haah(self, ctx, urls: ImageFinder = None):
        """Mirror an image vertically left to right"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_haah, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, wand.exceptions.MissingDelegateError):
                return await ctx.send(
                    "The image is either too large or you're missing delegates for this image format."
                )
            await self.safe_send(ctx, None, file, file_size)

    def do_woow(self, b):
        f = BytesIO()
        f2 = BytesIO()
        b.seek(0)
        with wand.image.Image(file=b) as img:
            h1 = img.clone()
            width = int(img.width) if int(img.width) > 0 else 1
            h1.crop(width=width, height=int(img.height / 2), gravity="north")
            h2 = h1.clone()
            h2.flop()
            h2.rotate(degree=180)
            h1.save(file=f)
            h2.save(file=f2)
        f.seek(0)
        f2.seek(0)
        list_im = [f, f2]
        imgs = [Image.open(i).convert("RGBA") for i in list_im]
        min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
        imgs_comb = np.vstack([np.asarray(i.resize(min_shape)) for i in imgs])
        imgs_comb = Image.fromarray(imgs_comb)
        final = BytesIO()
        imgs_comb.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command(aliases=["magik5", "mirror3"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def woow(self, ctx, urls: ImageFinder = None):
        """Mirror an image horizontally top to bottom"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_woow, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, wand.exceptions.MissingDelegateError):
                return await ctx.send(
                    "The image is either too large or you're missing delegates for this image format."
                )
            await self.safe_send(ctx, None, file, file_size)

    def do_hooh(self, b):
        f = BytesIO()
        f2 = BytesIO()
        b.seek(0)
        with wand.image.Image(file=b) as img:
            h1 = img.clone()
            h1.flop()
            width = int(img.width) if int(img.width) > 0 else 1
            h1.crop(width=width, height=int(img.height / 2), gravity="south")
            h2 = h1.clone()
            h1.rotate(degree=180)
            h2.flop()
            h1.save(file=f)
            h2.save(file=f2)
        f.seek(0)
        f2.seek(0)
        list_im = [f, f2]
        imgs = [Image.open(i).convert("RGBA") for i in list_im]
        min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
        imgs_comb = np.vstack([np.asarray(i.resize(min_shape)) for i in imgs])
        imgs_comb = Image.fromarray(imgs_comb)
        final = BytesIO()
        imgs_comb.save(final, "png")
        file_size = final.tell()
        final.seek(0)
        filename = self.random_filename(True, "png")
        file = discord.File(final, filename=filename)
        return file, file_size

    @commands.command(aliases=["magik6", "mirror4"])
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(attach_files=True)
    async def hooh(self, ctx, urls: ImageFinder = None):
        """Mirror an image horizontally bottom to top"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, self.do_hooh, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, wand.exceptions.MissingDelegateError):
                return await ctx.send(
                    "The image is either too large or you're missing delegates for this image format."
                )
            await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def flipimg(self, ctx, urls: ImageFinder = None):
        """Rotate an image 180 degrees"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return

            def flip_img(b):
                with Image.open(b) as img:
                    image = ImageOps.flip(img)
                with BytesIO() as final:
                    image.save(final, "png")
                    file_size = final.tell()
                    final.seek(0)
                    filename = self.random_filename(True, "png")
                    file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, flip_img, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "The image is either too large or image filetype is unsupported."
                )
            await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def flop(self, ctx, urls: ImageFinder = None):
        """Flip an image horizontally"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return

            def flop_img(b):
                with Image.open(b) as img:
                    image = ImageOps.mirror(img)
                with BytesIO() as final:
                    image.save(final, "png")
                    file_size = final.tell()
                    final.seek(0)
                    filename = self.random_filename(True, "png")
                    file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, flop_img, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send("That image is too large.")
            await self.safe_send(ctx, None, file, file_size)

    @commands.command(aliases=["inverse", "negate"])
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def invert(self, ctx, urls: ImageFinder = None):
        """Invert the colours of an image"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if b is False:
                await ctx.send(":warning: **Command download function failed...**")
                return

            def invert_img(b):
                with Image.open(b).convert("RGB") as img:
                    image = ImageOps.invert(img)
                with BytesIO() as final:
                    image.save(final, "png")
                    file_size = final.tell()
                    final.seek(0)
                    filename = self.random_filename(True, "png")
                    file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, invert_img, b)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "That image is either too large or image filetype is unsupported."
                )
            await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def rotate(self, ctx, degrees: int = 90, urls: ImageFinder = None):
        """Rotate image X degrees"""
        if urls is None:
            urls = await ImageFinder().search_for_images(ctx)
        url = urls[0]
        async with ctx.typing():
            b, mime = await self.bytes_download(url)
            if not b:
                return await ctx.send("That's not a valid image to rotate.")

            def rotate_img(b, degrees):
                with Image.open(b).convert("RGBA") as img:
                    image = img.rotate(int(degrees))
                with BytesIO() as final:
                    image.save(final, "png")
                    file_size = final.tell()
                    final.seek(0)
                    filename = self.random_filename(True, "png")
                    file = discord.File(final, filename=filename)
                return file, file_size

            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, rotate_img, b, degrees)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except (asyncio.TimeoutError, PIL.UnidentifiedImageError):
                return await ctx.send(
                    "That image is either too large or image filetype is unsupported."
                )
            await self.safe_send(ctx, f"Rotated: `{degrees}°`", file, file_size)
