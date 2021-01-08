import asyncio
import functools
import json
import os
import sys
import textwrap
from copy import copy
from io import BytesIO
from typing import Optional, Union, cast

import aiohttp
import discord
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageSequence
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path

from .converter import ImageFinder

try:
    import cv2

    TRUMP = True
except ImportError:
    TRUMP = False

try:
    import imageio

    BANNER = True
except ImportError:
    BANNER = False


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
    __version__ = "1.5.1"

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

    async def dl_image(self, url: str) -> Optional[BytesIO]:
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                if resp.status == 200:
                    test = await resp.read()
                    return BytesIO(test)
                else:
                    return None

    @commands.command()
    async def wheeze(
        self, ctx: commands.Context, *, text: Union[discord.Member, str] = None
    ) -> None:
        """
        Generate a wheeze image with text or a user avatar

        `text` the text or user avatar who will be placed in the bottom pane
        """
        if text is None:
            text = ctx.message.author
        async with ctx.channel.typing():
            wheeze_img = await self.make_wheeze(text)
            if wheeze_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(wheeze_img)
            # ext = await self.make_beautiful(user)
            await ctx.send(file=file)

    @commands.command()
    async def facemerge(self, ctx: commands.Context, *, urls: ImageFinder) -> None:
        """
        Generate a gif of two images fading into eachother
        """
        if len(urls) < 2:
            urls = await ImageFinder().search_for_images(ctx)
            if len(urls) < 2:
                return await ctx.send("You must supply at least 2 image links.")
        async with ctx.channel.typing():
            face_img = await self.face_merge(urls)
            if face_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(face_img)
            # ext = await self.make_beautiful(user)
            await ctx.send(file=file)

    @commands.command()
    @commands.check(lambda ctx: BANNER)
    async def scrollbanner(
        self, ctx: commands.Context, colour: Optional[discord.Colour] = (255, 0, 0), *, text: str
    ) -> None:
        """
        Generate a scrolling text gif banner
        """
        if isinstance(colour, discord.Colour):
            colour = colour.to_rgb() + (0,)
        async with ctx.channel.typing():
            task = functools.partial(self.make_banner, text=text, colour=colour)
            task = ctx.bot.loop.run_in_executor(None, task)
            try:
                image = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            file = discord.File(image)
            await ctx.send(files=[file])

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def obama(self, ctx: commands.Context, *, text: str) -> None:
        """
        Synthesize video clips of Obama
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
                await ctx.send(files=[file])

    @commands.command()
    async def gwheeze(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """
        Generate a gif wheeze image if user has a gif avatar

        `member` the member whos avatar will be pasted on the image
        defaults to author
        """
        if member is None:
            member = ctx.message.author
        async with ctx.channel.typing():
            wheeze_img = await self.make_wheeze(member, True)
            if wheeze_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(wheeze_img)
            # ext = await self.make_beautiful(user)
            await ctx.send(file=file)

    @commands.command()
    async def beautiful(
        self, ctx: commands.Context, user: discord.Member = None, is_gif=False
    ) -> None:
        """
        Generate a beautiful image using users avatar

        `user` the user whos avatar will be places on the image
        `is_gif` True/False to create a gif if the user has a gif avatar
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            beautiful_img = await self.make_beautiful(user, is_gif)
            if beautiful_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(beautiful_img)
            # ext = await self.make_beautiful(user)
            await ctx.send(file=file)

    @commands.command()
    async def feels(
        self, ctx: commands.Context, user: discord.Member = None, is_gif=False
    ) -> None:
        """
        Generate a feels image using users avatar and role colour

        `user` the user whos avatar will be places on the image
        `is_gif` True/False to create a gif if the user has a gif avatar
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            feels_img = await self.make_feels(user, is_gif)
            if feels_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(feels_img)
            # ext = await self.make_feels(user)
            await ctx.send(file=file)

    @commands.command(aliases=["isnowillegal"])
    @commands.check(lambda ctx: TRUMP)
    async def trump(self, ctx: commands.Context, *, message) -> None:
        """
        Generate isnowillegal gif image

        `message` will be what is pasted on the gif
        """
        if not TRUMP:
            msg = (
                "The bot owner needs to run " "`pip3 install opencv-python` " "to run this command"
            )
            await ctx.send(msg)
            return
        async with ctx.channel.typing():
            task = functools.partial(self.make_trump_gif, text=message)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                temp = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            image = discord.File(temp)
            await ctx.send(file=image)

    @commands.command()
    async def redpill(self, ctx: commands.Context) -> None:
        """Generate a Red Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #FF0000"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def bluepill(self, ctx: commands.Context) -> None:
        """Generate a Blue Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #0000FF"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def blackpill(self, ctx: commands.Context) -> None:
        """Generate a Black Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #000000"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def purplepill(self, ctx: commands.Context) -> None:
        """Generate a Purple Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #800080"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def yellowpill(self, ctx: commands.Context) -> None:
        """Generate a Yellow Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #FFFF00"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def greenpill(self, ctx: commands.Context) -> None:
        """Generate a Green Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #008000"
        ctx.bot.dispatch("message", msg)

    async def make_colour(self, colour):
        template_str = "https://i.imgur.com/n6r04O8.png"
        template = Image.open(await self.dl_image(template_str))
        task = functools.partial(self.colour_convert, template=template, colour=colour)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            image = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return
        image.seek(0)
        template.close()
        return image

    @commands.command()
    async def pill(self, ctx: commands.Context, colour="#FF0000") -> None:
        """
        Generate a pill image to any colour with hex codes

        `colour` is a hexcode colour
        """
        async with ctx.channel.typing():
            pill_image = await self.make_colour(colour)
            if pill_image is None:
                await ctx.send("Something went wrong sorry!")
                return
            image = discord.File(pill_image)
            await ctx.send(file=image)

    # Below are all the task handlers so the code is not blocking

    async def make_beautiful(self, user: discord.User, is_gif: bool) -> Optional[BytesIO]:
        template_str = "https://i.imgur.com/kzE9XBE.png"
        template = Image.open(await self.dl_image(template_str))
        if user.is_avatar_animated() and is_gif:
            avatar = Image.open(
                await self.dl_image(str(user.avatar_url_as(format="gif", size=128)))
            )
            task = functools.partial(self.make_beautiful_gif, template=template, avatar=avatar)

        else:
            avatar = Image.open(
                await self.dl_image(str(user.avatar_url_as(format="png", size=128)))
            )
            task = functools.partial(self.make_beautiful_img, template=template, avatar=avatar)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            avatar.close()
            template.close()
            return None
        avatar.close()
        template.close()
        temp.seek(0)
        return temp

    async def make_feels(self, user: discord.User, is_gif: bool) -> Optional[BytesIO]:
        template_str = "https://i.imgur.com/4xr6cdw.png"
        template = Image.open(await self.dl_image(template_str))
        colour = user.colour.to_rgb()
        if user.is_avatar_animated() and is_gif:
            avatar = Image.open(
                await self.dl_image(str(user.avatar_url_as(format="gif", size=64)))
            )
            task = functools.partial(
                self.make_feels_gif, template=template, colour=colour, avatar=avatar
            )
        else:
            avatar = Image.open(
                await self.dl_image(str(user.avatar_url_as(format="png", size=64)))
            )
            task = functools.partial(
                self.make_feels_img, template=template, colour=colour, avatar=avatar
            )
        task = self.bot.loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            avatar.close()
            template.close()
            return None
        avatar.close()
        template.close()
        temp.seek(0)
        return temp

    async def make_wheeze(
        self, text: Union[discord.Member, str], is_gif=False
    ) -> Optional[BytesIO]:
        template_path = "https://i.imgur.com/c5uoDcd.jpg"
        template = Image.open(await self.dl_image(template_path))
        avatar = None
        if type(text) == discord.Member:
            user = cast(discord.User, text)
            if user.is_avatar_animated() and is_gif:
                avatar = Image.open(
                    await self.dl_image(str(user.avatar_url_as(format="gif", size=64)))
                )

                task = functools.partial(self.make_wheeze_gif, template=template, avatar=avatar)

            else:
                avatar = Image.open(
                    await self.dl_image(str(user.avatar_url_as(format="png", size=64)))
                )
                task = functools.partial(self.make_wheeze_img, template=template, avatar=avatar)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                temp: BytesIO = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                avatar.close()
                template.close()
                return None
        else:
            task = functools.partial(self.make_wheeze_img, template=template, avatar=text)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                temp = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                template.close()
                return None
        if avatar:
            avatar.close()
        template.close()
        temp.seek(0)
        return temp

    async def face_merge(self, urls: list) -> Optional[BytesIO]:
        images = [await self.dl_image(u) for u in urls]
        task = functools.partial(self.face_transition, images=images)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            temp = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None
        temp.seek(0)
        return temp

    # Below are all the blocking code

    def make_beautiful_gif(self, template: Image, avatar: Image) -> BytesIO:
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = None
        for frame in gif_list:
            template = template.convert("RGBA")
            frame = frame.convert("RGBA")
            # frame = frame.rotate(-30, expand=True)
            # frame = frame.resize((60, 60), Image.ANTIALIAS)
            template.paste(frame, (370, 45), frame)
            template.paste(frame, (370, 330), frame)
            # temp2.thumbnail((320, 320), Image.ANTIALIAS)
            img_list.append(template)
            num += 1
            temp = BytesIO()
            template.save(
                temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0
            )
            temp.name = "beautiful.gif"
            if sys.getsizeof(temp) < 8000000 and sys.getsizeof(temp) > 7000000:
                break
        return temp

    def face_transition(self, images: list) -> BytesIO:
        img_list = []
        # base = Image.open(images[-1])
        for image in images[:-1]:
            overlay = Image.open(image)
            overlay = overlay.resize((256, 256), Image.ANTIALIAS)
            overlay = overlay.convert("RGBA")
            if len(overlay.split()) != 4:
                alpha = Image.new("L", overlay.size, 255)
            else:
                alpha = overlay.convert("L")  # Image.new("L", overlay.size, 255)
            overlay.putalpha(alpha)
            for i in range(0, 50):
                base_img = Image.open(images[-1])
                base_img = base_img.convert("RGBA")
                base_img = base_img.resize((256, 256), Image.ANTIALIAS)
                paste_mask = overlay.split()[3].point(lambda x: x * i / 50)
                base_img.paste(overlay, (0, 0), paste_mask)
                img_list.append(np.array(base_img))
            for i in range(49, -1, -1):
                base_img = Image.open(images[-1])
                base_img = base_img.convert("RGBA")
                base_img = base_img.resize((256, 256), Image.ANTIALIAS)
                paste_mask = overlay.split()[3].point(lambda x: x * i / 50)
                base_img.paste(overlay, (0, 0), paste_mask)
                img_list.append(np.array(base_img))
        # print(len(img_list))
        temp = BytesIO()
        temp.name = "merge.gif"
        imageio.mimwrite(temp, img_list, "gif", duration=0.02)
        overlay.close()
        base_img.close()
        return temp

    def make_banner(self, text: str, colour: str) -> BytesIO:
        im = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
        font = ImageFont.truetype(str(bundled_data_path(self) / "impact.ttf"), 18)
        draw = ImageDraw.Draw(im)
        size_w, size_h = draw.textsize(text, font=font)
        W, H = (size_w + 25, 100)

        images = []
        for i in range(0, W):
            im = Image.new("RGBA", (W, H), colour)
            draw = ImageDraw.Draw(im)
            draw.text((((W - size_w) / 2) - i, (100 - size_h) / 2), text, font=font, fill="white")
            draw.text((10 + W - i, (100 - size_h) / 2), text, font=font, fill="white")
            images.append(np.array(im))

        temp = BytesIO()
        temp.name = "temp.gif"
        imageio.mimwrite(temp, images, "gif", duration=0.02)
        temp.seek(0)
        im.close()
        return temp

    def make_beautiful_img(self, template: Image, avatar: Image) -> BytesIO:
        # print(template.info)
        template = template.convert("RGBA")
        avatar = avatar.convert("RGBA")
        template.paste(avatar, (370, 45), avatar)
        template.paste(avatar, (370, 330), avatar)
        temp = BytesIO()
        template.save(temp, format="PNG")
        temp.name = "beautiful.png"
        return temp

    def make_wheeze_gif(self, template: Image, avatar: Image) -> BytesIO:
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
            if sys.getsizeof(temp) < 8000000 and sys.getsizeof(temp) > 7000000:
                break
        return temp

    def make_wheeze_img(self, template: Image, avatar: Image):
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
                offset += font1.getsize(line)[1]
        temp = BytesIO()
        template.save(temp, format="PNG")
        temp.name = "wheeze.png"
        return temp

    def make_feels_gif(self, template: Image, colour: str, avatar: Image) -> BytesIO:
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
            frame = frame.resize((60, 60), Image.ANTIALIAS)
            temp2.paste(frame, (40, 25), frame)
            # temp2.thumbnail((320, 320), Image.ANTIALIAS)
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
            if sys.getsizeof(temp) < 8000000 and sys.getsizeof(temp) > 7000000:
                break
        return temp

    def make_feels_img(self, template: Image, colour: str, avatar: Image) -> BytesIO:
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
        avatar = avatar.resize((60, 60), Image.ANTIALIAS)
        temp2.paste(avatar, (40, 25), avatar)
        temp = BytesIO()
        temp2.save(temp, format="PNG")
        temp.name = "feels.png"
        temp2.close()
        return temp

    def colour_convert(self, template: Image, colour: Optional[str] = "#FF0000") -> BytesIO:
        template = template.convert("RGBA")
        colour = ImageColor.getrgb(colour)
        data = np.array(template)
        red, green, blue, alpha = data.T
        white_areas = (red == 0) & (blue == 0) & (green == 0) & (alpha == 255)
        data[..., :-1][white_areas.T] = colour
        im2 = Image.fromarray(data)
        temp = BytesIO()
        im2.save(temp, format="PNG")
        temp.name = "pill.png"
        im2.close()
        return temp

    """Code is from http://isnowillegal.com/ and made to work on redbot"""

    def make_trump_gif(self, text: str) -> BytesIO:
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
        return temp

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
            w, h = drawer.textsize(text, font=textFont)

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

        w, h = draw.textsize(text, font=textFont)
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
