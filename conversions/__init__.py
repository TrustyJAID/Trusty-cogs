from .conversions import Conversions


async def setup(bot):
    n = Conversions(bot)
    bot.add_cog(n)
