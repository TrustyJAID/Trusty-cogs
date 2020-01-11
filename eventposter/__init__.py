from .eventposter import EventPoster


async def setup(bot):
    cog = EventPoster(bot)
    await cog.initialize()
    bot.add_cog(cog)
