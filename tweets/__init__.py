from .tweets import Tweets


async def setup(bot):
    cog = Tweets(bot)
    await cog.initialize()
    bot.add_cog(cog)
