import asyncio
import functools
import logging
import os

import aiohttp
import discord
import moviepy
import yt_dlp as youtube_dl
from moviepy.editor import CompositeVideoClip, TextClip, VideoFileClip
from red_commons.logging import getLogger
from redbot.core import checks, commands
from redbot.core.data_manager import cog_data_path

logging.captureWarnings(False)


CRAB_LINK = "https://youtu.be/gDLE3LikgUs"

MIKU_LINK = "https://youtu.be/qeJjQGF6gz4"

FONT_FILE = "https://github.com/matomo-org/travis-scripts/raw/master/fonts/Verdana.ttf"
log = getLogger("red.trusty-cogs.crabrave")


class CrabRave(commands.Cog):
    """
    Create your very own crab rave
    """

    __author__ = ["DankMemer Team", "TrustyJAID", "thisisjvgrace"]
    __version__ = "1.1.3"

    def __init__(self, bot):
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return (
            f"{pre_processed}\n\n"
            f"Cog Version: {self.__version__}\n"
            f"yt-dlp Version: {youtube_dl.version.__version__}\n"
            f"MoveiPy Version: {moviepy.version.__version__}"
        )

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def check_video_file(self, link: str, name_template: str) -> bool:
        if not (cog_data_path(self) / name_template).is_file():
            try:
                loop = asyncio.get_running_loop()
                task = functools.partial(
                    self.dl_from_youtube, link=link, name_template=name_template
                )
                task = loop.run_in_executor(None, task)
                return await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                log.exception("Error downloading the crabrave video")
                return False
            except Exception:
                log.error("Error downloading crabrave video template", exc_info=True)
                return False
        return True

    def dl_from_youtube(self, link, name_template):
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]",
            "outtmpl": str(cog_data_path(self) / name_template),
        }
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
        except Exception:
            log.exception("Error downloading the video from YouTube.")
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
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.max_concurrency(2, commands.BucketType.default)
    @checks.bot_has_permissions(attach_files=True)
    async def crab(self, ctx: commands.Context, *, text: str):
        """Make crab rave videos

        There must be exactly 1 `,` to split the message
        """
        async with ctx.typing():
            t = ctx.message.clean_content[len(f"{ctx.prefix}{ctx.invoked_with}") :]
            t = t.upper().replace(", ", ",").split(",")
            if not await self.check_video_file(CRAB_LINK, "crab_template.mp4"):
                return await ctx.send("I couldn't download the template file.")
            if not await self.check_font_file():
                return await ctx.send("I couldn't download the font file.")
            if len(t) != 2:
                return await ctx.send("You must submit exactly two strings split by comma")
            if (not t[0] and not t[0].strip()) or (not t[1] and not t[1].strip()):
                return await ctx.send("Cannot render empty text")
            fake_task = functools.partial(self.make_crab, t=t, u_id=ctx.message.id)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, fake_task)

            try:
                await asyncio.wait_for(task, timeout=300)
            except asyncio.TimeoutError:
                # log.error("Error generating crabrave video", exc_info=True)
                await ctx.send("Crabrave Video took too long to generate.")
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
        clip = VideoFileClip(str(cog_data_path(self)) + "/crab_template.mp4")
        # clip.volume(0.5)
        text = TextClip(
            t[0], fontsize=48, color="white", stroke_width=2, stroke_color="black", font=fp
        )
        text2 = (
            TextClip(
                "____________________",
                fontsize=48,
                color="white",
                font=fp,
            )
            .set_position(("center", 210))
            .set_duration(15.4)
        )
        text = text.set_position(("center", 200)).set_duration(15.4)
        text3 = (
            TextClip(
                t[1], fontsize=48, color="white", stroke_width=2, stroke_color="black", font=fp
            )
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

    @commands.command(aliases=["mikurave"])
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.max_concurrency(2, commands.BucketType.default)
    @checks.bot_has_permissions(attach_files=True)
    async def miku(self, ctx: commands.Context, *, text: str) -> None:
        """Make miku rave videos

        There must be exactly 1 `,` to split the message
        """
        async with ctx.typing():
            t = ctx.message.clean_content[len(f"{ctx.prefix}{ctx.invoked_with}") :]
            t = t.upper().replace(", ", ",").split(",")
            if not await self.check_video_file(MIKU_LINK, "miku_template.mp4"):
                return await ctx.send("I couldn't download the template file.")
            if not await self.check_font_file():
                return await ctx.send("I couldn't download the font file.")
            if len(t) != 2:
                return await ctx.send("You must submit exactly two strings split by comma")
            if (not t[0] and not t[0].strip()) or (not t[1] and not t[1].strip()):
                return await ctx.send("Cannot render empty text")
            fake_task = functools.partial(self.make_miku, t=t, u_id=ctx.message.id)
            loop = asyncio.get_running_loop()
            task = loop.run_in_executor(None, fake_task)

            try:
                await asyncio.wait_for(task, timeout=300)
            except asyncio.TimeoutError:
                # log.error("Error generating mikurave video", exc_info=True)
                await ctx.send("Mikurave Video took too long to generate.")
                return
            fp = cog_data_path(self) / f"{ctx.message.id}mikurave.mp4"
            file = discord.File(str(fp), filename="mikurave.mp4")
            try:
                await ctx.send(files=[file])
            except Exception:
                log.error("Error sending mikurave video", exc_info=True)
                pass
            try:
                os.remove(fp)
            except Exception:
                log.error("Error deleting mikurave video", exc_info=True)

    def make_miku(self, t: str, u_id: int) -> bool:
        """Non blocking miku rave video generation from DankMemer bot

        https://github.com/DankMemer/meme-server/blob/master/endpoints/crab.py
        """
        fp = str(cog_data_path(self) / f"Verdana.ttf")
        clip = VideoFileClip(str(cog_data_path(self)) + "/miku_template.mp4")
        # clip.volume(1.0)
        text = TextClip(t[0], fontsize=48, color="DarkSlateGrey", font=fp)
        text2 = (
            TextClip(
                "____________________",
                fontsize=48,
                color="DarkSlateGrey",
                font=fp,
            )
            .set_position(("center", 210))
            .set_duration(40.0)
        )
        text = text.set_position(("center", 200)).set_duration(40.0)
        text3 = (
            TextClip(
                t[1],
                fontsize=48,
                color="DarkSlateGrey",
                font=fp,
            )
            .set_position(("center", 270))
            .set_duration(40.0)
        )

        video = CompositeVideoClip(
            [clip, text.crossfadein(1), text2.crossfadein(1), text3.crossfadein(1)]
        ).set_duration(40.0)
        video = video.volumex(0.7)
        video.write_videofile(
            str(cog_data_path(self)) + f"/{u_id}mikurave.mp4",
            threads=1,
            preset="superfast",
            verbose=False,
            logger=None,
            temp_audiofile=str(cog_data_path(self) / f"{u_id}mikuraveaudio.mp3")
            # ffmpeg_params=["-filter:a", "volume=0.5"]
        )
        clip.close()
        video.close()
        return True
