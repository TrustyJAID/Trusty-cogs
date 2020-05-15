import os
import discord
import aiohttp
import asyncio
import logging
import functools

from redbot.core import commands, checks
from redbot.core.data_manager import cog_data_path

from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

logging.captureWarnings(False)


CRAB_LINK = (
    "https://github.com/DankMemer/meme-server"
    "/raw/9ce10a61e133f5b87b24d425fc671c9295affa6a/assets/crab/template.mp4"
)
# Use a historical link incase something changes
FONT_FILE = (
    "https://github.com/matomo-org/travis-scripts/"
    "raw/65cace9ce09dca617832cbac2bbae3dacdffa264/fonts/Verdana.ttf"
)
log = logging.getLogger("red.trusty-cogs.crabrave")


class CrabRave(commands.Cog):
    """
        Create your very own crab rave
    """
    __author__ = ["DankMemer Team", "TrustyJAID"]
    __version__ = "1.0.1"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def check_video_file(self) -> bool:
        if not (cog_data_path(self) / "template.mp4").is_file():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(CRAB_LINK) as resp:
                        data = await resp.read()
                with open(cog_data_path(self) / "template.mp4", "wb") as save_file:
                    save_file.write(data)
            except Exception:
                log.error("Error downloading crabrave video template", exc_info=True)
                return False
        return True

    async def check_font_file(self) -> bool:
        if not (cog_data_path(self) / "Verdana.ttf").is_file():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(FONT_FILE) as resp:
                        data = await resp.read()
                with open(cog_data_path(self) / "Verdana.ttf", "wb") as save_file:
                    save_file.write(data)
            except Exception:
                log.error("Error downloading crabrave video template", exc_info=True)
                return False
        return True

    @commands.command(aliases=["crabrave"])
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @checks.bot_has_permissions(attach_files=True)
    async def crab(self, ctx: commands.Context, *, text: str) -> None:
        """Make crab rave videos

            There must be exactly 1 `,` to split the message
        """
        t = ctx.message.clean_content[len(f"{ctx.prefix}{ctx.invoked_with}"):]
        t = t.upper().replace(", ", ",").split(",")
        if not await self.check_video_file():
            return await ctx.send("I couldn't download the template file.")
        if not await self.check_font_file():
            return await ctx.send("I couldn't download the font file.")
        if len(t) != 2:
            return await ctx.send("You must submit exactly two strings split by comma")
        if (not t[0] and not t[0].strip()) or (not t[1] and not t[1].strip()):
            return await ctx.send("Cannot render empty text")
        fake_task = functools.partial(self.make_crab, t=t, u_id=ctx.message.id)
        task = self.bot.loop.run_in_executor(None, fake_task)
        async with ctx.typing():
            try:
                await asyncio.wait_for(task, timeout=300)
            except asyncio.TimeoutError:
                log.error("Error generating crabrave video", exc_info=True)
                return
        fp = cog_data_path(self) / f"{ctx.message.id}crabrave.mp4"
        file = discord.File(str(fp), filename="crabrave.mp4")
        try:
            await ctx.send(files=[file])
        except Exception:
            log.error("Error sending crabrave video", exc_info=True)
            pass
        try:
            os.remove(fp)
        except Exception:
            log.error("Error deleting crabrave video", exc_info=True)

    def make_crab(self, t: str, u_id: int) -> bool:
        """Non blocking crab rave video generation from DankMemer bot

        https://github.com/DankMemer/meme-server/blob/master/endpoints/crab.py
        """
        fp = str(cog_data_path(self) / f"Verdana.ttf")
        clip = VideoFileClip(str(cog_data_path(self)) + "/template.mp4")
        # clip.volume(0.5)
        text = TextClip(t[0], fontsize=48, color="white", font=fp)
        text2 = (
            TextClip("____________________", fontsize=48, color="white", font=fp)
            .set_position(("center", 210))
            .set_duration(15.4)
        )
        text = text.set_position(("center", 200)).set_duration(15.4)
        text3 = (
            TextClip(t[1], fontsize=48, color="white", font=fp)
            .set_position(("center", 270))
            .set_duration(15.4)
        )

        video = CompositeVideoClip(
            [clip, text.crossfadein(1), text2.crossfadein(1), text3.crossfadein(1)]
        ).set_duration(15.4)
        video = video.volumex(0.1)
        video.write_videofile(
            str(cog_data_path(self)) + f"/{u_id}crabrave.mp4",
            threads=1,
            preset="superfast",
            verbose=False,
            logger=None,
            temp_audiofile=str(cog_data_path(self) / f"{u_id}crabraveaudio.mp3")
            # ffmpeg_params=["-filter:a", "volume=0.5"]
        )
        clip.close()
        video.close()
        return True
