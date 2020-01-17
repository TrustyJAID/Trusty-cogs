from .starboard import Starboard


async def setup(bot):
    cog = Starboard(bot)
    await cog.initialize()
    bot.add_cog(cog)
