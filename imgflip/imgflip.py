from redbot.core import commands, checks, Config
from random import choice
import aiohttp
from typing import Union
from redbot.core.utils.chat_formatting import pagify
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

SEARCH_URL = "https://api.imgflip.com/get_memes"
CAPTION_URL = "https://api.imgflip.com/caption_image"


class Meme(Converter):
    """
    This will accept user ID's, mentions, and perform a fuzzy search for 
    members within the guild and return a list of member objects
    matching partial names

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """

    async def convert(self, ctx, argument):
        result = None
        if not argument.isdigit():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(SEARCH_URL) as r:
                        results = await r.json()
                for memes in results["data"]["memes"]:
                    if argument.lower() in memes["name"].lower():
                        result = memes["id"]
            except:
                result = None

        else:
            result = argument

        if result is None:
            raise BadArgument('Meme "{}" not found'.format(argument))

        return result


class Imgflip(getattr(commands, "Cog", object)):
    """
        Generate memes from imgflip.com API
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 356889977)
        default_global = {"username": "", "password": ""}
        self.config.register_global(**default_global)

    async def get_meme(self, meme, text_0, text_1):
        try:
            params = {
                "template_id": meme,
                "username": await self.config.username(),
                "password": await self.config.password(),
                "text0": text_0,
                "text1": text_1,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(CAPTION_URL, params=params) as r:
                    result = await r.json()
            if result["success"]:
                return result["data"]["url"]
            if not result["success"]:
                return
        except Exception as e:
            print(e)
            return

    @commands.command(alias=["listmemes"])
    async def getmemes(self, ctx):
        """List memes with names that can be used"""
        await ctx.trigger_typing()
        await self.get_memes(ctx)

    async def get_memes(self, ctx):
        async with aiohttp.ClientSession() as session:
            async with session.get(SEARCH_URL) as r:
                results = await r.json()
        memelist = ", ".join(m["name"] for m in results["data"]["memes"])
        memelist += (
            "Find a meme <https://imgflip.com/memetemplates> "
            "click blank template and get the Template ID for more!"
        )
        for page in pagify(memelist, [","]):
            await ctx.send(page)

    @commands.command()
    async def meme(self, ctx, meme_name: Meme, *, text: str):
        """ 
            Create custom memes from imgflip
            
            `meme_name` can be the name of the meme to use or the ID from imgflip
            `text` can one or two lines of text separated by `;`
            Do `[p]getmemes` to see which meme names will work

            You can get meme ID's from https://imgflip.com/memetemplates
            click blank template and use the Template ID in place of meme_name
        """
        await ctx.trigger_typing()
        for member in ctx.message.mentions:
            text = text.replace(member.mention, member.display_name.replace(";", ""))
        text = text.split(";")
        if len(text) == 1:
            text_0 = text[0]
            text_1 = " "
        else:
            text_0 = text[0]
            text_1 = text[1]
        url = await self.get_meme(meme_name, text_0, text_1)
        await ctx.send(url)

    @commands.command(name="imgflipset", aliases=["memeset"])
    @checks.is_owner()
    async def imgflip_set(self, ctx, username: str, password: str):
        """Command for setting required access information for the API"""
        await self.config.username.set(username)
        await self.config.password.set(password)
        await ctx.send("Credentials set!")
