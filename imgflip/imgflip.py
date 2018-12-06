from redbot.core import commands, checks, Config
from random import choice
import aiohttp
from typing import Union
from redbot.core.utils.chat_formatting import pagify

class Imgflip(getattr(commands, "Cog", object)):
    """
        Generate memes from imgflip.com API
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 356889977)
        default_global = {"username": "", "password": ""}
        self.config.register_global(**default_global)
        self.url = "https://api.imgflip.com/caption_image"
        self.search = "https://api.imgflip.com/get_memes"
        self.session = aiohttp.ClientSession(loop=self.bot.loop)


    async def get_meme_id(self, meme):
        url = self.search.format(await self.config.username(), await self.config.password())
        try:
            async with self.session.get(self.search) as r:
                results = await r.json()
            for memes in results["data"]["memes"]:
                if meme.lower() in memes["name"].lower():
                    return memes["id"]
        except:
            return

    @commands.command(alias=["listmemes"])
    async def getmemes(self, ctx):
        """List memes with names that can be used"""
        await ctx.trigger_typing()
        await self.get_memes(ctx)

    async def get_memes(self, ctx):
        url = self.search
        async with self.session.get(self.search) as r:
            results = await r.json()
        memelist = ", ".join(m["name"] for m in results["data"]["memes"])
        memelist += "Find a meme <https://imgflip.com/memetemplates> click blank template and get the Template ID for more!"
        for page in pagify(memelist, [","]):
            await ctx.send(page)
        

    @commands.command()
    async def meme(self, ctx, meme_name:Union[int, str], text_1:str=" ", text_2:str=" "):
        """ 
            Create custom memes from imgflip
            
            All arguments with spaces require \"quotation marks\" to work
            e.g. `[p]meme \"Two Buttons\" \"Make meme in discord\" \"Make meme in paint\"`
            
            Do `[p]getmemes` to see which meme names will work

            You can get meme ID's from https://imgflip.com/memetemplates
            click blank template and use the Template ID in place of meme_name
        """
        await ctx.trigger_typing()
                
        text_1 = text_1[:20] if len(text_1) > 20 else text_1
        text_2 = text_2[:20] if len(text_2) > 20 else text_2
        username = await self.config.username()
        password = await self.config.password()
        if type(meme_name) is str:
            meme = await self.get_meme_id(meme_name)
        else:
            meme = meme_name
        if meme is None:
            await ctx.send("{} doesn't appear to be a meme I can use".format(meme_name))
        try:
            params = {
                "template_id":meme,
                "username": await self.config.username(),
                "password": await self.config.password(),
                "text0":text_1,
                "text1":text_2

            }
            async with self.session.post(self.url, params=params) as r:
                result = await r.json()
            if result["success"]:
                url = result["data"]["url"]
                await ctx.send(url)
            if not result["success"]:
                await ctx.send(result["error_message"])
        except Exception as e:
            print(e)
            await ctx.send("That meme wasn't found!")

    @commands.command(name='imgflipset', aliases=["memeset"])
    @checks.is_owner()
    async def imgflip_set(self, ctx, username:str, password:str):
        """Command for setting required access information for the API"""
        await self.config.username.set(username)
        await self.config.password.set(password)
        await ctx.send("Credentials set!")

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
