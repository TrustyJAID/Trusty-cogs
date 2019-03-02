from .retrigger import ReTrigger


async def setup(bot):
    cog = ReTrigger(bot)
    bot.add_cog(cog)
