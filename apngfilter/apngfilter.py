import discord
import aiohttp
from redbot.core import checks, commands, Config


class APNGFilter(getattr(commands, "Cog", object)):
    """Filter those pesky APNG images"""

    def __init__(self, bot):
        self.bot = bot
        default = {"enabled":False}
        self.config = Config.get_conf(self, 435457347654)
        self.config.register_guild(**default)

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def apngfilter(self, ctx):
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

    async def on_message(self, message):
        if message.guild is None:
            return
        if message.attachments == []:
            return
        if not await self.config.guild(message.guild).enabled():
            return
        channel = message.channel
        channel_perms = channel.permissions_for(channel.guild.me).manage_messages
        for attachment in message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as infile:
                    # https://stackoverflow.com/questions/4525152/can-i-programmatically-determine-if-a-png-is-animated
                    if b"acTL" in await infile.read():
                        if channel_perms:
                            await message.delete()