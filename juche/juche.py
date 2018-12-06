import discord
from redbot.core import commands, Config

class Juche(getattr(commands, "Cog", object)):
    """
        Convert dates into the juche calendar
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 4563465345472)
        default = {"correct_juche":False}
        self.config.register_guild(**default)
    
    async def check_date(self, message):
        for i in range(1912, 2100):
            if str(i) in message.split(" ") and "http" not in message:
                message = message.replace(str(i), "Juche " + str(i-1912+1))
                message = "I think you mean Juche " + str(i-1912+1) + "."
                return message

        return None

    @commands.command()
    async def juche(self, ctx):
        """
            Toggle the bot correcting dates in messages with the juche calendar
        """
        if await self.config.guild(ctx.guild).correct_juche():
            await self.config.guild(ctx.guild).correct_juche.set(False)
            await ctx.send("No longer correcting dates to the Juche calendar.")
        else:
            await self.config.guild(ctx.guild).correct_juche.set(True)
            await ctx.send("Now correcting dates to the Juche calendar.")

    async def on_message(self, message):
        msg = message.content
        if not hasattr(message, "guild"):
            return
        guild = message.guild
        channel = message.channel

        if await self.config.guild(guild).correct_juche():
            juche = await self.check_date(msg)
            if juche != None:
                await channel.send(juche)
