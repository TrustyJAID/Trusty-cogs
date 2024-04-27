import asyncio
import functools
import json
import os
import textwrap
from io import BytesIO
from typing import List, Optional, Tuple, Union, cast

import aiohttp
import discord
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageSequence
from PIL import features as pil_features
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

from .converter import ImageFinder

log = getLogger("red.trusty-cogs.imagemaker")

try:
    import cv2

    TRUMP = True
except ImportError:
    TRUMP = False


WEBP_OR_GIF = "webp" if pil_features.check("webp_anim") else "gif"
WEBP_OR_PNG = "webp" if pil_features.check("webp") else "png"
# Thanks Fixator
# https://github.com/fixator10/Fixator10-Cogs/blob/b147a0660b87ffc1b3a622083a562b11a47fad26/leveler/image_generators.py#L37


class ImageMaker(commands.Cog):
    """
    Create various fun images
    """

    __author__ = [
        "TrustyJAID",
        "Ivan Seidel (isnowillegal.com)",
        "Bruno Lemos (isnowillegal.com)",
        "Jo\u00e3o Pedro (isnowillegal.com)",
    ]
    __version__ = "1.6.0"

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

    async def safe_send(
        self, ctx: commands.Context, text: Optional[str], file: discord.File, file_size: int
    ):
        if not ctx.channel.permissions_for(ctx.me).send_messages:
            return
        if not ctx.channel.permissions_for(ctx.me).attach_files:
            await ctx.send("I don't have permission to attach files.")
            return
        BASE_FILESIZE_LIMIT = 25 * 1024 * 1024
        if ctx.guild and file_size < ctx.guild.filesize_limit:
            await ctx.send(content=text, file=file)
        elif not ctx.guild and file_size < BASE_FILESIZE_LIMIT:
            await ctx.send(content=text, file=file)
        else:
            await ctx.send("The contents of this command is too large to upload!")
        file.close()

    async def dl_image(
        self, url: Union[discord.Asset, discord.Attachment, str]
    ) -> Optional[BytesIO]:
        if isinstance(url, (discord.Asset, discord.PartialEmoji, discord.Attachment)):
            try:
                b = BytesIO()
                await url.save(b)
                return b
            except discord.HTTPException:
                return None
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                if resp.status == 200:
                    test = await resp.read()
                    return BytesIO(test)
                else:
                    return None

    def make_outline_image(self, img):
        # https://medium.com/nerd-for-tech/cartoonize-images-with-python-10e2a466b5fb
        # Apply some Gaussian blur on the image
        img_gb = cv2.GaussianBlur(img, (7, 7), 0)
        # Apply some Median blur on the image
        img_mb = cv2.medianBlur(img_gb, 5)
        # Apply a bilateral filer on the image
        img_bf = cv2.bilateralFilter(img_mb, 5, 80, 80)
        # Use the laplace filter to detect edges
        img_lp_im = cv2.Laplacian(img, cv2.CV_8U, ksize=5)
        img_lp_gb = cv2.Laplacian(img_gb, cv2.CV_8U, ksize=5)
        img_lp_mb = cv2.Laplacian(img_mb, cv2.CV_8U, ksize=5)
        img_lp_al = cv2.Laplacian(img_bf, cv2.CV_8U, ksize=5)
        # Convert the image to greyscale (1D)
        img_lp_im_grey = cv2.cvtColor(img_lp_im, cv2.COLOR_BGR2GRAY)
        img_lp_gb_grey = cv2.cvtColor(img_lp_gb, cv2.COLOR_BGR2GRAY)
        img_lp_mb_grey = cv2.cvtColor(img_lp_mb, cv2.COLOR_BGR2GRAY)
        img_lp_al_grey = cv2.cvtColor(img_lp_al, cv2.COLOR_BGR2GRAY)
        # Manual image thresholding
        _, EdgeImage = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        # Remove some additional noise
        blur_im = cv2.GaussianBlur(img_lp_im_grey, (5, 5), 0)
        blur_gb = cv2.GaussianBlur(img_lp_gb_grey, (5, 5), 0)
        blur_mb = cv2.GaussianBlur(img_lp_mb_grey, (5, 5), 0)
        blur_al = cv2.GaussianBlur(img_lp_al_grey, (5, 5), 0)
        # Apply a threshold (Otsu)
        _, tresh_im = cv2.threshold(blur_im, 245, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, tresh_gb = cv2.threshold(blur_gb, 245, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, tresh_mb = cv2.threshold(blur_mb, 245, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, tresh_al = cv2.threshold(blur_al, 245, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Invert the black and the white
        inverted_original = cv2.subtract(255, tresh_im)
        inverted_GaussianBlur = cv2.subtract(255, tresh_gb)
        inverted_MedianBlur = cv2.subtract(255, tresh_mb)
        inverted_Bilateral = cv2.subtract(255, tresh_al)
        template = self.cvImageToPillow(inverted_original)
        temp = BytesIO()
        template.save(temp, format=WEBP_OR_PNG)
        temp.name = f"outline.{WEBP_OR_PNG}"
        temp.seek(0)
        return temp

    # @commands.command()
    # @commands.bot_has_permissions(attach_files=True)
    async def scrybe(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """
        Scrybe your own card

         WIP not done
        """
        if user is None:
            user = ctx.author
        avatar = await self.dl_image(user.display_avatar.replace(format="png"))
        avatar.seek(0)
        file_bytes = np.frombuffer(avatar.read(), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        new_img = self.make_outline_image(img)
        await ctx.send(file=discord.File(new_img, filename="outline.png"))

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def wheeze(
        self,
        ctx: commands.Context,
        *,
        text: Optional[Union[discord.Member, discord.User, str]] = None,
    ) -> None:
        """
        Generate a wheeze image with text or a user avatar.

        `<text>` the text or user avatar who will be placed in the bottom pane.
        """
        if text is None:
            text = ctx.message.author
        async with ctx.channel.typing():
            try:
                file, file_size = await self.make_wheeze(text)
            except RuntimeError as e:
                log.error(e)
                await ctx.send("There was an issue getting the template file.")
                return
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
            # ext = await self.make_beautiful(user)
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def facemerge(self, ctx: commands.Context, *, urls: ImageFinder):
        """
        Generate a gif of two images fading into eachother.

        - `<urls>` The urls you want to fade merge together.
         - This can be 2 users and will use their display avatar or
           emojis to combine 2 discord emojis.
        """
        if len(urls) < 2:
            urls = await ImageFinder().search_for_images(ctx)
            if len(urls) < 2:
                return await ctx.send("You must supply at least 2 image links.")
        async with ctx.channel.typing():
            file, file_size = await self.face_merge(urls)
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def scrollbanner(
        self,
        ctx: commands.Context,
        colour: discord.Colour = discord.Colour.from_rgb(255, 0, 0),
        *,
        text: str,
    ) -> None:
        """
        Generate a scrolling text gif banner.

        - `[colour=#ff0000]` The colour of the banner wheel.
         - defaults to red or `#ff0000`.
         - named colours can be found [here.](https://discordpy.readthedocs.io/en/latest/api.html#colour)
        - `<text>` The text that will be scrolled on the banner.
        """
        async with ctx.channel.typing():
            task = functools.partial(self.make_banner, text=text, colour=colour)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, task)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                await ctx.send("I could not create the banner you requested.")
                return
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def obama(self, ctx: commands.Context, *, text: str):
        """
        Synthesize video clips of Obama.

        - `<text>` The message you want Obama to say. Max 280 characters.
        """
        text = ctx.message.clean_content[len(f"{ctx.prefix}{ctx.invoked_with}") :]
        if len(text) > 280:
            msg = "A maximum character total of 280 is enforced. You sent: `{}` characters"
            return await ctx.send(msg.format(len(text)))
        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        url="http://talkobamato.me/synthesize.py", data={"input_text": text}
                    ) as resp:
                        if resp.status != 200:
                            return await ctx.send(
                                "Something went wrong while trying to get the video."
                            )
                        url = resp.url

                    key = url.query["speech_key"]
                    link = f"http://talkobamato.me/synth/output/{key}/obama.mp4"
                    await asyncio.sleep(len(text) // 5)
                    async with session.get(link) as resp:
                        if resp.status != 200:
                            return await ctx.send(
                                "Something went wrong while trying to get the video."
                            )
                    async with session.get(link) as r:
                        data = BytesIO(await r.read())
                except aiohttp.ClientConnectionError:
                    return await ctx.send("Something went wrong while trying to get the video.")
                data.name = "obama.mp4"
                data.seek(0)
                file = discord.File(data)
                file_size = data.tell()
                data.close()
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def gwheeze(
        self, ctx: commands.Context, member: Optional[Union[discord.Member, discord.User]] = None
    ) -> None:
        """
        Generate a gif wheeze image if user has a gif avatar.

        - `[member]` the member whos avatar will be pasted on the image.
         - defaults to the author.
        """
        if member is None:
            member = ctx.message.author
        async with ctx.channel.typing():
            try:
                file, file_size = await self.make_wheeze(member, True)
            except RuntimeError as e:
                log.error(e)
                await ctx.send("There was an issue getting the template file.")
                return
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def beautiful(
        self,
        ctx: commands.Context,
        user: Optional[Union[discord.Member, discord.User]] = None,
        is_gif: bool = False,
    ) -> None:
        """
        Generate a beautiful image using users avatar.

        - `[user]` the user whos avatar will be places on the image.
        - `[is_gif=False]` True/False to create a gif if the user has a gif avatar.
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            try:
                file, file_size = await self.make_beautiful(user, is_gif)
            except RuntimeError as e:
                log.error(e)
                await ctx.send("There was an issue getting the template file.")
                return
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await self.safe_send(ctx, None, file, file_size)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def feels(
        self,
        ctx: commands.Context,
        user: Optional[Union[discord.Member, discord.User]] = None,
        is_gif: bool = False,
    ) -> None:
        """
        Generate a feels image using users avatar and role colour.

        - `[user]` the user whos avatar will be places on the image.
        - `[is_gif=False]` True/False to create a gif if the user has a gif avatar.
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            try:
                file, file_size = await self.make_feels(user, is_gif)
            except RuntimeError as e:
                log.error(e)
                await ctx.send("There was an issue getting the template file.")
                return
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await self.safe_send(ctx, None, file, file_size)

    @commands.command(aliases=["isnowillegal"])
    @commands.check(lambda ctx: TRUMP)
    @commands.bot_has_permissions(attach_files=True)
    async def trump(self, ctx: commands.Context, *, message) -> None:
        """
        Generate isnowillegal gif image.

        - `<message>` will be what is pasted on the gif.
        """
        if not TRUMP:
            msg = (
                "The bot owner needs to run " "`pip3 install opencv-python` " "to run this command"
            )
            await ctx.send(msg)
            return
        async with ctx.channel.typing():
            task = functools.partial(self.make_trump_gif, text=message)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, task)
            try:
                file, file_size = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
        await self.safe_send(ctx, None, file, file_size)

    async def make_colour(self, colour: discord.Colour):
        image_path = cog_data_path(self) / "pill.png"
        if not os.path.isfile(image_path) or os.path.getsize(image_path) == 0:
            url = "https://i.imgur.com/n6r04O8.png"
            data = await self.dl_image(url)
            if data is not None:
                with image_path.open("wb") as outfile:
                    outfile.write(data.read())
            else:
                raise RuntimeError(
                    "A required template file is missing. "
                    f"Please visit {url} and save it to `{image_path}`"
                )

        template = Image.open(image_path)
        task = functools.partial(self.colour_convert, template=template, colour=colour)
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            image = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None, None
        image.seek(0)
        template.close()
        file = discord.File(image, filename=f"pill.{WEBP_OR_PNG}")
        file_size = image.tell()
        return file, file_size

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def pill(
        self, ctx: commands.Context, colour: discord.Colour = discord.Colour.from_str("#FF0000")
    ) -> None:
        """
        Generate a pill image to any colour with hex codes.

        - `[colour=#ff0000]` is a hexcode colour or named colour.
         - defaults to red or `#ff0000`.
         - named colours can be found [here.](https://discordpy.readthedocs.io/en/latest/api.html#colour)
        """
        async with ctx.channel.typing():
            try:
                file, file_size = await self.make_colour(colour)
            except RuntimeError as e:
                log.error(e)
                await ctx.send("There was an issue getting the template file.")
                return
            if file is None:
                await ctx.send("Something went wrong sorry!")
                return
        await self.safe_send(ctx, None, file, file_size)

    # Below are all the task handlers so the code is not blocking

    async def make_beautiful(
        self, user: Union[discord.Member, discord.User], is_gif: bool
    ) -> Tuple[Optional[discord.File], int]:
        image_path = cog_data_path(self) / "beautiful.png"
        if not os.path.isfile(image_path) or os.path.getsize(image_path) == 0:
            url = "https://i.imgur.com/kzE9XBE.png"
            data = await self.dl_image(url)
            if data is not None:
                with image_path.open("wb") as outfile:
                    outfile.write(data.read())
            else:
                raise RuntimeError(
                    "A required template file is missing. "
                    f"Please visit {url} and save it to `{image_path}`"
                )

        template = Image.open(image_path)
        if user.display_avatar.is_animated() and is_gif:
            asset = BytesIO(await user.display_avatar.replace(format="gif", size=128).read())
            avatar = Image.open(asset)
            task = functools.partial(self.make_beautiful_gif, template=template, avatar=avatar)

        else:
            asset = BytesIO(await user.display_avatar.replace(format="png", size=128).read())
            avatar = Image.open(asset)
            task = functools.partial(self.make_beautiful_img, template=template, avatar=avatar)
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            template.close()
            return None, 0
        template.close()
        temp.seek(0)
        filename = "beautiful.gif" if is_gif else "beautiful.png"
        file = discord.File(temp, filename=filename)
        file_size = temp.tell()
        return file, file_size

    async def make_feels(
        self, user: discord.User, is_gif: bool
    ) -> Tuple[Optional[discord.File], int]:
        image_path = cog_data_path(self) / "feels.png"
        if not os.path.isfile(image_path) or os.path.getsize(image_path) == 0:
            url = "https://i.imgur.com/4xr6cdw.png"
            data = await self.dl_image(url)
            if data is not None:
                with image_path.open("wb") as outfile:
                    outfile.write(data.read())
            else:
                raise RuntimeError(
                    "A required template file is missing. "
                    f"Please visit {url} and save it to `{image_path}`"
                )

        template = Image.open(image_path)
        colour = user.colour.to_rgb()
        if user.display_avatar.is_animated() and is_gif:
            asset = BytesIO(await user.display_avatar.replace(format="gif", size=64).read())
            avatar = Image.open(asset)
            task = functools.partial(
                self.make_feels_gif, template=template, colour=colour, avatar=avatar
            )
        else:
            asset = BytesIO(await user.display_avatar.replace(format=WEBP_OR_PNG, size=64).read())
            avatar = Image.open(asset)
            task = functools.partial(
                self.make_feels_img, template=template, colour=colour, avatar=avatar
            )
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            template.close()
            return None, 0
        template.close()
        temp.seek(0)
        filename = "feels.gif" if is_gif else f"feels.{WEBP_OR_PNG}"
        file = discord.File(temp, filename=filename)
        file_size = temp.tell()
        return file, file_size

    async def make_wheeze(
        self, text: Union[discord.Member, discord.User, str], is_gif=False
    ) -> Tuple[Optional[discord.File], int]:
        image_path = cog_data_path(self) / "wheeze.jpg"
        if not os.path.isfile(image_path) or os.path.getsize(image_path) == 0:
            url = "https://i.imgur.com/c5uoDcd.jpg"
            data = await self.dl_image(url)
            if data is not None:
                with image_path.open("wb") as outfile:
                    outfile.write(data.read())
            else:
                raise RuntimeError(
                    "A required template file is missing. "
                    f"Please visit {url} and save it to `{image_path}`"
                )

        template = Image.open(image_path)
        avatar = None
        if type(text) == discord.Member:
            user = cast(discord.User, text)
            if user.display_avatar.is_animated() and is_gif:
                asset = BytesIO(await user.display_avatar.replace(format="gif", size=64).read())
                avatar = Image.open(asset)

                task = functools.partial(self.make_wheeze_gif, template=template, avatar=avatar)

            else:
                asset = BytesIO(
                    await user.display_avatar.replace(format=WEBP_OR_PNG, size=64).read()
                )
                avatar = Image.open(asset)
                task = functools.partial(self.make_wheeze_img, template=template, avatar=avatar)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, task)
            try:
                temp: BytesIO = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                template.close()
                return None, 0
        else:
            task = functools.partial(self.make_wheeze_img, template=template, avatar=text)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, task)
            try:
                temp = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                template.close()
                return None, 0
        template.close()
        file_size = temp.tell()
        temp.seek(0)
        filename = "wheeze.gif" if is_gif else f"wheeze.{WEBP_OR_PNG}"
        file = discord.File(temp, filename=filename)
        return file, file_size

    async def face_merge(self, urls: list) -> Tuple[Optional[discord.File], int]:
        images = []
        for u in urls:
            try:
                img_b = await self.dl_image(u)
                if img_b is None:
                    continue
                images.append(img_b)
            except Exception:
                raise
        task = functools.partial(self.face_transition, images=images)
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None, 0
        temp.seek(0)
        file = discord.File(temp, filename="facemerge.gif")
        file_size = temp.tell()
        return file, file_size

    # Below are all the blocking code

    def make_beautiful_gif(self, template: Image.Image, avatar: Image.Image) -> BytesIO:
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = BytesIO()
        for frame in gif_list:
            template = template.convert("RGBA")
            frame = frame.convert("RGBA")
            # frame = frame.rotate(-30, expand=True)
            # frame = frame.resize((60, 60), Image.Resampling.LANCZOS)
            template.paste(frame, (370, 45), frame)
            template.paste(frame, (370, 330), frame)
            # temp2.thumbnail((320, 320), Image.Resampling.LANCZOS)
            img_list.append(template)
            num += 1
            # temp = BytesIO()
            template.save(
                temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0
            )
            temp.name = "beautiful.gif"

        return temp

    def face_transition(self, images: List[BytesIO]) -> BytesIO:
        img_list = []
        base = Image.new("RGBA", (256, 256))
        for image in images[:-1]:
            overlay = Image.open(image)
            overlay = overlay.resize((256, 256), Image.Resampling.LANCZOS)
            overlay = overlay.convert("RGBA")
            if len(overlay.split()) != 4:
                alpha = Image.new("L", overlay.size, 255)
            else:
                alpha = overlay.convert("L")  # Image.new("L", overlay.size, 255)
            overlay.putalpha(alpha)
            for i in range(0, 50):
                base_img = Image.open(images[-1])
                base_img = base_img.convert("RGBA")
                base_img = base_img.resize((256, 256), Image.Resampling.LANCZOS)
                paste_mask = overlay.split()[3].point(lambda x: x * i / 50)
                base_img.paste(overlay, (0, 0), paste_mask)
                # img_list.append(np.array(base_img))
                img_list.append(base_img)
            for i in range(49, -1, -1):
                base_img = Image.open(images[-1])
                base_img = base_img.convert("RGBA")
                base_img = base_img.resize((256, 256), Image.Resampling.LANCZOS)
                paste_mask = overlay.split()[3].point(lambda x: x * i / 50)
                base_img.paste(overlay, (0, 0), paste_mask)
                # img_list.append(np.array(base_img))
                img_list.append(base_img)
        # print(len(img_list))
        temp = BytesIO()
        temp.name = "merge.gif"
        base.save(
            temp,
            format="GIF",
            save_all=True,
            append_images=img_list,
            loop=0,
            duration=20,
            disposal=0,
            optimize=True,
        )
        return temp

    def make_banner(self, text: str, colour: discord.Colour) -> Tuple[discord.File, int]:
        # W, H = (300, 100)
        # im = Image.new("RGBA", (W, H), colour.to_rgb())
        font = ImageFont.truetype(str(bundled_data_path(self) / "impact.ttf"), 18)
        # draw = ImageDraw.Draw(im)
        top, left, bottom, right = font.getbbox(text=text)
        size_w, size_h = (bottom - top, right - left)
        # old = draw.textsize(text, font=font)
        # log.debug("old %s new %s %s", old, size_w, size_h)
        W, H = (size_w + 25, 100)
        im = Image.new("RGBA", (W, H), colour.to_rgb())
        draw = ImageDraw.Draw(im)

        images = []
        for i in range(0, W):
            new_im = Image.new("RGBA", (W, H), colour.to_rgb())
            draw = ImageDraw.Draw(new_im)
            draw.text((((W - size_w) / 4) - i, (100 - size_h) / 2), text, font=font, fill="white")
            draw.text((10 + W - i, (100 - size_h) / 2), text, font=font, fill="white")
            images.append(new_im)

        temp = BytesIO()
        temp.name = "temp.gif"
        im.save(
            temp,
            format="GIF",
            save_all=True,
            optimize=True,
            append_images=images,
            duration=20,
            loop=0,
            disposal=0,
        )
        temp.seek(0)
        file = discord.File(temp)
        file_size = temp.tell()
        return file, file_size

    def make_beautiful_img(self, template: Image.Image, avatar: Image.Image) -> BytesIO:
        # print(template.info)
        template = template.convert("RGBA")
        avatar = avatar.convert("RGBA")
        template.paste(avatar, (370, 45), avatar)
        template.paste(avatar, (370, 330), avatar)
        temp = BytesIO()
        template.save(temp, format=WEBP_OR_PNG)
        temp.name = f"beautiful.{WEBP_OR_PNG}"
        return temp

    def make_wheeze_gif(self, template: Image.Image, avatar: Image.Image) -> BytesIO:
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = None
        for frame in gif_list:
            template = template.convert("RGBA")
            frame = frame.convert("RGBA")
            template.paste(frame, (60, 470), frame)
            img_list.append(template)
            num += 1
            temp = BytesIO()
            template.save(
                temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0
            )
            temp.name = "beautiful.gif"
        return temp

    def make_wheeze_img(self, template: Image.Image, avatar: Image.Image):
        # print(template.info)
        template = template.convert("RGBA")

        if type(avatar) != str:
            avatar = avatar.convert("RGBA")
            template.paste(avatar, (60, 470), avatar)
        else:
            font_loc = str(bundled_data_path(self) / "impact.ttf")
            font1 = ImageFont.truetype(font_loc, 40)
            draw = ImageDraw.Draw(template)
            margin = 40
            offset = 470
            count = 0
            for line in textwrap.wrap(avatar, width=10):
                count += 1
                if count == 6:
                    draw.text((margin, offset), f"{line}...", fill=(0, 0, 0), font=font1)
                    break
                draw.text((margin, offset), f"{line}", fill=(0, 0, 0), font=font1)
                _top, left, _bottom, right = font1.getbbox(text=line)
                h = right - left
                offset += h
        temp = BytesIO()
        template.save(temp, format=WEBP_OR_PNG)
        temp.name = f"wheeze.{WEBP_OR_PNG}"
        return temp

    def make_feels_gif(self, template: Image.Image, colour: str, avatar: Image.Image) -> BytesIO:
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = None
        for frame in gif_list:
            template = template.convert("RGBA")
            # transparency = template.split()[-1].getdata()
            data = np.array(template)
            red, green, blue, alpha = data.T
            blue_areas = (red == 0) & (blue == 255) & (green == 0) & (alpha == 255)
            data[..., :-1][blue_areas.T] = colour
            temp2 = Image.fromarray(data)
            frame = frame.convert("RGBA")
            frame = frame.rotate(-30, expand=True)
            frame = frame.resize((60, 60), Image.Resampling.LANCZOS)
            temp2.paste(frame, (40, 25), frame)
            # temp2.thumbnail((320, 320), Image.Resampling.LANCZOS)
            img_list.append(temp2)
            num += 1
            temp = BytesIO()
            temp2.save(
                temp,
                format="GIF",
                save_all=True,
                append_images=img_list,
                duration=0,
                loop=0,
                transparency=0,
            )
            temp.name = "feels.gif"
        return temp

    def make_feels_img(self, template: Image.Image, colour: str, avatar: Image.Image) -> BytesIO:
        # print(template.info)
        template = template.convert("RGBA")

        # avatar = Image.open(self.files + "temp." + ext)
        # transparency = template.split()[-1].getdata()
        data = np.array(template)
        red, green, blue, alpha = data.T
        blue_areas = (red == 0) & (blue == 255) & (green == 0) & (alpha == 255)
        data[..., :-1][blue_areas.T] = colour
        temp2 = Image.fromarray(data)
        temp2 = temp2.convert("RGBA")
        avatar = avatar.convert("RGBA")
        avatar = avatar.rotate(-30, expand=True)
        avatar = avatar.resize((60, 60), Image.Resampling.LANCZOS)
        temp2.paste(avatar, (40, 25), avatar)
        temp = BytesIO()
        temp2.save(temp, format=WEBP_OR_PNG)
        temp.name = f"feels.{WEBP_OR_PNG}"
        temp2.close()
        return temp

    def colour_convert(self, template: Image.Image, colour: discord.Colour) -> BytesIO:
        template = template.convert("RGBA")
        colour = ImageColor.getrgb(str(colour))
        data = np.array(template)
        red, green, blue, alpha = data.T
        white_areas = (red == 0) & (blue == 0) & (green == 0) & (alpha == 255)
        data[..., :-1][white_areas.T] = colour
        im2 = Image.fromarray(data)
        temp = BytesIO()
        im2.save(temp, format=WEBP_OR_PNG)
        temp.name = f"pill.{WEBP_OR_PNG}"
        return temp

    """Code is from http://isnowillegal.com/ and made to work on redbot"""

    def make_trump_gif(self, text: str) -> Tuple[Optional[discord.File], int]:
        folder = str(bundled_data_path(self)) + "/trump_template"
        jsonPath = os.path.join(folder, "frames.json")

        # Load frames
        frames = json.load(open(jsonPath))

        # Used to compute motion blur
        lastCorners = None
        textImage = self.generateText(text)

        # Will store all gif frames
        frameImages = []

        # Iterate trough frames
        for frame in frames:
            # Load image
            name = frame["file"]
            filePath = os.path.join(folder, name)
            finalFrame = None

            # If it has transformations,
            # process with opencv and convert back to pillow
            if frame["show"]:
                image = cv2.imread(filePath)

                # Do rotoscope
                image = self.rotoscope(image, textImage, frame)

                # Show final result
                # cv2.imshow(name, image)
                finalFrame = self.cvImageToPillow(image)
            else:
                finalFrame = Image.open(filePath)

            frameImages.append(finalFrame)
        temp = BytesIO()
        # Saving...
        frameImages[0].save(
            temp, format="GIF", save_all=True, append_images=frameImages, duration=0, loop=0
        )
        temp.name = "Trump.gif"
        temp.seek(0)
        finalFrame.close()
        file = discord.File(temp)
        file_size = temp.tell()
        temp.close()
        return file, file_size

    def rotoscope(self, dst, warp, properties: dict):
        if not properties["show"]:
            return dst

        corners = properties["corners"]

        wRows, wCols, wCh = warp.shape
        rows, cols, ch = dst.shape

        # Apply blur on warp
        kernel = np.ones((5, 5), np.float32) / 25
        warp = cv2.filter2D(warp, -1, kernel)

        # Prepare points to be matched on Affine Transformation
        pts1 = np.float32([[0, 0], [wCols, 0], [0, wRows]])
        pts2 = np.float32(corners) * 2

        # Enlarge image to multisample
        dst = cv2.resize(dst, (cols * 2, rows * 2))

        # Transform image with the Matrix
        M = cv2.getAffineTransform(pts1, pts2)
        cv2.warpAffine(
            warp,
            M,
            (cols * 2, rows * 2),
            dst,
            flags=cv2.INTER_AREA,
            borderMode=cv2.BORDER_TRANSPARENT,
        )

        # Sample back image size
        dst = cv2.resize(dst, (cols, rows))

        return dst

    def computeAndLoadTextFontForSize(
        self, drawer: ImageDraw.Draw, text: str, maxWidth: int
    ) -> ImageFont:
        # global textFont

        # Measure text and find out position
        maxSize = 50
        minSize = 6
        curSize = maxSize
        textFont = None
        while curSize >= minSize:
            textFont = ImageFont.truetype(
                str(bundled_data_path(self)) + "/impact.ttf", size=curSize
            )
            size = drawer.textbbox((0, 0), text, font=textFont)
            w = size[2] - size[0]
            # w, h = drawer.textsize(text, font=textFont)

            if w > maxWidth:
                curSize -= 4
            else:
                return textFont
        return textFont

    def generateText(self, text: str):
        # global impact, textFont

        txtColor = (20, 20, 20)
        bgColor = (224, 233, 237)
        # bgColor = (100, 0, 0)
        imgSize = (160, 200)

        # Create image
        image = Image.new("RGB", imgSize, bgColor)

        # Draw text on top
        draw = ImageDraw.Draw(image)

        # Load font for text
        textFont = self.computeAndLoadTextFontForSize(draw, text, imgSize[0])
        top, left, bottom, right = textFont.getbbox(text=text)
        w, h = (bottom - top, right - left)
        # w, h = draw.textsize(text, font=textFont)
        xCenter = (imgSize[0] - w) / 2
        yCenter = (50 - h) / 2
        draw.text((xCenter, 10 + yCenter), text, font=textFont, fill=txtColor)
        impact = ImageFont.truetype(str(bundled_data_path(self)) + "/impact.ttf", 46)
        draw.text((12, 70), "IS NOW", font=impact, fill=txtColor)
        draw.text((10, 130), "ILLEGAL", font=impact, fill=txtColor)

        # Convert to CV2
        cvImage = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # cv2.imshow('text', cvImage)

        return cvImage

    def cvImageToPillow(self, cvImage) -> Image:
        cvImage = cv2.cvtColor(cvImage, cv2.COLOR_BGR2RGB)
        return Image.fromarray(cvImage)
