from .translate import Translate


async def setup(bot):
    cog = Translate(bot)
    await cog.init()
    bot.add_cog(cog)
