from .retrigger import ReTrigger


async def setup(bot):
    cog = ReTrigger(bot)
    await cog.initialize()
    bot.add_cog(cog)
