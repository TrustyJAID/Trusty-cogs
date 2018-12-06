from .conversions import Conversions


def setup(bot):
    n = Conversions(bot)
    bot.add_cog(n)