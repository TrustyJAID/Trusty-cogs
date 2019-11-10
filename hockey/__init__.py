from .hockey import Hockey


async def setup(bot):
    cog = Hockey(bot)
    await cog.initialize_pickems()
    bot.add_cog(cog)
