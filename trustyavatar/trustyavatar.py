import asyncio
import functools
import logging
import sys
from datetime import datetime
from io import BytesIO
from random import choice, randint
from typing import Optional, Tuple, Union

import aiohttp
import discord
from PIL import Image, ImageSequence
from redbot.core import Config, VersionInfo, checks, commands, version_info

log = logging.getLogger("red.trusty-cogs.TrustyAvatar")


class TrustyAvatar(commands.Cog):
    """Changes the bot's image every so often"""

    __author__ = ["TrustyJAID"]
    __version__ = "1.2.3"

    def __init__(self, bot):
        self.bot = bot

        self.activities = [
            discord.ActivityType.playing,
            discord.ActivityType.listening,
            discord.ActivityType.watching,
        ]
        defaults = {
            "status": False,
            "streaming": False,
            "avatar": False,
            "last_avatar": 0.0,
            "search_guild": None,
        }
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_global(**defaults)
        self.loop = bot.loop.create_task(self.maybe_change_avatar())
        self.statuses = {
            "neutral": {
                "status": discord.Status.online,
                "game": ["Please Remain Calm", "Mind the Gap"],
                "type": self.activities,
                "link": "https://i.imgur.com/9iRBSeI.png",
                "xmas": "https://i.imgur.com/lSjMH5u.png",
                "transparent": "https://i.imgur.com/z1sHKYA.png",
            },
            "happy": {
                "status": discord.Status.online,
                "game": ["Take it to Make it"],
                "type": self.activities,
                "link": "https://i.imgur.com/P5rUpET.png",
                "xmas": "https://i.imgur.com/zlQzAGP.png",
                "transparent": "https://i.imgur.com/b21iEMj.png",
            },
            "unamused": {
                "status": discord.Status.idle,
                "game": ["Obey Posted Limits"],
                "type": self.activities,
                "link": "https://i.imgur.com/Wr3i9CG.png",
                "xmas": "https://i.imgur.com/Hp7XRjO.png",
                "transparent": "https://i.imgur.com/cZoFosX.png",
            },
            "quizzical": {
                "status": discord.Status.idle,
                "game": ["Yellow Means Yield"],
                "type": self.activities,
                "link": "https://i.imgur.com/qvBCgvU.png",
                "xmas": "https://i.imgur.com/1jCdG3x.png",
                "transparent": "https://i.imgur.com/3WBrM66.png",
            },
            "sad": {
                "status": discord.Status.dnd,
                "game": ["No Public Access"],
                "type": self.activities,
                "link": "https://i.imgur.com/WwrZCTY.png",
                "xmas": "https://i.imgur.com/tb1FZjP.png",
                "transparent": "https://i.imgur.com/wPAdZ7S.png",
            },
            "angry": {
                "status": discord.Status.dnd,
                "game": ["Hitchhickers May Be Escaping Inmates"],
                "type": self.activities,
                "link": "https://i.imgur.com/0JkYNGZ.png",
                "xmas": "https://i.imgur.com/hODosRi.png",
                "transparent": "https://i.imgur.com/L7PKqZF.png",
            },
            "watching": {
                "status": discord.Status.dnd,
                "game": [" "],
                "type": [discord.ActivityType.watching],
                "link": "https://i.imgur.com/Xs4Mwyd.png",
                "xmas": "https://i.imgur.com/xSLto00.png",
                "transparent": "https://i.imgur.com/X6SXXvx.png",
            },
        }

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

    async def dl_image(self, url: str) -> BytesIO:
        """Download bytes like object of user avatar"""
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as resp:
                test = await resp.read()
                return BytesIO(test)

    def replace_colour(self, img: Image, to_colour: tuple) -> BytesIO:
        """https://stackoverflow.com/questions/765736/using-pil-to-make-all-white-pixels-transparent"""
        img = Image.open(img)
        img = img.convert("RGBA")
        datas = img.getdata()
        # reds = [94, 221, 170]
        # greens = [123, 227, 185]
        # blues = [75, 217, 160]
        newData = []
        for item in datas:
            # if item[0] in [94] and item[1] in [123] and item[2] in [75]:
            if item[3] == 0:
                newData.append(to_colour)
            else:
                newData.append(item)

        img.putdata(newData)
        temp = BytesIO()
        img.save(temp, format="PNG")
        temp.name = "trustyavatar.png"
        temp.seek(0)
        return temp

    def make_new_avatar(
        self, author_avatar: BytesIO, choice_avatar: BytesIO, is_gif: bool
    ) -> Optional[BytesIO]:
        avatar = Image.open(author_avatar)
        new_avatar = Image.open(choice_avatar)
        new_avatar = new_avatar.convert("RGBA")
        if is_gif:
            gif_list = [frame.copy() for frame in ImageSequence.Iterator(avatar)]
            img_list = []
            for frame in gif_list:
                temp2 = Image.new("RGBA", frame.size)
                temp2.paste(frame, (0, 0))
                w, h = frame.size
                new_avatar = new_avatar.resize((w, h))
                temp2.paste(new_avatar, (0, 0), new_avatar)
                temp2 = temp2.resize((200, 200), Image.ANTIALIAS)
                img_list.append(temp2)
                temp = BytesIO()
                temp2.save(
                    temp, format="GIF", save_all=True, append_images=img_list, duration=0, loop=0
                )
                temp.name = "trustyavatar.gif"
                if sys.getsizeof(temp) > 7000000 and sys.getsizeof(temp) < 8000000:
                    break
        else:
            temp2 = avatar.copy()
            w, h = temp2.size
            new_avatar = new_avatar.resize((w, h))
            temp2.paste(new_avatar, (0, 0), new_avatar)
            temp2 = temp2.resize((200, 200), Image.ANTIALIAS)
            temp = BytesIO()
            temp2.save(temp, format="PNG")
            temp.name = "trustyavatar.png"
        if temp:
            temp.seek(0)
        return temp

    @commands.command(aliases=["ta"])
    async def trustyavatar(
        self,
        ctx: commands.Context,
        style: Optional[Union[discord.Member, discord.Colour]] = None,
        face: Optional[str] = None,
        is_gif: bool = False,
    ):
        """
        Create your own avatar like TrustyBot's

        `style` can be a user or a colour code if none is supplied the authors avatar
        is used
        `face` must be one of neutral, happy, unamused, quizzical,
        sad, angry, or watching if none are supplied a random one is picked

        """
        author = ctx.author
        new_avatar = choice([s for s in self.statuses])
        if face:
            if face.lower() not in self.statuses:
                await ctx.send("That is not a valid choice.")
                return
            new_avatar = face
        if isinstance(style, discord.Colour):
            choice_avatar = await self.dl_image(self.statuses[new_avatar]["transparent"])
            task = functools.partial(
                self.replace_colour, img=choice_avatar, to_colour=style.to_rgb()
            )
            task = self.bot.loop.run_in_executor(None, task)
            try:
                file = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
        else:
            if isinstance(style, discord.Member):
                author = style
            if author.is_avatar_animated() and is_gif:
                author_avatar = await self.dl_image(author.avatar_url_as(format="gif"))
            else:
                author_avatar = await self.dl_image(author.avatar_url_as(format="png"))
            choice_avatar = await self.dl_image(self.statuses[new_avatar]["transparent"])
            task = functools.partial(
                self.make_new_avatar,
                author_avatar=author_avatar,
                choice_avatar=choice_avatar,
                is_gif=is_gif,
            )
            task = self.bot.loop.run_in_executor(None, task)
            try:
                file = await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
        embed = discord.Embed(colour=author.colour, description="TrustyAvatar")
        embed.set_author(
            name="{} - {}".format(author, author.display_name), icon_url=author.avatar_url
        )
        embed.set_image(url="attachment://trustyavatar.png")
        image = discord.File(file, "trustyavatar.png")
        if is_gif:
            image = discord.File(file, "trustyavatar.gif")
            embed.set_image(url="attachment://trustyavatar.gif")
        await ctx.send(embed=embed, files=[image])

    @commands.group(aliases=["taset"])
    @checks.is_owner()
    async def trustyavatarset(self, ctx: commands.Context):
        """
        Commands for overriding aspects of the bots avatar changes
        """
        pass

    @trustyavatarset.command()
    async def set(self, ctx: commands.Context, *, name: str):
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

    @trustyavatarset.command()
    async def status(self, ctx: commands.Context):
        """
        Toggle status automatic changing
        """
        is_override = await self.config.status()
        await self.config.status.set(not is_override)
        await ctx.send("Status override set to " + str(not is_override))

    @trustyavatarset.command()
    async def guild(self, ctx: commands.Context, guild_id: int):
        """
        Set a guild preferrably owned by the bot owner for the bot
        to use to get a member object of the owner for streaming status
        updates.
        """
        await self.config.search_guild.set(guild_id)
        await ctx.send("Default guild set to " + str(guild_id))

    @trustyavatarset.command()
    async def avatar(self, ctx: commands.Context):
        """
        Toggle avatar automatic changing
        """
        is_override = await self.config.avatar()
        await self.config.avatar.set(not is_override)
        await ctx.send("Avatar override set to " + str(not is_override))

    @trustyavatarset.command()
    async def streaming(self, ctx: commands.Context):
        """
        Toggle owner streaming sync
        """
        is_streaming = await self.config.streaming()
        await self.config.streaming.set(not is_streaming)
        await ctx.send("Streaming sync set to " + str(not is_streaming))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """This essentially syncs streaming status with the bot owner"""
        if before.id != self.bot.owner_id:
            return
        if not await self.config.streaming():
            return
        for activity in after.activities:
            if type(activity) == discord.ActivityType.streaming:
                await self.bot.change_presence(activity=after.activity)

    async def change_avatar(self, url: str) -> None:
        now = datetime.now().timestamp()
        last = await self.config.last_avatar()
        if (now - last) > 1800:
            # Some extra checks so we don't get rate limited over reloads/resets
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as image:
                        data = await image.read()
                await self.bot.user.edit(avatar=data)
            except Exception as e:
                print(e)
            await self.config.last_avatar.set(now)

    async def change_activity(
        self, status: Optional[discord.Status], activity: discord.ActivityType
    ) -> None:
        try:
            await self.bot.change_presence(status=status, activity=activity)
        except Exception:
            log.error("Error updating presence", exc_info=True)

    async def get_activity(self, new_status: dict) -> tuple:
        """
        This will return which avatar, status, and activity to use
        """
        date = datetime.now()
        activity = discord.Activity(
            name=choice(new_status["game"]), type=choice(new_status["type"])
        )
        status = new_status["status"]
        url = new_status["link"]
        if date.month == 12 and date.day <= 25:
            url = new_status["xmas"]
            activity = discord.Activity(name="Merry Christmas!", type=discord.ActivityType.playing)
            status = discord.Status.online
        elif (date.month == 12 and date.day >= 30) or (date.month == 1 and date.day == 1):
            url = new_status["link"]
            activity = discord.Activity(name="Happy New Year!", type=discord.ActivityType.playing)
            status = discord.Status.online
        return status, activity, url

    async def get_bot_owner_streaming(self) -> Tuple[bool, Optional[discord.Activity]]:
        """
        Probably somewhat expensive once we start scaling
        Hopefully we can get owner as a member object easier in the future
        without hard coding a server to search for the owner of the bot
        """
        guild_id = await self.config.search_guild()
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False, None
        owner = guild.get_member(self.bot.owner_id)
        for activity in owner.activites:
            if type(activity) == discord.ActivityType.streaming:
                return True, activity
        return False

    async def maybe_change_avatar(self) -> None:
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        while self is self.bot.get_cog("TrustyAvatar"):

            new_avatar = choice([s for s in self.statuses])
            new_status = self.statuses.get(new_avatar, None)
            status, activity, url = await self.get_activity(new_status)
            is_streaming, stream_activity = await self.get_bot_owner_streaming()
            if await self.config.streaming():
                if is_streaming:
                    await self.change_activity(None, stream_activity)
                    log.debug("Changing to owner is streaming status.")
            if await self.config.status() and not is_streaming:
                # we don't want to override the streaming status if the owner is streaming
                await self.change_activity(status, activity)
                log.debug("Changing to random status.")
            if await self.config.avatar():
                await self.change_avatar(url)
                log.debug("changing avatar to {}".format(new_avatar))
            await asyncio.sleep(randint(1800, 3600))

    def cog_unload(self):
        self.loop.cancel()

    __unload = cog_unload
