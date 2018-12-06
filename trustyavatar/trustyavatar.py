import discord
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path
from redbot.core import checks
from random import choice, randint
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
                    "neutral": {"status":discord.Status.online, "game":["Please Remain Calm", "Mind the Gap"], "type":self.activities},
                    "happy": {"status":discord.Status.online, "game":["Take it to Make it"], "type":self.activities},
                    "are you kidding me": {"status":discord.Status.idle, "game":["Obey Posted Limits"], "type":self.activities},
                    "quizzical": {"status": discord.Status.idle, "game":["Yellow Means Yield"], "type":self.activities},
                    "sad": {"status": discord.Status.dnd, "game":["No Public Access"], "type":self.activities},
                    "angry": {"status":discord.Status.dnd, "game":["Hitchhickers May Be Escaping Inmates"], "type":self.activities},
                    "watching": {"status":discord.Status.dnd, "game":[" "], "type":[discord.ActivityType.watching]},
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
            self.images = glob.glob(str(bundled_data_path(self)) + "/regular/*")
            data = None
            try:
                new_avatar = choice(self.images)
                image_name = new_avatar.split("/")[-1].split(".")[0]
                with open(new_avatar, "rb") as image:
                    data = image.read()
                status = self.status.get(image_name.lower(), None)
                activity = discord.Activity(name=choice(status["game"]), type=choice(status["type"]))
                await self.bot.change_presence(status=status["status"], activity=activity)
            except Exception as e:
                print(e)
            try:
                print("changing avatar to {}".format(image_name))
                await self.bot.user.edit(avatar=data)
            except Exception as e:
                print(e)
            
            await asyncio.sleep(randint(1000, 1500))

    def __unload(self):
        self.loop.cancel()
