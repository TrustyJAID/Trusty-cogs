import io
import re
from typing import cast

import aiohttp
import discord
from redbot.core import Config, checks, commands

IS_LINK_REGEX = re.compile(r"(http(s?):)([/|.|\w|\s|-])*\.(?:png)")
APNG_REGEX = re.compile(rb"fdAT")  # credit to Soulrift for researh on this


class APNGFilter(commands.Cog):
    """Filter those pesky APNG images"""

    __author__ = ["TrustyJAID", "Sinbad", "Soulrift"]
    __version__ = "1.0.1"

    def __init__(self, bot):
        self.bot = bot
        default = {"enabled": False}
        self.config = Config.get_conf(self, 435457347654)
        self.config.register_guild(**default)

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

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def apngfilter(self, ctx: commands.Context) -> None:
        """
        Toggle APNG filters on the server
        """
        if await self.config.guild(ctx.guild).enabled():
            await self.config.guild(ctx.guild).enabled.set(False)
            msg = "Disabled"
        else:
            await self.config.guild(ctx.guild).enabled.set(True)
            msg = "Enabled"
        await ctx.send("APNG Filter " + msg)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        if not await self.config.guild(message.guild).enabled():
            return
        channel = cast(discord.TextChannel, message.channel)
        if not channel.permissions_for(channel.guild.me).manage_messages:
            return
        is_link = IS_LINK_REGEX.findall(message.content)

        autoimmune = getattr(self.bot, "is_automod_immune", None)
        if autoimmune and await autoimmune(message):
            return

        for attachment in message.attachments:
            if attachment.filename.split(".")[-1] not in ("apng", "png"):
                continue  # discord attempts to render by file extension, not mime type
            # keeps requests on the bot's session, prventing a unauthenticated ratelimit for attachments
            temp = io.BytesIO()
            await attachment.save(temp)
            temp.seek(0)
            # https://stackoverflow.com/questions/4525152/can-i-programmatically-determine-if-a-png-is-animated
            if APNG_REGEX.search(temp.getvalue()):
                await message.delete()
                break
        if is_link:
            for files in IS_LINK_REGEX.finditer(message.content):
                async with aiohttp.ClientSession() as session:
                    async with session.get(files.group()) as file:
                        temp = io.BytesIO()
                        data = await file.read()
                        temp.write(data)
                        temp.seek(0)
                if APNG_REGEX.search(temp.getvalue()):
                    await message.delete()
