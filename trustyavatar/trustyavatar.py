import discord
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path
from redbot.core import checks
from random import choice, randint
from datetime import datetime
import asyncio
import aiohttp
import glob


class TrustyAvatar(getattr(commands, "Cog", object)):
    """Changes the bot's image every so often"""

    def __init__(self, bot):
        self.bot = bot
        self.loop = bot.loop.create_task(self.change_avatar())
        self.activities = [discord.ActivityType.playing, discord.ActivityType.listening, discord.ActivityType.watching]
        self.status ={
                    "neutral": {
                        "status":discord.Status.online, 
                        "game":["Please Remain Calm", "Mind the Gap"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/0aVJqlS.png",
                        "xmas": "https://i.imgur.com/UGOuOp4.png"
                        },
                    "happy": {
                        "status":discord.Status.online,
                        "game":["Take it to Make it"],
                        "type":self.activities,
                        "link": "https://i.imgur.com/bvh93u4.png",
                        "xmas": "https://i.imgur.com/PqVdPj0.png"
                        },
                    "are you kidding me": {
                        "status":discord.Status.idle, 
                        "game":["Obey Posted Limits"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/Pwz7rzs.png",
                        "xmas": "https://i.imgur.com/khUrr4x.png"
                        },
                    "quizzical": {
                        "status": discord.Status.idle, 
                        "game":["Yellow Means Yield"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/VXIUHMb.png",
                        "xmas": "https://i.imgur.com/1Bm9t68.png"
                        },
                    "sad": {
                        "status": discord.Status.dnd, 
                        "game":["No Public Access"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/5BzptFg.png",
                        "xmas": "https://i.imgur.com/SkNB8Pr.png"
                        },
                    "angry": {
                        "status":discord.Status.dnd, 
                        "game":["Hitchhickers May Be Escaping Inmates"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/b4Qpz6V.png",
                        "xmas": "https://i.imgur.com/gRUfLKI.png"
                        },
                    "watching": {
                        "status":discord.Status.dnd, 
                        "game":[" "], 
                        "type":[discord.ActivityType.watching],
                        "link": "https://i.imgur.com/nJXLjip.png",
                        "xmas": "https://i.imgur.com/J98wFhk.png"
                        },
                   }

    @commands.command()
    @checks.is_owner()
    async def checkstatus(self):
        image_name = choice(self.status.keys())
        status = self.status.get(image_name.lower(), None)
        activity = discord.Activity(name=choice(status["game"]), type=choice(status["type"]))
        await self.bot.change_presence(status=status["status"], activity=activity)

    
    async def change_avatar(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("TrustyAvatar"):
            data = None
            try:
                new_avatar = choice(["watching", "happy", "neutral", 
                                     "sad", "angry", "are you kidding me", 
                                     "quizzical"])
                status = self.status.get(new_avatar, None)
                activity = discord.Activity(name=choice(status["game"]), type=choice(status["type"]))
                await self.bot.change_presence(status=status["status"], activity=activity)
            except Exception as e:
                print(e)
            try:
                print("changing avatar to {}".format(new_avatar))
                if datetime.now().month == 12:
                    url = status["xmas"]
                else:
                    url = status["link"]
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as image:
                        data = await image.read()
                await self.bot.user.edit(avatar=data)
            except Exception as e:
                print(e)
            
            await asyncio.sleep(randint(1000, 1500))

    def __unload(self):
        self.loop.cancel()
