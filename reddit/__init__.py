from .reddit import Reddit


async def setup(bot):
    cog = Reddit(bot)
    await cog.initialize()
    bot.add_cog(cog)