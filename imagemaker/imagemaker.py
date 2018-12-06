import aiohttp
import discord
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path
from io import BytesIO, StringIO
import sys
import functools
import asyncio
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageSequence
import numpy as np
import os
import json
from copy import copy


try:
    import cv2
    TRUMP = True
except ImportError:
    TRUMP = False

class ImageMaker(getattr(commands, "Cog", object)):
    """
        Create various fun images
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.textFont = None
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    async def dl_image(self, url):
        async with self.session.get(url) as resp:
            test = await resp.read()
            return BytesIO(test)

    @commands.command(pass_context=True)
    async def beautiful(self, ctx, user:discord.Member=None):
        """
            Generate a beautiful image using users avatar

            `user` the user whos avatar will be places on the image
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            beautiful_img = await self.make_beautiful(user)
            if beautiful_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(beautiful_img)
            # ext = await self.make_beautiful(user)
            await ctx.send(file=file)

    @commands.command(pass_context=True)
    async def feels(self, ctx, user:discord.Member=None):
        """
            Generate a feels image using users avatar and role colour

            `user` the user whos avatar will be places on the image
        """
        if user is None:
            user = ctx.message.author
        async with ctx.channel.typing():
            feels_img = await self.make_feels(user)
            if feels_img is None:
                await ctx.send("sorry something went wrong!")
                return
            file = discord.File(feels_img)
            # ext = await self.make_feels(user)
            await ctx.send(file=file)

    @commands.command(aliases=["isnowillegal"])
    async def trump(self, ctx, *, message):
        """
            Generate isnowillegal gif image

            `message` will be what is pasted on the gif
        """
        if not TRUMP:
            await ctx.send("The bot owner needs to run `pip3 install opencv-python` to run this command")
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
    async def redpill(self, ctx):
        """Generate a Red Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #FF0000"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def bluepill(self, ctx):
        """Generate a Blue Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #0000FF"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def blackpill(self, ctx):
        """Generate a Black Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #000000"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def purplepill(self, ctx):
        """Generate a Purple Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #800080"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def yellowpill(self, ctx):
        """Generate a Yellow Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #FFFF00"
        ctx.bot.dispatch("message", msg)

    @commands.command()
    async def greenpill(self, ctx):
        """Generate a Green Pill"""
        msg = copy(ctx.message)
        msg.content = ctx.prefix + "pill #008000"
        ctx.bot.dispatch("message", msg)

    async def make_colour(self, colour):
        task = functools.partial(self.colour_convert,colour=colour)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            image = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return
        image.seek(0)
        return image

    @commands.command()
    async def pill(self, ctx, colour="#FF0000"):
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

    def make_beautiful_gif(self, avatar):
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = None
        for frame in gif_list:
            template = Image.open(str(bundled_data_path(self)) + "/beautiful.png")
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
            template.save(temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0)
            temp.name = "beautiful.gif"
            if sys.getsizeof(temp) < 8000000 and sys.getsizeof(temp) > 7000000:
                break
        return temp

    def make_beautiful_img(self, avatar):
        template = Image.open(str(bundled_data_path(self)) + "/beautiful.png")
        # print(template.info)
        template = template.convert("RGBA") 
        avatar = avatar.convert("RGBA")       
        template.paste(avatar, (370, 45), avatar)
        template.paste(avatar, (370, 330), avatar)
        temp = BytesIO()
        template.save(temp, format="PNG")
        temp.name = "beautiful.png"
        return temp

    async def make_beautiful(self, user):

        if user.is_avatar_animated():
            avatar = Image.open(await self.dl_image(user.avatar_url_as(format="gif", size=128)))
            task = functools.partial(self.make_beautiful_gif, avatar=avatar)
            
        else:
            avatar = Image.open(await self.dl_image(user.avatar_url_as(format="png", size=128)))
            task = functools.partial(self.make_beautiful_img, avatar=avatar)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            temp = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return
        temp.seek(0)
        return temp

    def make_feels_gif(self, colour, avatar):
        gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
        img_list = []
        num = 0
        temp = None
        for frame in gif_list:
            template = Image.open(str(bundled_data_path(self)) + "/pepetemplate.png")
            template = template.convert("RGBA")
            transparency = template.split()[-1].getdata()
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
            temp2.save(temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0, transparency=0)
            temp.name = "feels.gif"
            if sys.getsizeof(temp) < 8000000 and sys.getsizeof(temp) > 7000000:
                break
        return temp

    def make_feels_img(self, colour, avatar):
        template = Image.open(str(bundled_data_path(self)) + "/pepetemplate.png")
        # print(template.info)
        template = template.convert("RGBA")
        
        # avatar = Image.open(self.files + "temp." + ext)
        transparency = template.split()[-1].getdata()
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
        return temp

    async def make_feels(self, user):
        colour = user.colour.to_rgb()
        if user.is_avatar_animated():
            avatar = Image.open(await self.dl_image(user.avatar_url_as(format="gif", size=64)))
            task = functools.partial(self.make_feels_gif, colour=colour, avatar=avatar)
        else:
            avatar = Image.open(await self.dl_image(user.avatar_url_as(format="png", size=64)))
            task = functools.partial(self.make_feels_img, colour=colour, avatar=avatar)
        task = self.bot.loop.run_in_executor(None, task)
        try:
            temp = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return
        temp.seek(0)
        return temp

    def colour_convert(self, colour="#FF0000"):
        im = Image.open(str(bundled_data_path(self)) + "/blackpill.png")
        im = im.convert('RGBA')
        colour = ImageColor.getrgb(colour)
        data = np.array(im)
        red, green, blue, alpha = data.T
        white_areas = (red == 0) & (blue == 0) & (green == 0) & (alpha == 255)
        data[..., :-1][white_areas.T] = colour
        im2 = Image.fromarray(data)
        temp = BytesIO()
        im2.save(temp, format="PNG")
        temp.name = "pill.png"
        return temp

    """Code is from http://isnowillegal.com/ and made to work on redbot"""
    def make_trump_gif(self, text):
        folder = str(bundled_data_path(self))+"/trump_template"
        jsonPath = os.path.join(folder, 'frames.json')

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
            name = frame['file']
            filePath = os.path.join(folder, name)
            finalFrame = None

            # If it has transformations,
            # process with opencv and convert back to pillow
            if frame['show'] == True:
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
        frameImages[0].save(temp, format="GIF", save_all=True, append_images=frameImages, duration=0, loop=0)
        temp.name = "Trump.gif"
        temp.seek(0)
        return temp


    def rotoscope(self, dst, warp, properties):
        if properties['show'] == False:
            return dst

        corners = properties['corners']

        wRows, wCols, wCh = warp.shape
        rows, cols, ch = dst.shape

        # Apply blur on warp
        kernel = np.ones((5, 5), np.float32) / 25
        warp = cv2.filter2D(warp, -1, kernel)

        # Prepare points to be matched on Affine Transformation
        pts1 = np.float32([[0, 0],[wCols, 0],[0, wRows]])
        pts2 = np.float32(corners) * 2

        # Enlarge image to multisample
        dst = cv2.resize(dst, (cols * 2, rows * 2))

        # Transform image with the Matrix
        M = cv2.getAffineTransform(pts1, pts2)
        cv2.warpAffine(warp, M, (cols * 2, rows * 2), dst, flags=cv2.INTER_AREA, borderMode=cv2.BORDER_TRANSPARENT)

        # Sample back image size
        dst = cv2.resize(dst, (cols, rows))

        return dst


    def computeAndLoadTextFontForSize(self, drawer, text, maxWidth):
        # global textFont

        # Measure text and find out position
        maxSize = 50
        minSize = 6
        curSize = maxSize
        while curSize >= minSize:
            self.textFont = ImageFont.truetype(str(bundled_data_path(self))+'/impact.ttf', size=curSize)
            w, h = drawer.textsize(text, font=self.textFont)
            
            if w > maxWidth:
                curSize -= 4
            else:
                return self.textFont
        return self.textFont

    def generateText(self, text):
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
        if self.textFont == None:
            self.textFont = self.computeAndLoadTextFontForSize(draw, text, imgSize[0])
            
        w, h = draw.textsize(text, font=self.textFont)
        xCenter = (imgSize[0] - w) / 2
        yCenter = (50 - h) / 2
        draw.text((xCenter, 10 + yCenter), text, font=self.textFont, fill=txtColor)
        impact = ImageFont.truetype(str(bundled_data_path(self))+'/impact.ttf', 46)
        draw.text((12, 70), "IS NOW", font=impact, fill=txtColor)
        draw.text((10, 130), "ILLEGAL", font=impact, fill=txtColor)
        
        # Convert to CV2
        cvImage = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # cv2.imshow('text', cvImage)
        
        return cvImage

    def cvImageToPillow(self, cvImage):
        cvImage = cv2.cvtColor(cvImage, cv2.COLOR_BGR2RGB)
        return Image.fromarray(cvImage)

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
