from .twitch import Twitch


async def setup(bot):
    cog = Twitch(bot)
    bot.add_cog(cog)
