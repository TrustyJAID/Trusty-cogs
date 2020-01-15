from .eventposter import EventPoster


async def setup(bot):
    cog = EventPoster(bot)
    bot.add_cog(cog)
