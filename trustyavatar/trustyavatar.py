import discord
import asyncio
import aiohttp

from redbot.core import commands, checks, Config
from random import choice, randint
from datetime import datetime



class TrustyAvatar(getattr(commands, "Cog", object)):
    """Changes the bot's image every so often"""

    def __init__(self, bot):
        self.bot = bot
        
        self.activities = [discord.ActivityType.playing, 
                           discord.ActivityType.listening, 
                           discord.ActivityType.watching]
        defaults = {"status":False, 
                   "streaming":False, 
                   "avatar":False,
                   "last_avatar":0.0}
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_global(**defaults)
        self.loop = bot.loop.create_task(self.maybe_change_avatar())
        self.statuses ={
                    "neutral": {
                        "status":discord.Status.online, 
                        "game":["Please Remain Calm", "Mind the Gap"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/9iRBSeI.png",
                        "xmas": "https://i.imgur.com/lSjMH5u.png"
                        },
                    "happy": {
                        "status":discord.Status.online,
                        "game":["Take it to Make it"],
                        "type":self.activities,
                        "link": "https://i.imgur.com/P5rUpET.png",
                        "xmas": "https://i.imgur.com/zlQzAGP.png"
                        },
                    "unamused": {
                        "status":discord.Status.idle, 
                        "game":["Obey Posted Limits"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/Wr3i9CG.png",
                        "xmas": "https://i.imgur.com/Hp7XRjO.png"
                        },
                    "quizzical": {
                        "status": discord.Status.idle, 
                        "game":["Yellow Means Yield"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/qvBCgvU.png",
                        "xmas": "https://i.imgur.com/1jCdG3x.png"
                        },
                    "sad": {
                        "status": discord.Status.dnd, 
                        "game":["No Public Access"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/WwrZCTY.png",
                        "xmas": "https://i.imgur.com/tb1FZjP.png"
                        },
                    "angry": {
                        "status":discord.Status.dnd, 
                        "game":["Hitchhickers May Be Escaping Inmates"], 
                        "type":self.activities,
                        "link": "https://i.imgur.com/0JkYNGZ.png",
                        "xmas": "https://i.imgur.com/hODosRi.png"
                        },
                    "watching": {
                        "status":discord.Status.dnd, 
                        "game":[" "], 
                        "type":[discord.ActivityType.watching],
                        "link": "https://i.imgur.com/Xs4Mwyd.png",
                        "xmas": "https://i.imgur.com/xSLto00.png"
                        },
                   }

    @commands.group(aliases=["ta"])
    @checks.is_owner()
    async def trustyavatar(self, ctx):
        """
            Commands for overriding aspects of the bots avatar changes
        """
        pass

    @trustyavatar.command()
    async def set(self, ctx, *, name:str):
        """
            Manually change preset options

            `name` must be one of neutral, happy, unamused, quizzical,
            sad, angry, or watching
        """
        if name.lower() not in self.statuses:
            return
        else:
            status, activity, url = await self.get_activity(self.statuses[name.lower()])
            await self.change_activity(status=status, activity=activity)
            await self.change_avatar(url)
        await ctx.tick()

    @trustyavatar.command()
    async def status(self, ctx):
        """
            Toggle status automatic changing
        """
        is_override = await self.config.status()
        await self.config.status.set(not is_override)
        await ctx.send("Status override set to " + str(not is_override))

    @trustyavatar.command()
    async def avatar(self, ctx):
        """
            Toggle avatar automatic changing
        """
        is_override = await self.config.avatar()
        await self.config.avatar.set(not is_override)
        await ctx.send("Avatar override set to " + str(not is_override))

    @trustyavatar.command()
    async def streaming(self, ctx):
        """
            Toggle owner streaming sync
        """
        is_streaming = await self.config.streaming()
        await self.config.streaming.set(not is_streaming)
        await ctx.send("Streaming sync set to " + str(not is_streaming))

    async def on_member_update(self, before, after):
        """This essentially syncs streaming status with the bot owner"""
        if before.id != self.bot.owner_id:
            return
        if not await self.config.streaming():
            return
        if type(after.activity) == discord.ActivityType.streaming:
            await self.bot.change_presence(activity=after.activity)

    async def change_avatar(self, url:str):
        now = datetime.now().timestamp()
        last = await self.config.last_avatar()
        if (now-last) > 1000:
            # Some extra checks so we don't get rate limited over reloads/resets
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as image:
                        data = await image.read()
                # await self.bot.user.edit(avatar=data)
            except Exception as e:
                print(e)
            await self.config.last_avatar.set(now)
        

    async def change_activity(self, status:discord.Status, activity:discord.ActivityType):
        try:
            await self.bot.change_presence(status=status, activity=activity)
        except Exception as e:
            print(e)

    async def get_activity(self, new_status:dict) -> tuple:
        """
            This will return which avatar, status, and activity to use
        """
        date = datetime.now()
        activity = None
        status = None
        if date.month == 12 and date.day <= 25:
                url = status["xmas"]
                activity = discord.Activity(name="Merry Christmas!", 
                                            type=discord.ActivityType.playing)
                status = discord.Status.online
        elif (date.month == 12 and date.day >= 30) or (date.month == 1 and date.day == 1):
            url = new_status["link"]
            activity = discord.Activity(name="Happy New Year!", 
                                        type=discord.ActivityType.playing)
            status = discord.Status.online
        else:
            url = new_status["link"]
            activity = discord.Activity(name=choice(new_status["game"]), 
                                        type=choice(new_status["type"]))
            status = new_status["status"]
        return status, activity, url

    async def get_bot_owner(self):
        """
            Probably somewhat expensive once we start scaling
            Hopefully we can get owner as a member object easier in the future
            without hard coding a server to search for the owner of the bot
        """
        for member in self.bot.get_all_members():
            if member.id == self.bot.owner_id:
                return member

    async def maybe_change_avatar(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("TrustyAvatar"):

            new_avatar = choice([s for s in self.statuses])
            new_status = self.statuses.get(new_avatar, None)
            status, activity, url = await self.get_activity(new_status)
            owner = await self.get_bot_owner()
            is_streaming = (type(owner.activity) == discord.ActivityType.streaming)
            if await self.config.streaming():
                if is_streaming:
                    await self.change_activity(None, owner.activity)
            if await self.config.status() and not is_streaming:
                # we don't want to override the streaming status if the owner is streaming
                await self.change_activity(status, activity)
            if await self.config.avatar():
                await self.change_avatar(url)
                print("changing avatar to {}".format(new_avatar))
            await asyncio.sleep(randint(1000, 1500))

    def __unload(self):
        self.loop.cancel()
