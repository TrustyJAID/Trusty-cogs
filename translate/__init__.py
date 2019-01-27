from .translate import Translate


def setup(bot):
    n = Translate(bot)
    bot.add_cog(n)
