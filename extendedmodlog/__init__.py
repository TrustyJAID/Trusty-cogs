from .extendedmodlog import ExtendedModLog


async def setup(bot):
    cog = ExtendedModLog(bot)
    await cog.initialize()
    bot.add_cog(cog)
