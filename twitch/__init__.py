from .twitch import Twitch


async def setup(bot):
    cog = Twitch(bot)
    await cog.initialize()
    bot.add_cog(cog)
